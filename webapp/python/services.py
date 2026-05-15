import json
import hashlib
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from webapp.python.models import (
    Event, Contestant, Score, Criteria, 
    Segment, AuditLog, ScoreLedger, EventJudge
)

# SocketIO import for broadcasting
try:
    from flask_socketio import emit
except ImportError:
    emit = None

# =========================================================
# LEDGER & DECENTRALIZATION UTILITIES
import threading

# Global lock to prevent blockchain forks during concurrent score submissions
ledger_lock = threading.Lock()

def append_to_ledger(db: Session, score_obj: Score):
    """
    Creates a new immutable block in the ScoreLedger table and 
    broadcasts it to all connected devices to ensure decentralization.
    """
    # 1. Retrieve the latest block for chaining
    last_block = db.query(ScoreLedger).order_by(ScoreLedger.block_index.desc()).first()
    
    prev_hash = "0" * 64  # Genesis fallback
    next_index = 1
    
    if last_block:
        prev_hash = last_block.current_hash
        next_index = last_block.block_index + 1

    # 2. Prepare the data snapshot
    data_payload = {
        "score_id": score_obj.id,
        "contestant_id": score_obj.contestant_id,
        "judge_id": score_obj.judge_id,
        "segment_id": score_obj.segment_id,
        "criteria_id": getattr(score_obj, 'criteria_id', None),
        "score_value": float(score_obj.score_value) if score_obj.score_value else 0.0,
        "is_correct": score_obj.is_correct,
        "timestamp": datetime.now().isoformat()
    }
    
    data_str = json.dumps(data_payload, sort_keys=True)

    # 3. Instantiate the ledger entry
    # IMPORTANT: Set timestamp explicitly so generate_hash() uses the
    # same value that will be persisted. Relying on the column default
    # leaves self.timestamp as None at hash-generation time, which
    # causes verify_ledger_integrity() to fail later.
    block_timestamp = datetime.now().replace(microsecond=0)
    
    new_block = ScoreLedger(
        block_index=next_index,
        score_id=score_obj.id,
        data_snapshot=data_str,
        previous_hash=prev_hash,
        timestamp=block_timestamp
    )
    
    # Generate hash using the model's method
    new_block.current_hash = new_block.generate_hash()
    
    db.add(new_block)
    # Flush ensures the block is ready but not yet final in case the broadcast logic fails
    db.flush()

    # 4. BROADCAST: True Decentralization
    # This sends the block data to all connected browser "nodes"
    if emit:
        # Include integrity status so widgets know if chain is broken
        # We only do the fast chain check here to prevent slowdowns on every score
        is_valid, _, _ = verify_ledger_integrity(db, full_check=False)
        
        block_data = {
            "index": new_block.block_index,
            "prev_hash": new_block.previous_hash,
            "curr_hash": new_block.current_hash,
            "data": data_str,
            "timestamp": str(new_block.timestamp),
            "integrity": is_valid
        }
        # namespace='/' ensures global broadcast
        try:
            emit('new_ledger_block', block_data, namespace='/', broadcast=True)
        except Exception:
            # Prevent scoring failure if socket broadcast fails
            pass

def verify_ledger_integrity(db: Session, full_check: bool = True):
    """
    Two-layer verification:
    1. CHAIN CHECK: Walks the chain to verify hash links are intact.
    2. DATA CHECK: Cross-references the latest ledger snapshot for each
       score against the actual Score table to detect direct DB tampering.
    
    Returns: (is_valid, message, list_of_compromised_block_indices)
    """
    import json
    
    blocks = db.query(ScoreLedger).order_by(ScoreLedger.block_index.asc()).all()
    expected_prev_hash = "0" * 64
    
    # Layer 1: Chain integrity
    for block in blocks:
        if block.previous_hash != expected_prev_hash:
            return False, f"Chain broken at block {block.block_index}: Previous hash mismatch.", [block.block_index]
            
        recalculated_hash = block.generate_hash()
        if block.current_hash != recalculated_hash:
            return False, f"Chain broken at block {block.block_index}: Block data tampered.", [block.block_index]
            
        expected_prev_hash = block.current_hash
    
    if not full_check:
        return True, "Chain integrity verified (fast check).", []
    
    # Layer 2: Cross-reference ALL latest ledger entries against actual DB scores
    # Build a map of score_id -> latest snapshot (highest block_index wins)
    latest_snapshots = {}
    for block in blocks:
        if block.score_id:
            try:
                data = json.loads(block.data_snapshot)
                latest_snapshots[block.score_id] = {
                    'block_index': block.block_index,
                    'score_value': data.get('score_value'),
                    'is_correct': data.get('is_correct'),
                }
            except (json.JSONDecodeError, AttributeError):
                pass
    
    # Collect ALL tampered blocks instead of returning on the first one
    compromised_blocks = []
    tamper_details = []
    
    for score_id, snapshot in latest_snapshots.items():
        actual_score = db.query(Score).filter(Score.id == score_id).first()
        if not actual_score:
            continue
        
        # Check score_value
        ledger_val = float(snapshot['score_value']) if snapshot['score_value'] is not None else None
        actual_val = float(actual_score.score_value) if actual_score.score_value is not None else None
        
        if ledger_val is not None and actual_val is not None:
            if round(ledger_val, 4) != round(actual_val, 4):
                compromised_blocks.append(snapshot['block_index'])
                tamper_details.append(
                    f"Block #{snapshot['block_index']}: Score ID {score_id} "
                    f"was {ledger_val} \u2192 now {actual_val}"
                )
        
        # Check is_correct (for quiz bee)
        if snapshot['is_correct'] is not None:
            if actual_score.is_correct != snapshot['is_correct']:
                compromised_blocks.append(snapshot['block_index'])
                tamper_details.append(
                    f"Block #{snapshot['block_index']}: Score ID {score_id} answer "
                    f"was {'correct' if snapshot['is_correct'] else 'wrong'} \u2192 "
                    f"now {'correct' if actual_score.is_correct else 'wrong'}"
                )
    
    if compromised_blocks:
        msg = f"Score tampering detected in {len(compromised_blocks)} block(s)! " + " | ".join(tamper_details)
        return False, msg, compromised_blocks
    
    return True, "Ledger integrity verified. All blocks and scores match.", []

# =========================================================
# CORE SCORING SERVICES
# =========================================================

def submit_pageant_score(db: Session, judge_id: int, contestant_id: int, criteria_id: int, score_value: float):
    try:
        score = db.query(Score).filter_by(
            judge_id=judge_id, 
            contestant_id=contestant_id, 
            criteria_id=criteria_id
        ).first()
        
        crit = db.query(Criteria).filter_by(id=criteria_id).first()
        if not crit:
            return False, "Criteria not found"
            
        if score:
            score.score_value = score_value
        else:
            score = Score(
                contestant_id=contestant_id,
                judge_id=judge_id,
                criteria_id=criteria_id,
                segment_id=crit.segment_id,
                score_value=score_value
            )
            db.add(score)
        
        # Record and Broadcast securely with a lock
        with ledger_lock:
            # CRITICAL: Flush to generate score.id for ledger snapshot
            db.flush()
            append_to_ledger(db, score)
            db.commit()
            
        return True, "Score saved and broadcast to ledger."
    except Exception as e:
        db.rollback()
        return False, f"Error: {str(e)}"

def submit_quizbee_score(db: Session, judge_id: int, contestant_id: int, question_num: int, is_correct: bool, segment_id: int):
    try:
        score = db.query(Score).filter_by(
            judge_id=judge_id,
            contestant_id=contestant_id,
            question_number=question_num,
            segment_id=segment_id
        ).first()

        if score:
            score.is_correct = is_correct
            score.score_value = 1.0 if is_correct else 0.0
        else:
            score = Score(
                judge_id=judge_id,
                contestant_id=contestant_id,
                question_number=question_num,
                segment_id=segment_id,
                is_correct=is_correct,
                score_value=1.0 if is_correct else 0.0
            )
            db.add(score)

        with ledger_lock:
            db.flush()
            append_to_ledger(db, score)
            db.commit()
            
        return True, "Point recorded and broadcast to ledger."
    except Exception as e:
        db.rollback()
        return False, str(e)

# =========================================================
# LIVE TABULATION & RANKING
# =========================================================

def get_live_leaderboard(db: Session, event_id: int):
    event = db.query(Event).get(event_id)
    if not event:
        return []
    return calculate_rankings(db, event_id)

def calculate_rankings(db: Session, event_id: int):
    event = db.query(Event).get(event_id)
    contestants = db.query(Contestant).filter(Contestant.event_id == event_id, Contestant.status == 'Active').all()
    results = []

    for c in contestants:
        total_score = 0
        if event.event_type == 'Score-Based':
            scores = db.query(Score).filter(Score.contestant_id == c.id).all()
            for s in scores:
                if s.criteria:
                    total_score += (s.score_value * (s.criteria.weight / 100))
        else:
            total_score = db.query(func.sum(Score.score_value)).filter(Score.contestant_id == c.id).scalar() or 0

        results.append({
            'id': c.id,
            'name': c.name,
            'number': c.candidate_number,
            'total_score': round(total_score, 2)
        })

    results.sort(key=lambda x: x['total_score'], reverse=True)
    for i, res in enumerate(results):
        res['rank'] = i + 1
    return results

# =========================================================
# ADMIN DASHBOARD CALCULATIONS
# =========================================================

def calculate_dashboard_progress(db: Session, active_events, recent_events):
    event_progress = {}
    total_actual = 0
    total_expected = 0
    
    all_events = db.query(Event).all()
    unique_events_ids = set(e.id for e in (active_events + recent_events))

    for event in all_events:
        judge_count = db.query(EventJudge).filter(EventJudge.event_id == event.id).count()
        contestant_count = db.query(Contestant).filter(Contestant.event_id == event.id, Contestant.status == 'Active').count()
        
        if event.event_type == 'Score-Based':
            criteria_count = db.query(Criteria).join(Segment).filter(Segment.event_id == event.id).count()
            expected = judge_count * contestant_count * criteria_count
        else:
            total_q = db.query(func.sum(Segment.total_questions)).filter(Segment.event_id == event.id).scalar() or 0
            expected = contestant_count * total_q

        actual = db.query(Score).join(Contestant).filter(Contestant.event_id == event.id).count()
        
        # Cap actual at expected to prevent percentages > 100% due to data anomalies
        capped_actual = min(actual, expected) if expected > 0 else 0
        
        if event.id in unique_events_ids:
            pct = (capped_actual / expected * 100) if expected > 0 else 0
            event_progress[event.id] = round(min(pct, 100), 1)
        
        total_actual += capped_actual
        total_expected += expected

    global_pct = (total_actual / total_expected * 100) if total_expected > 0 else 0
    return round(global_pct, 1), event_progress
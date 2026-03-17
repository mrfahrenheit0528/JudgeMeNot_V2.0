from sqlalchemy.orm import Session
from webapp.python.models import Event, Score, Contestant, Criteria, JudgeProgress, Score

def submit_pageant_score(db: Session, judge_id: int, contestant_id: int, criteria_id: int, score_value: float):
    score = db.query(Score).filter_by(
        judge_id=judge_id, contestant_id=contestant_id, criteria_id=criteria_id
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
    db.commit()
    return True, "Score saved"


def get_live_leaderboard(db: Session, event_id: int):
    """
    Universal fallback generator used by PDF Exporters and basic tables.
    Returns a unified leaderboard accurately calculating weights.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event_id).all()
    
    results = []
    final_started = False
    final_seg = next((s for s in event.segments if s.is_final), None)
    
    if final_seg:
        if final_seg.is_active or any(s.segment_id == final_seg.id and s.score_value is not None for s in all_scores):
            final_started = True

    for contestant in event.contestants:
        prelim_score = 0.0
        final_score = 0.0
        
        for segment in event.segments:
            if not segment.is_contestant_allowed(contestant.id):
                continue
                
            if event.event_type == 'Point-Based':
                pts = sum([segment.points_per_question for s in all_scores if s.contestant_id == contestant.id and s.segment_id == segment.id and s.is_correct])
                if segment.is_final or 'Clincher' in segment.name or 'Tie Breaker' in segment.name:
                    final_score += pts
                else:
                    prelim_score += pts
            else:
                # THE FIX: Applying Criteria Weights properly in the Fallback engine
                crit_weights = {crit.id: (crit.weight / 100.0 if crit.weight > 1.0 else crit.weight) for crit in segment.criteria}
                
                seg_scores_arr = []
                for j in event.assigned_judges:
                    j_score = 0.0
                    has_scores = False
                    for s in all_scores:
                        if s.contestant_id == contestant.id and s.segment_id == segment.id and s.judge_id == j.judge_id and s.score_value is not None:
                            cw = crit_weights.get(s.criteria_id, 1.0)
                            j_score += s.score_value * cw
                            has_scores = True
                            
                    if has_scores:
                        seg_scores_arr.append(j_score)
                        
                avg_seg = sum(seg_scores_arr) / len(seg_scores_arr) if seg_scores_arr else 0.0
                
                w_seg = segment.percentage_weight or 0.0
                if w_seg > 1.0: w_seg = w_seg / 100.0
                
                pts = avg_seg * w_seg if w_seg > 0 else avg_seg
                
                if segment.is_final or 'Clincher' in segment.name or 'Tie Breaker' in segment.name:
                    final_score += pts
                else:
                    prelim_score += pts
                    
        # Add contestant calculation to payload
        results.append({
            "contestant": contestant,
            "score": final_score if final_started else prelim_score,
            "prelim_score": prelim_score,
            "final_score": final_score
        })

    # Descending standard sort
    results.sort(key=lambda x: x["final_score"] if final_started else x["prelim_score"], reverse=True)
    
    # Define simple rank
    rank = 1
    for r in results:
        r["rank"] = rank
        rank += 1
        
    return results

def calculate_dashboard_progress(db, active_events, recent_events):
    """Calculates global and per-event progress percentages for the dashboard."""
    # --- 1. GLOBAL SCORES SUBMITTED (Active Events Only) ---
    global_expected = 0
    global_actual = 0
    
    for event in active_events:
        if event.event_type == 'Score-Based':
            judges_count = len(event.assigned_judges)
            for seg in event.segments:
                global_expected += judges_count
                global_actual += db.query(JudgeProgress).filter(JudgeProgress.segment_id == seg.id, JudgeProgress.is_submitted == True).count()
        else: # Point-Based
            contestant_count = len(event.contestants)
            for seg in event.segments:
                qs = seg.total_questions or 0
                global_expected += contestant_count * qs
                global_actual += db.query(Score).filter(Score.segment_id == seg.id).count()
                
    global_progress_pct = int((global_actual / global_expected) * 100) if global_expected > 0 else 0
    
    # --- 2. INDIVIDUAL EVENT PROGRESS (For the Progress Bars) ---
    event_progress = {}
    for event in recent_events:
        expected = 0
        actual = 0
        
        if event.event_type == 'Score-Based':
            judges_count = len(event.assigned_judges)
            for seg in event.segments:
                expected += judges_count
                actual += db.query(JudgeProgress).filter(JudgeProgress.segment_id == seg.id, JudgeProgress.is_submitted == True).count()
        else:
            contestant_count = len(event.contestants)
            for seg in event.segments:
                qs = seg.total_questions or 0
                expected += contestant_count * qs
                actual += db.query(Score).filter(Score.segment_id == seg.id).count()
        
        event_progress[event.id] = int((actual / expected) * 100) if expected > 0 else 0
        
    return global_progress_pct, event_progress
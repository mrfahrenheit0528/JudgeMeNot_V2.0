from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, session
from webapp.python.database import SessionLocal
from webapp.python.models import Event, EventJudge, Contestant, Segment, Score, Criteria, JudgeProgress
from webapp.python.auth import require_role

judge_bp = Blueprint('judge', __name__, url_prefix='/judge')

# =====================================================================
# 1. REAL-TIME DASHBOARD POLLING
# =====================================================================
@judge_bp.route('/api/status')
@require_role(['judge', 'tabulator']) 
def api_status():
    """Real-time polling API for both Pageant Judges and Quiz Bee Tabulators."""
    db = SessionLocal()
    try:
        user_id = session.get('user')['id']
        
        # 1. Fetch Score-Based Events (Pageant Judges)
        judge_assignments = db.query(EventJudge).filter(EventJudge.judge_id == user_id).all()
        assigned_event_ids = [a.event_id for a in judge_assignments]
        
        # 2. Fetch Point-Based Events (Quiz Bee Tabulators)
        tabulator_assignments = db.query(Contestant).filter(Contestant.assigned_judge_id == user_id).all()
        pb_event_ids = [c.event_id for c in tabulator_assignments]
        
        # 3. Combine unique event IDs
        all_event_ids = list(set(assigned_event_ids + pb_event_ids))
        
        events = db.query(Event).filter(Event.id.in_(all_event_ids)).all()
        
        status_data = {}
        for event in events:
            active_segment = next((s for s in event.segments if s.is_active), None)
            status_data[event.id] = {
                'status': event.status,
                'active_segment_id': active_segment.id if active_segment else None,
                'active_segment_name': active_segment.name if active_segment else None,
                'total_questions': active_segment.total_questions if active_segment else 0
            }
            
        return jsonify(status_data)
    finally:
        db.close()


# =====================================================================
# 2. POINT-BASED / QUIZ BEE SCORING
# =====================================================================
@judge_bp.route('/pb_scoring/<int:event_id>/<int:segment_id>', methods=['GET', 'POST'])
@require_role(['judge', 'tabulator']) 
def pb_scoring(event_id, segment_id):
    """Specialized Tabulator UI for Point-Based (Quiz Bee) events."""
    db = SessionLocal()
    try:
        user = session.get('user')
        segment = db.query(Segment).filter(Segment.id == segment_id).first()
        event = db.query(Event).filter(Event.id == event_id).first()

        if not segment or not segment.is_active or event.status != 'Ongoing':
            flash(f'The {segment.name} round is currently closed.', 'error')
            return redirect(url_for('index'))

        contestant = db.query(Contestant).filter(
            Contestant.event_id == event_id, 
            Contestant.assigned_judge_id == user['id']
        ).first()
        
        if not contestant:
            flash("You are not assigned to any team for this event.", 'error')
            return redirect(url_for('index'))

        if not segment.is_contestant_allowed(contestant.id):
            flash("Your team is not participating in this specific round (Did not qualify).", 'warning')
            return redirect(url_for('index'))

        if request.method == 'POST':
            from webapp.python.services import append_to_ledger
            for q_num in range(1, segment.total_questions + 1):
                answer_status = request.form.get(f'question_{q_num}')
                if answer_status:
                    is_correct_val = (answer_status == 'correct')
                    existing_score = db.query(Score).filter_by(
                        contestant_id=contestant.id, segment_id=segment.id, question_number=q_num).first()
                    
                    if existing_score:
                        # Only record to ledger if the answer actually changed
                        if existing_score.is_correct != is_correct_val:
                            existing_score.is_correct = is_correct_val
                            existing_score.score_value = 1.0 if is_correct_val else 0.0
                            existing_score.judge_id = user['id']
                            db.flush()
                            append_to_ledger(db, existing_score)
                    else:
                        new_score = Score(
                            contestant_id=contestant.id, 
                            segment_id=segment.id, 
                            judge_id=user['id'],
                            question_number=q_num, 
                            is_correct=is_correct_val,
                            score_value=1.0 if is_correct_val else 0.0
                        )
                        db.add(new_score)
                        db.flush()
                        append_to_ledger(db, new_score)
            
            db.commit()
            flash('Scores saved and broadcast to ledger!', 'success')
            return redirect(url_for('judge.pb_scoring', event_id=event_id, segment_id=segment_id))

        existing_scores = db.query(Score).filter_by(contestant_id=contestant.id, segment_id=segment.id).all()
        score_map = {s.question_number: s.is_correct for s in existing_scores}
        
        return render_template('pb_scoring.html', event=event, segment=segment, contestant=contestant, score_map=score_map)
    finally:
        db.close()


# =====================================================================
# 3. SCORE-BASED / PAGEANT SCORING
# =====================================================================
@judge_bp.route('/scoring/<int:event_id>/<int:segment_id>')
@require_role(['judge'])
def scoring(event_id, segment_id):
    """Pageant Scoring UI for Judges."""
    db = SessionLocal()
    try:
        user = session.get('user')
        event = db.query(Event).filter(Event.id == event_id).first()
        segment = db.query(Segment).filter(Segment.id == segment_id).first()
        
        if not segment or not segment.is_active or event.status != 'Ongoing':
            flash("This segment is not currently active.", "warning")
            return redirect(url_for('index'))
            
        # --- THE FIX: STRICT BACKEND ELIMINATION ---
        # Instead of sending all contestants and hiding them with HTML, 
        # we completely omit eliminated contestants from the memory payload!
        allowed_contestants = [c for c in event.contestants if segment.is_contestant_allowed(c.id)]
        
        criteria_list = segment.criteria
        
        existing_scores = db.query(Score).filter(
            Score.segment_id == segment_id,
            Score.judge_id == user['id']
        ).all()
        
        score_map = {}
        for s in existing_scores:
            if s.contestant_id not in score_map:
                score_map[s.contestant_id] = {}
            score_map[s.contestant_id][s.criteria_id] = s.score_value
            
        progress = db.query(JudgeProgress).filter(
            JudgeProgress.segment_id == segment_id,
            JudgeProgress.judge_id == user['id']
        ).first()
        is_locked = progress.is_submitted if progress else False
        
        return render_template('judge_scoring.html', 
                               event=event, 
                               segment=segment, 
                               contestants=allowed_contestants, # Injecting the filtered list!
                               criteria_list=criteria_list,
                               score_map=score_map,
                               is_locked=is_locked)
    finally:
        db.close()


@judge_bp.route('/api_submit_score', methods=['POST'])
@require_role(['judge'])
def api_submit_score():
    data = request.get_json()
    segment_id = data.get('segment_id')
    contestant_id = data.get('contestant_id')
    criteria_id = data.get('criteria_id')
    score_value = data.get('score_value')
    
    user_id = session.get('user')['id']
    db = SessionLocal()
    try:
        progress = db.query(JudgeProgress).filter_by(segment_id=segment_id, judge_id=user_id).first()
        if progress and progress.is_submitted:
            return jsonify({"status": "error", "message": "Scores are already locked."})
            
        from webapp.python.services import submit_pageant_score
        success, msg = submit_pageant_score(db, user_id, contestant_id, criteria_id, float(score_value))
        
        if success:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    finally:
        db.close()


@judge_bp.route('/api_lock_segment', methods=['POST'])
@require_role(['judge'])
def api_lock_segment():
    data = request.get_json()
    segment_id = data.get('segment_id')
    user_id = session.get('user')['id']
    
    db = SessionLocal()
    try:
        progress = db.query(JudgeProgress).filter_by(segment_id=segment_id, judge_id=user_id).first()
        if not progress:
            progress = JudgeProgress(segment_id=segment_id, judge_id=user_id, is_finished=True, is_submitted=True)
            db.add(progress)
        else:
            progress.is_finished = True
            progress.is_submitted = True
            
        db.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)})
    finally:
        db.close()
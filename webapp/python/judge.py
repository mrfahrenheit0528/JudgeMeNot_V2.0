from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for
from webapp.python.database import SessionLocal
from webapp.python.models import Event, Segment, Contestant, Criteria, Score, EventJudge, JudgeProgress
from webapp.python.auth import require_role
from webapp.python.services import submit_pageant_score

judge_bp = Blueprint('judge', __name__, url_prefix='/judge')

@judge_bp.route('/scoring/<int:event_id>/<int:segment_id>')
@require_role(['judge', 'admin'])
def scoring(event_id, segment_id):
    db = SessionLocal()
    try:
        user_id = session.get('user')['id']
        
        event = db.query(Event).filter(Event.id == event_id).first()
        segment = db.query(Segment).filter(Segment.id == segment_id).first()
        
        if not event or not segment:
            flash("Event or Segment not found.", "error")
            return redirect(url_for('index'))
            
        # Verify if the judge is actually assigned to this event
        assignment = db.query(EventJudge).filter(EventJudge.event_id == event_id, EventJudge.judge_id == user_id).first()
        if not assignment and session.get('user')['role'] != 'admin':
            flash("You are not assigned to score this event.", "error")
            return redirect(url_for('index'))
            
        # Must be an ongoing event and active segment to allow scoring
        if event.status != 'Ongoing' or not segment.is_active:
            if session.get('user')['role'] != 'admin':
                flash("This segment is currently closed for scoring.", "error")
                return redirect(url_for('index'))
                
        # Fetch Contestants and sort by candidate number
        contestants = db.query(Contestant).filter(Contestant.event_id == event_id).order_by(Contestant.candidate_number).all()
        criteria_list = db.query(Criteria).filter(Criteria.segment_id == segment_id).all()
        
        # Fetch existing scores for this judge to pre-fill the form if they reload
        existing_scores = db.query(Score).filter(
            Score.judge_id == user_id,
            Score.segment_id == segment_id
        ).all()
        
        # Structure: { contestant_id: { criteria_id: score_value } }
        score_map = {}
        for s in existing_scores:
            if s.contestant_id not in score_map:
                score_map[s.contestant_id] = {}
            score_map[s.contestant_id][s.criteria_id] = s.score_value

        # Check if judge has locked this segment
        progress = db.query(JudgeProgress).filter(JudgeProgress.judge_id == user_id, JudgeProgress.segment_id == segment_id).first()
        is_locked = progress.is_submitted if progress else False

        return render_template('judge_scoring.html', 
                               event=event, 
                               segment=segment, 
                               contestants=contestants, 
                               criteria_list=criteria_list,
                               score_map=score_map,
                               is_locked=is_locked)
    finally:
        db.close()

@judge_bp.route('/api/submit_score', methods=['POST'])
@require_role(['judge', 'admin'])
def api_submit_score():
    """Endpoint for AJAX auto-saving of scores"""
    data = request.json
    judge_id = session.get('user')['id']
    contestant_id = data.get('contestant_id')
    criteria_id = data.get('criteria_id')
    segment_id = data.get('segment_id')
    
    try:
        score_value = float(data.get('score_value'))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid score value"}), 400
        
    db = SessionLocal()
    try:
        # Prevent saving if the segment is locked for this judge
        if segment_id:
            progress = db.query(JudgeProgress).filter(JudgeProgress.judge_id == judge_id, JudgeProgress.segment_id == segment_id).first()
            if progress and progress.is_submitted:
                return jsonify({"status": "error", "message": "Scores are already locked and cannot be edited."}), 400

        # Validate against max score
        criteria = db.query(Criteria).filter(Criteria.id == criteria_id).first()
        if criteria and score_value > criteria.max_score:
            return jsonify({"status": "error", "message": f"Score cannot exceed max of {criteria.max_score}"}), 400
            
        success, msg = submit_pageant_score(db, judge_id, contestant_id, criteria_id, score_value)
        if success:
            return jsonify({"status": "success", "message": "Saved"})
        else:
            return jsonify({"status": "error", "message": msg}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@judge_bp.route('/api/lock_segment', methods=['POST'])
@require_role(['judge', 'admin'])
def api_lock_segment():
    """Endpoint to permanently lock a segment for a judge"""
    data = request.json
    segment_id = data.get('segment_id')
    user_id = session.get('user')['id']
    
    db = SessionLocal()
    try:
        progress = db.query(JudgeProgress).filter(JudgeProgress.judge_id == user_id, JudgeProgress.segment_id == segment_id).first()
        if not progress:
            progress = JudgeProgress(judge_id=user_id, segment_id=segment_id, is_submitted=True)
            db.add(progress)
        else:
            progress.is_submitted = True
        db.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

@judge_bp.route('/api/status')
@require_role(['judge'])
def api_dashboard_status():
    """Lightweight API for the Judge Dashboard to poll real-time event statuses."""
    db = SessionLocal()
    try:
        judge_id = session.get('user')['id']
        
        # Get all events assigned to this judge
        assignments = db.query(EventJudge).filter(EventJudge.judge_id == judge_id).all()
        
        data = {}
        for assignment in assignments:
            event = assignment.event
            # Find the currently active segment, if any
            active_segment = next((s for s in event.segments if s.is_active), None)
            
            data[event.id] = {
                'status': event.status,
                'active_segment_name': active_segment.name if active_segment else None,
                'active_segment_id': active_segment.id if active_segment else None
            }
            
        return jsonify(data)
    finally:
        db.close()
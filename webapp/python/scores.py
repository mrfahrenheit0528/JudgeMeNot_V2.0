from flask import Blueprint, render_template, flash, redirect, url_for
from webapp.python.database import SessionLocal
from webapp.python.models import Event, Contestant, Score
from webapp.python.auth import require_role
from webapp.python.services import get_live_leaderboard

scores_bp = Blueprint('scores', __name__, url_prefix='/admin/scores')

@scores_bp.route('/')
@require_role(['admin'])
def index():
    """Admin Hub: Shows ALL events regardless of status."""
    db = SessionLocal()
    try:
        events = db.query(Event).order_by(Event.id.desc()).all()
        return render_template('scores_main.html', events=events)
    finally:
        db.close()

@scores_bp.route('/<int:event_id>')
@require_role(['admin'])
def detail(event_id):
    """Comprehensive Table view showing judge-by-judge breakdown."""
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            flash("Event not found.", "error")
            return redirect(url_for('scores.index'))
            
        # Get overall sorted leaderboard
        overall_leaderboard = get_live_leaderboard(db, event_id)
        
        # Get raw scores
        all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event_id).all()
        
        # Build comprehensive matrix map: matrix[segment.id][contestant.id][judge.id] = total_raw_score
        matrix = {}
        for seg in event.segments:
            matrix[seg.id] = {}
            for c in event.contestants:
                matrix[seg.id][c.id] = {}
                for assignment in event.assigned_judges:
                    judge_id = assignment.judge_id
                    # Sum all criteria scores given by this judge for this segment and contestant
                    j_scores = [s.score_value for s in all_scores if s.contestant_id == c.id and s.segment_id == seg.id and s.judge_id == judge_id and s.score_value is not None]
                    
                    matrix[seg.id][c.id][judge_id] = sum(j_scores) if j_scores else '-'

        return render_template('scores_detail.html', 
                               event=event, 
                               overall_leaderboard=overall_leaderboard,
                               matrix=matrix)
    finally:
        db.close()

@scores_bp.route('/<int:event_id>/export/<string:target>')
@require_role(['admin'])
def export(event_id, target):
    """Placeholder for targeted export (e.g. target='overall' or target='segment_1')"""
    flash(f"Detailed score export for {target.capitalize()} initiated (PDF module integration pending).", "success")
    return redirect(url_for('scores.detail', event_id=event_id))
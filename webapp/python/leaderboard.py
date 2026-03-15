import os
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, send_file, current_app
from webapp.python.database import SessionLocal
from webapp.python.models import Event, Contestant, Score
from webapp.python.services import get_live_leaderboard
from webapp.python.reporting import generate_pdf_report

leaderboard_bp = Blueprint('leaderboard', __name__, url_prefix='/leaderboard')

@leaderboard_bp.route('/')
def index():
    """Main Leaderboard Hub - Shows all events and system-wide score statistics."""
    db = SessionLocal()
    try:
        events = db.query(Event).order_by(Event.last_active.desc()).all()
        total_events = len(events)
        total_contestants = db.query(Contestant).count()
        total_scores = db.query(Score).count()
        
        return render_template('leaderboard_main.html', 
                               events=events,
                               total_events=total_events,
                               total_contestants=total_contestants,
                               total_scores=total_scores)
    finally:
        db.close()

@leaderboard_bp.route('/<int:event_id>')
def detail(event_id):
    """Specific Event Leaderboard - The host for the real-time partial."""
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            flash("Event not found.", "error")
            return redirect(url_for('leaderboard.index'))
            
        leaderboard_data = get_live_leaderboard(db, event_id)
        
        return render_template('leaderboard_detail.html', event=event, leaderboard=leaderboard_data)
    finally:
        db.close()

@leaderboard_bp.route('/api/<int:event_id>')
def api_detail(event_id):
    """Real-Time Data Endpoint - Fetches the live leaderboard for the polling script."""
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            return jsonify({"error": "Event not found"}), 404
            
        leaderboard_data = get_live_leaderboard(db, event_id)
        
        # Serialize data cleanly for Javascript interpretation
        results = []
        for row in leaderboard_data:
            formatted_score = f"{row['score']:.2f}" if event.event_type == "Score-Based" else str(row['score'])
            results.append({
                "rank": row["rank"],
                "candidate_number": row["contestant"].candidate_number or "-",
                "name": row["contestant"].name,
                "category": row["contestant"].gender or "Uncategorized",
                "score": formatted_score
            })
            
        return jsonify({
            "status": event.status,
            "leaderboard": results
        })
    finally:
        db.close()

@leaderboard_bp.route('/<int:event_id>/export')
def export(event_id):
    """Triggers the PDF export and sends it directly to the user's browser."""
    output_dir = os.path.join(current_app.static_folder, 'reports')
    
    success, result = generate_pdf_report(event_id, output_dir)
    
    if success:
        return send_file(result, as_attachment=True)
    else:
        flash(f"Failed to generate report: {result}", "error")
        return redirect(url_for('leaderboard.detail', event_id=event_id))
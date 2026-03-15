import os
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from webapp.python.database import SessionLocal
from webapp.python.models import Event, Contestant, Score

leaderboard_bp = Blueprint('leaderboard', __name__, url_prefix='/leaderboard')

@leaderboard_bp.route('/')
def index():
    """Main Leaderboard Hub - Auto-redirects to the active event scoreboard."""
    db = SessionLocal()
    try:
        active_event = db.query(Event).filter(Event.status == 'Ongoing').order_by(Event.id.desc()).first()
        
        if active_event:
            return redirect(url_for('leaderboard.detail', event_id=active_event.id))
            
        return render_template('leaderboard_main.html')
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
            
        all_active_events = db.query(Event).filter(Event.status == 'Ongoing').all()
        
        return render_template('leaderboard_detail.html', 
                               event=event, 
                               all_active_events=all_active_events)
    finally:
        db.close()

@leaderboard_bp.route('/api/<int:event_id>')
def api_detail(event_id):
    """Real-Time Data Endpoint - Calculates detailed round-by-round scores."""
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            return jsonify({"error": "Event not found"}), 404
            
        all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event_id).all()
        
        # Determine if the Final Segment has started
        final_started = False
        final_seg = next((s for s in event.segments if s.is_final), None)
        if final_seg:
            if final_seg.is_active:
                final_started = True
            elif any(s.segment_id == final_seg.id and s.score_value is not None for s in all_scores):
                final_started = True

        # Generate dynamic segment headers
        segments_info = []
        for seg in sorted(event.segments, key=lambda x: (x.order_index, x.id)):
            segments_info.append({
                "id": seg.id,
                "name": seg.name,
                "is_final": seg.is_final,
                "is_clincher": 'Clincher' in seg.name or 'Tie Breaker' in seg.name,
                "order_index": seg.order_index
            })

        contestants_data = {}
        for c in event.contestants:
            cat = c.gender or "Overall"
            if cat not in contestants_data:
                contestants_data[cat] = []
                
            prelim_score = 0.0
            final_score = 0.0
            segment_scores = {}
            
            for seg in event.segments:
                # Check if contestant is eliminated/not participating in this round
                if not seg.is_contestant_allowed(c.id):
                    segment_scores[seg.id] = '-'
                    continue
                
                if event.event_type == 'Point-Based':
                    # Quiz Bee logic: sum of correct answers * points_per_question
                    pts = sum([seg.points_per_question for s in all_scores if s.contestant_id == c.id and s.segment_id == seg.id and s.is_correct])
                    segment_scores[seg.id] = pts
                    
                    if seg.is_final or 'Clincher' in seg.name or 'Tie Breaker' in seg.name:
                        final_score += pts
                    else:
                        prelim_score += pts
                else:
                    # Pageant logic
                    seg_scores_arr = []
                    for j in event.assigned_judges:
                        j_score = sum([s.score_value for s in all_scores if s.contestant_id == c.id and s.segment_id == seg.id and s.judge_id == j.judge_id and s.score_value is not None])
                        if j_score > 0:
                            seg_scores_arr.append(j_score)
                    
                    avg_seg_score = sum(seg_scores_arr) / len(seg_scores_arr) if seg_scores_arr else 0.0
                    w = seg.percentage_weight or 0.0
                    if w > 1.0: w = w / 100.0  
                    
                    weighted_score = avg_seg_score * w if w > 0 else avg_seg_score
                    segment_scores[seg.id] = weighted_score
                    
                    if seg.is_final:
                        final_score += weighted_score
                    else:
                        prelim_score += weighted_score
                        
            contestants_data[cat].append({
                "candidate_number": c.candidate_number or "-",
                "name": c.name,
                "prelim_score": prelim_score,
                "final_score": final_score,
                "segment_scores": segment_scores
            })
            
        results = {}
        for cat, c_list in contestants_data.items():
            # SMART RANKING: Sort by Final Score if started, otherwise sort by Prelim Score
            c_list.sort(key=lambda x: x['final_score'] if final_started else x['prelim_score'], reverse=True)
            
            for i, c in enumerate(c_list):
                c['rank'] = i + 1
                
                # Format scores beautifully (removes .0 from Quiz Bees, enforces .2f for Pageants)
                if event.event_type == 'Point-Based':
                    c['prelim_score'] = str(int(c['prelim_score'])) if c['prelim_score'].is_integer() else str(c['prelim_score'])
                    c['final_score'] = str(int(c['final_score'])) if c['final_score'].is_integer() else str(c['final_score'])
                    for sid, val in c['segment_scores'].items():
                        if isinstance(val, (int, float)):
                            c['segment_scores'][sid] = str(int(val)) if float(val).is_integer() else str(val)
                else:
                    c['prelim_score'] = f"{c['prelim_score']:.2f}"
                    c['final_score'] = f"{c['final_score']:.2f}"
                    for sid, val in c['segment_scores'].items():
                        if isinstance(val, (int, float)):
                            c['segment_scores'][sid] = f"{val:.2f}"
                
            results[cat] = c_list
            
        return jsonify({
            "status": event.status,
            "event_type": event.event_type,
            "final_started": final_started,
            "segments": segments_info,
            "leaderboard": results
        })
    finally:
        db.close()
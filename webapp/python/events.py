import os
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify
from webapp.python.database import SessionLocal
# Added JudgeProgress to models import
from webapp.python.models import Event, Segment, Criteria, Contestant, User, EventJudge, JudgeProgress, Score
from webapp.python.auth import require_role

events_bp = Blueprint('events', __name__, url_prefix='/events')

UPLOAD_FOLDER = 'webapp/static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@events_bp.route('/create', methods=['GET', 'POST'])
@require_role(['admin'])
def create():
    if request.method == 'POST':
        name = request.form.get('name')
        event_type = request.form.get('event_type')
        category_count = request.form.get('category_count', type=int, default=1)
        
        if not name or not event_type:
            flash("Event name and type are required.", "error")
            return redirect(url_for('events.create'))
            
        db = SessionLocal()
        try:
            new_event = Event(name=name, event_type=event_type, category_count=category_count)
            db.add(new_event)
            db.commit()
            flash(f"Event '{name}' created successfully!", "success")
            return redirect(url_for('events.manage', event_id=new_event.id))
        except Exception as e:
            flash(f"Error creating event: {str(e)}", "error")
        finally:
            db.close()
            
    return render_template('event_create.html')

@events_bp.route('/<int:event_id>/manage', methods=['GET'])
@require_role(['admin'])
def manage(event_id):
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            flash("Event not found.", "error")
            return redirect(url_for('index'))
            
        # FIX: Ensure it correctly checks for 'Score-Based' and strictly fetches judges
        if event.event_type == 'Score-Based' or event.event_type == 'PAGEANT':
            eligible_judges = db.query(User).filter(User.role == 'judge').all()
        else:
            eligible_judges = db.query(User).filter(User.role == 'tabulator').all()
            
        next_numbers = {'Male': 1, 'Female': 1, 'None': 1}
        last_category = "Male"
        
        if event.contestants:
            # Calculate highest number per category
            for cat in next_numbers.keys():
                cat_contestants = [c for c in event.contestants if (c.gender == cat or (not c.gender and cat == 'None'))]
                max_num = max([c.candidate_number for c in cat_contestants if c.candidate_number] or [0])
                next_numbers[cat] = max_num + 1
            
            last_added = event.contestants[-1]
            if last_added.gender:
                last_category = last_added.gender
                
        # --- ADDED: Check judge progress for all segments ---
        segment_progress = {}
        total_judges = len(event.assigned_judges) if event.assigned_judges else 0
        
        for seg in event.segments:
            submitted_count = db.query(JudgeProgress).filter(
                JudgeProgress.segment_id == seg.id, 
                JudgeProgress.is_submitted == True
            ).count()
            segment_progress[seg.id] = {
                'submitted': submitted_count,
                'total': total_judges
            }

        return render_template('event_manage.html', 
                               event=event, 
                               eligible_judges=eligible_judges,
                               next_numbers=next_numbers,
                               last_category=last_category,
                               segment_progress=segment_progress) # Passed to template
    finally:
        db.close()

@events_bp.route('/<int:event_id>/add_segment', methods=['POST'])
@require_role(['admin'])
def add_segment(event_id):
    name = request.form.get('name')
    is_final = request.form.get('is_final') == 'on'
    try:
        percentage_weight = float(request.form.get('percentage_weight') or 0.0)
        # Convert whole number input (e.g. 50%) to decimal (0.5) for the database
        if percentage_weight >= 1.0:
            percentage_weight = percentage_weight / 100.0
    except ValueError:
        percentage_weight = 0.0

    db = SessionLocal()
    try:
        if not name:
            flash("Segment name is required.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        if not is_final:
            if percentage_weight <= 0:
                flash("Percentage weight is required and must be > 0 for non-final segments.", "error")
                return redirect(url_for('events.manage', event_id=event_id))
            
        order = db.query(Segment).filter(Segment.event_id == event_id).count() + 1
        
        new_segment = Segment(event_id=event_id, 
                              name=name, 
                              order_index=order, 
                              is_final=is_final, 
                              percentage_weight=percentage_weight)
        db.add(new_segment)
        db.commit()
        flash("Segment added successfully.", "success")
    except Exception as e:
        flash(f"Error adding segment: {str(e)}", "error")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/add_contestant', methods=['POST'])
@require_role(['admin'])
def add_contestant(event_id):
    name = request.form.get('name')
    number = request.form.get('number')
    category = request.form.get('category')
    
    db = SessionLocal()
    try:
        if not name:
            flash("Contestant name is required.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        existing_name = db.query(Contestant).filter(Contestant.event_id == event_id, Contestant.name == name).first()
        if existing_name:
            flash("Contestant with this name already exists in this event.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        existing_num = db.query(Contestant).filter(Contestant.event_id == event_id, Contestant.gender == category, Contestant.candidate_number == number).first()
        if existing_num and number:
            flash(f"Candidate #{number} already exists in the {category} category.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        image_path = None
        file = request.files.get('image')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            image_path = f"uploads/{filename}"
            
        new_contestant = Contestant(event_id=event_id, name=name, candidate_number=number, gender=category, image_path=image_path)
        db.add(new_contestant)
        db.commit()
        flash("Contestant added successfully.", "success")
    except Exception as e:
        flash(f"Error adding contestant: {str(e)}", "error")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/add_judge', methods=['POST'])
@require_role(['admin'])
def add_judge(event_id):
    judge_id = request.form.get('judge_id')
    is_chairman = request.form.get('is_chairman') == 'on'
    db = SessionLocal()
    try:
        if not judge_id:
            flash("Please select a judge.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        existing = db.query(EventJudge).filter(EventJudge.event_id == event_id, EventJudge.judge_id == judge_id).first()
        if existing:
            flash("Judge is already assigned to this event.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        new_assignment = EventJudge(event_id=event_id, judge_id=judge_id, is_chairman=is_chairman)
        db.add(new_assignment)
        db.commit()
        flash("Judge assigned successfully.", "success")
    except Exception as e:
        flash(f"Error assigning judge: {str(e)}", "error")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/edit_segment/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def edit_segment(event_id, segment_id):
    name = request.form.get('name')
    is_final = request.form.get('is_final') == 'on'
    try:
        percentage_weight = float(request.form.get('percentage_weight') or 0.0)
        if percentage_weight >= 1.0:
            percentage_weight = percentage_weight / 100.0
    except ValueError:
        percentage_weight = 0.0

    db = SessionLocal()
    try:
        seg = db.query(Segment).filter(Segment.id == segment_id, Segment.event_id == event_id).first()
        if not seg:
            flash("Segment not found.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        if name:
            seg.name = name
            
        seg.is_final = is_final
        if not is_final:
            if percentage_weight <= 0:
                flash("Percentage weight is required and must be > 0 for non-final segments.", "error")
                return redirect(url_for('events.manage', event_id=event_id))
            seg.percentage_weight = percentage_weight
        else:
            seg.percentage_weight = 0.0
            
        db.commit()
        flash("Segment updated.", "success")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/add_criteria/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def add_criteria(event_id, segment_id):
    name = request.form.get('name')
    try:
        weight = float(request.form.get('weight') or 1.0)
        max_score = int(request.form.get('max_score') or 10)
        if weight >= 1.0:
            weight = weight / 100.0
    except ValueError:
        weight = 1.0
        max_score = 10
        
    db = SessionLocal()
    try:
        seg = db.query(Segment).filter(Segment.id == segment_id, Segment.event_id == event_id).first()
        if not seg:
            flash("Segment not found.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        if not name:
            flash("Criteria name required.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        new_crit = Criteria(segment_id=segment_id, name=name, weight=weight, max_score=max_score)
        db.add(new_crit)
        db.commit()
        flash(f"Criteria '{name}' added to {seg.name}.", "success")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/edit_criteria/<int:criteria_id>', methods=['POST'])
@require_role(['admin'])
def edit_criteria(event_id, criteria_id):
    name = request.form.get('name')
    try:
        weight = float(request.form.get('weight') or 0.0)
        max_score = int(request.form.get('max_score') or 10)
        if weight >= 1.0:
            weight = weight / 100.0
    except ValueError:
        weight = 0.0
        max_score = 10
        
    db = SessionLocal()
    try:
        crit = db.query(Criteria).filter(Criteria.id == criteria_id).first()
        if not crit:
            flash("Criteria not found.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        if name:
            crit.name = name
        if weight > 0:
            crit.weight = weight
        if max_score > 0:
            crit.max_score = max_score
            
        db.commit()
        flash("Criteria updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating criteria: {str(e)}", "error")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/delete_criteria/<int:criteria_id>', methods=['POST'])
@require_role(['admin'])
def delete_criteria(event_id, criteria_id):
    db = SessionLocal()
    try:
        crit = db.query(Criteria).filter(Criteria.id == criteria_id).first()
        if crit:
            db.delete(crit)
            db.commit()
            flash("Criteria deleted.", "success")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/delete_segment/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def delete_segment(event_id, segment_id):
    db = SessionLocal()
    try:
        seg = db.query(Segment).filter(Segment.id == segment_id, Segment.event_id == event_id).first()
        if seg:
            db.delete(seg)
            db.commit()
            flash("Segment deleted.", "success")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/toggle_segment/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def toggle_segment(event_id, segment_id):
    db = SessionLocal()
    try:
        seg = db.query(Segment).filter(Segment.id == segment_id, Segment.event_id == event_id).first()
        if not seg:
            flash("Segment not found.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        if not seg.is_active and seg.event.status != "Ongoing":
            flash("You cannot activate a segment while the Event is deactivated.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        seg.is_active = not seg.is_active
        
        if seg.is_active:
            other_segs = db.query(Segment).filter(Segment.event_id == event_id, Segment.id != segment_id).all()
            for other in other_segs:
                other.is_active = False
                
        db.commit()
        if seg.is_active:
            flash(f"Segment '{seg.name}' is now ACTIVE.", "success")
        else:
            flash(f"Segment '{seg.name}' has been deactivated.", "success")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/edit_contestant/<int:contestant_id>', methods=['POST'])
@require_role(['admin'])
def edit_contestant(event_id, contestant_id):
    name = request.form.get('name')
    number = request.form.get('number')
    category = request.form.get('category')
    
    db = SessionLocal()
    try:
        con = db.query(Contestant).filter(Contestant.id == contestant_id, Contestant.event_id == event_id).first()
        if not con:
            flash("Contestant not found.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        if not name:
            flash("Contestant name is required.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        existing_name = db.query(Contestant).filter(Contestant.event_id == event_id, Contestant.name == name, Contestant.id != contestant_id).first()
        if existing_name:
            flash("Contestant with this name already exists in this event.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        existing_num = db.query(Contestant).filter(Contestant.event_id == event_id, Contestant.gender == category, Contestant.candidate_number == number, Contestant.id != contestant_id).first()
        if existing_num and number:
            flash(f"Candidate #{number} already exists in the {category} category.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        con.name = name
        con.candidate_number = number
        con.gender = category
        
        file = request.files.get('image')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            con.image_path = f"uploads/{filename}"
            
        db.commit()
        flash("Contestant updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating contestant: {str(e)}", "error")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/delete_contestant/<int:contestant_id>', methods=['POST'])
@require_role(['admin'])
def delete_contestant(event_id, contestant_id):
    db = SessionLocal()
    try:
        con = db.query(Contestant).filter(Contestant.id == contestant_id, Contestant.event_id == event_id).first()
        if con:
            db.delete(con)
            db.commit()
            flash("Contestant deleted.", "success")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/edit_judge/<int:assignment_id>', methods=['POST'])
@require_role(['admin'])
def edit_judge(event_id, assignment_id):
    is_chairman = request.form.get('is_chairman') == 'on'
    db = SessionLocal()
    try:
        assignment = db.query(EventJudge).filter(EventJudge.id == assignment_id, EventJudge.event_id == event_id).first()
        if assignment:
            assignment.is_chairman = is_chairman
            db.commit()
            flash("Judge assignment updated.", "success")
        else:
            flash("Judge assignment not found.", "error")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/delete_judge/<int:assignment_id>', methods=['POST'])
@require_role(['admin'])
def delete_judge(event_id, assignment_id):
    db = SessionLocal()
    try:
        assignment = db.query(EventJudge).filter(EventJudge.id == assignment_id, EventJudge.event_id == event_id).first()
        if assignment:
            db.delete(assignment)
            db.commit()
            flash("Judge assignment removed.", "success")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/quick_create_judge', methods=['POST'])
@require_role(['admin'])
def quick_create_judge(event_id):
    from webapp.python.auth import hash_password
    username = request.form.get('username')
    name = request.form.get('name')
    password = request.form.get('password')
    role = request.form.get('role', 'judge')
    
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            flash("Username already exists in the system.", "error")
        else:
            hashed_pwd = hash_password(password)
            new_user = User(username=username, name=name, password_hash=hashed_pwd, role=role)
            db.add(new_user)
            db.flush() 
            
            # UPDATED DB LOGIC CHECK
            if role == 'judge':
                new_assignment = EventJudge(event_id=event_id, judge_id=new_user.id, is_chairman=False)
                db.add(new_assignment)
                
            db.commit()
            flash(f"Account '{username}' created successfully and automatically assigned!", "success")
    except Exception as e:
        flash(f"Error creating user: {str(e)}", "error")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/<int:event_id>/launch', methods=['POST'])
@require_role(['admin'])
def launch(event_id):
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            flash("Event not found.", "error")
            return redirect(url_for('index'))
            
        if event.status == "Ongoing":
            event.is_locked = False
            event.status = "Setup"
            for s in event.segments:
                s.is_active = False
            flash(f"Event '{event.name}' has been deactivated and paused.", "success")
        else:
            event.is_locked = True
            event.status = "Ongoing"
            event.last_active = datetime.now()
            
            if event.segments:
                has_active = any(s.is_active for s in event.segments)
                if not has_active:
                    first_seg = min(event.segments, key=lambda s: s.order_index or 999)
                    first_seg.is_active = True
                    
            flash(f"Event '{event.name}' has been launched!", "success")
            
        db.commit()
    except Exception as e:
        flash(f"Error toggling event status: {str(e)}", "error")
    finally:
        db.close()
    return redirect(url_for('events.manage', event_id=event_id))

@events_bp.route('/api/<int:event_id>/status')
def api_event_status(event_id):
    """Lightweight API endpoint for real-time frontend polling."""
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            return jsonify({'error': 'Not found'}), 404
            
        active_segment = next((s for s in event.segments if s.is_active), None)
        total_judges = len(event.assigned_judges)
        
        progress = {}
        for seg in event.segments:
            submitted = db.query(JudgeProgress).filter(
                JudgeProgress.segment_id == seg.id,
                JudgeProgress.is_submitted == True
            ).count()
            progress[seg.id] = {
                'submitted': submitted,
                'total': total_judges,
                'is_active': seg.is_active
            }
            
        return jsonify({
            'status': event.status,
            'active_segment_id': active_segment.id if active_segment else None,
            'progress': progress
        })
    finally:
        db.close()

@events_bp.route('/<int:event_id>/pb_add_segment', methods=['POST'])
@require_role(['admin'])
def pb_add_segment(event_id):
    """Adds a Quiz Bee Segment (Round)."""
    db = SessionLocal()
    try:
        new_segment = Segment(
            event_id=event_id,
            name=request.form.get('name'),
            order_index=request.form.get('order_index'),
            points_per_question=request.form.get('points_per_question'),
            total_questions=request.form.get('total_questions'),
            qualifying_count=int(request.form.get('qualifying_count') or 0),
            is_final=request.form.get('is_final') == 'on'
        )
        db.add(new_segment)
        db.commit()
        flash('Quiz Bee Segment Added.', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/pb_add_contestant', methods=['POST'])
@require_role(['admin'])
def pb_add_contestant(event_id):
    """Adds a Contestant/Team and strictly assigns their Tabulator."""
    db = SessionLocal()
    try:
        new_contestant = Contestant(
            event_id=event_id,
            candidate_number=request.form.get('candidate_number'),
            name=request.form.get('name'),
            gender=request.form.get('gender'), # Used as Category if needed
            assigned_judge_id=request.form.get('assigned_judge_id')
        )
        db.add(new_contestant)
        db.commit()
        flash('Team & Tabulator Linked.', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/api/<int:event_id>/pb_mission_control')
@require_role(['admin'])
def pb_api_mission_control(event_id):
    """Real-time JSON API that powers the Live Scoreboard in Mission Control."""
    db = SessionLocal()
    try:
        from flask import jsonify
        event = db.query(Event).filter(Event.id == event_id).first()
        active_segment = next((s for s in event.segments if s.is_active), None)
        
        if not active_segment:
            return jsonify({"status": "no_active_segment"})
            
        all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event_id).all()
        
        # Determine Cumulative vs Final Mode based on your strict Hybrid Rules
        show_cumulative = True
        is_hybrid_final = active_segment.is_final
        # THE FIX: Explicitly check for 'Clincher' so it starts at 0!
        if 'Tie Breaker' in active_segment.name or 'Clincher' in active_segment.name or is_hybrid_final:
            show_cumulative = False
            
        previous_segments = []
        if show_cumulative:
            previous_segments = [s for s in event.segments if s.order_index < active_segment.order_index and 'Tie Breaker' not in s.name]

        live_scores = []
        all_finished = True
        
        for c in event.contestants:
            if not active_segment.is_contestant_allowed(c.id):
                continue
                
            # Current Segment Scores
            c_scores = [s for s in all_scores if s.contestant_id == c.id and s.segment_id == active_segment.id and s.is_correct]
            current_points = sum([active_segment.points_per_question for s in c_scores])
            answered_count = len([s for s in all_scores if s.contestant_id == c.id and s.segment_id == active_segment.id])
            
            if answered_count < active_segment.total_questions:
                all_finished = False

            # Calculation Mode
            main_score_for_sorting = current_points
            display_score = current_points
            
            if show_cumulative:
                past_points = 0
                for prev_seg in previous_segments:
                    past_points += sum([prev_seg.points_per_question for s in all_scores if s.contestant_id == c.id and s.segment_id == prev_seg.id and s.is_correct])
                main_score_for_sorting = past_points + current_points
                display_score = main_score_for_sorting

            live_scores.append({
                'contestant_id': c.id,
                'name': c.name,
                'progress_pct': (answered_count / active_segment.total_questions * 100) if active_segment.total_questions > 0 else 0,
                'answered': answered_count,
                'total_q': active_segment.total_questions,
                'score': main_score_for_sorting,
                'display_score': display_score
            })
            
        # Sort and apply Smart Colors
        live_scores.sort(key=lambda x: x['score'], reverse=True)
        
        q_count = active_segment.qualifying_count or 0
        for i, stat in enumerate(live_scores):
            stat['rank'] = i + 1
            stat['row_class'] = ""
            
            if 'Clincher' in active_segment.name:
                if stat['score'] > 0 and stat['score'] == live_scores[0]['score']:
                    stat['row_class'] = "table-warning" # Gold
                elif stat['answered'] > 0 and stat['score'] < live_scores[0]['score']:
                    stat['row_class'] = "table-danger" # Red
            else:
                if q_count > 0 and stat['rank'] <= q_count:
                    stat['row_class'] = "table-success" # Green

        return jsonify({
            "status": "active",
            "segment_name": active_segment.name,
            "show_cumulative": show_cumulative,
            "q_count": q_count,
            "all_finished": all_finished,
            "live_scores": live_scores
        })
    finally:
        db.close()


@events_bp.route('/pb_evaluate/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def pb_evaluate_segment(segment_id):
    """The Brain: Handles cutoffs, recursive tie-breakers, and clinchers."""
    db = SessionLocal()
    from itertools import groupby
    import re
    try:
        segment = db.query(Segment).filter(Segment.id == segment_id).first()
        event = db.query(Event).filter(Event.id == segment.event_id).first()
        all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event.id).all()
        
        cutoff = segment.qualifying_count
        if cutoff == 0 and 'Clincher' not in segment.name:
            pass # Proceed normally without cutoff
            
        standings = []
        for c in event.contestants:
            if not segment.is_contestant_allowed(c.id): continue
            
            score_val = 0
            if 'Tie Breaker' in segment.name or 'Clincher' in segment.name or segment.is_final:
                score_val = sum([segment.points_per_question for s in all_scores if s.contestant_id == c.id and s.segment_id == segment.id and s.is_correct])
            else:
                # Cumulative calculation up to this segment
                for s in event.segments:
                    if s.order_index <= segment.order_index and 'Tie Breaker' not in s.name:
                        score_val += sum([s.points_per_question for sc in all_scores if sc.contestant_id == c.id and sc.segment_id == s.id and sc.is_correct])
                        
            standings.append({'contestant': c, 'score': score_val})
            
        standings.sort(key=lambda x: x['score'], reverse=True)

        # 1. CLINCHER TIE-BREAKER RECURSION
        if 'Clincher' in segment.name:
            ties_created = 0
            for score, group in groupby(standings, key=lambda x: x['score']):
                tied_group = list(group)
                if len(tied_group) > 1:
                    tied_ids = ",".join([str(item['contestant'].id) for item in tied_group])
                    
                    if segment.participating_contestants and set(tied_ids.split(',')) == set(segment.participating_contestants.split(',')) and len(standings) == len(tied_group):
                         flash("⚠️ TIE NOT BROKEN! All contestants scored the same. Add a question (+1 Q).", 'error')
                         return redirect(url_for('events.manage', event_id=event.id))

                    match = re.search(r'Clincher (\d+)', segment.name)
                    next_num = (int(match.group(1)) + 1) if match else 2
                    
                    tb_segment = Segment(
                        event_id=event.id, order_index=segment.order_index, name=f"Clincher {next_num}",
                        points_per_question=1, total_questions=1, participating_contestants=tied_ids,
                        # THE FIX: Inherit the is_final status from the parent so points are grouped correctly
                        qualifying_count=0, is_active=True, is_final=segment.is_final 
                    )
                    db.add(tb_segment)
                    ties_created += 1
            
            segment.is_active = False # Lock current clincher
            db.commit()
            
            if ties_created > 0:
                flash(f"Created & Auto-Started {ties_created} new Clincher round(s) for remaining ties.", "warning")
                return redirect(url_for('events.manage', event_id=event.id))
            else:
                # NEW AUTO-ACTIVATE LOGIC FOR CLINCHERS
                next_seg = db.query(Segment).filter(Segment.event_id == event.id, Segment.order_index > segment.order_index).order_by(Segment.order_index.asc()).first()
                if next_seg:
                    # APPEND clincher winners to next round!
                    existing = next_seg.participating_contestants.split(',') if next_seg.participating_contestants else []
                    new_ids = [str(s['contestant'].id) for s in standings]
                    next_seg.participating_contestants = ",".join(list(set(existing + new_ids)))
                    next_seg.is_active = True
                    db.commit()
                    flash(f"Evaluation Complete. All ties broken! {next_seg.name} automatically started.", "success")
                else:
                    db.commit()
                    flash("Evaluation Complete. All ties broken! Final Ranking is set.", "success")
                return redirect(url_for('events.manage', event_id=event.id))

        # 2. HYBRID FINAL TIES
        if segment.is_final:
            for i in range(len(standings) - 1):
                if standings[i]['score'] == standings[i+1]['score']:
                    tied_score = standings[i]['score']
                    tied_group = [s['contestant'] for s in standings if s['score'] == tied_score]
                    ids_string = ",".join([str(s.id) for s in tied_group])
                    
                    tb_seg = Segment(
                        event_id=event.id, order_index=segment.order_index, name="Clincher 1",
                        points_per_question=1, total_questions=1, participating_contestants=ids_string,
                        # THE FIX: Explicitly mark Final Clinchers as Final Rounds
                        qualifying_count=0, is_active=True, is_final=True 
                    )
                    db.add(tb_seg)
                    segment.is_active = False
                    db.commit()
                    flash(f"⚠️ Tie detected in Final. 'Clincher 1' created and started.", 'warning')
                    return redirect(url_for('events.manage', event_id=event.id))
            
            segment.is_active = False
            db.commit()
            flash(f"🏆 FINAL RESULTS OFFICIAL.", 'success')
            return redirect(url_for('events.manage', event_id=event.id))

        # 3. STANDARD ROUND CUTOFFS
        if len(standings) > cutoff and cutoff > 0:
            boundary_score = standings[cutoff - 1]['score']
            next_score = standings[cutoff]['score']
            
            if boundary_score == next_score:
                 if 'Tie Breaker' in segment.name:
                     flash("Tie still exists. Add question.", 'error')
                     return redirect(url_for('events.manage', event_id=event.id))
                 
                 tied_schools = [s['contestant'] for s in standings if s['score'] == boundary_score]
                 ids_string = ",".join([str(s.id) for s in tied_schools])
                 clean_winners = [s['contestant'] for s in standings if s['score'] > boundary_score]
                 slots = cutoff - len(clean_winners)
                 
                 tb_seg = Segment(
                     event_id=event.id, order_index=segment.order_index, name=f"Tie Breaker ({segment.name})",
                     points_per_question=1, total_questions=1, participating_contestants=ids_string,
                     qualifying_count=slots, is_active=True, is_final=segment.is_final # Auto-activate!
                 )
                 db.add(tb_seg)
                 
                 # ---- THE FIX: SECURE CLEAN WINNERS INTO THE NEXT ROUND IMMEDIATELY ----
                 if clean_winners:
                     next_seg = db.query(Segment).filter(Segment.event_id == event.id, Segment.order_index > segment.order_index).order_by(Segment.order_index.asc()).first()
                     if next_seg:
                         existing = next_seg.participating_contestants.split(',') if next_seg.participating_contestants else []
                         new_ids = [str(s.id) for s in clean_winners]
                         next_seg.participating_contestants = ",".join(list(set(existing + new_ids)))
                 
                 segment.is_active = False
                 db.commit()
                 flash(f"Tie detected! Clean winners secured. Tie Breaker for remaining slots created & started.", 'warning')
                 return redirect(url_for('events.manage', event_id=event.id))
                 
            final_advancing = [s['contestant'] for s in standings[:cutoff]]
        else:
            final_advancing = [s['contestant'] for s in standings]

        # Advance logic (NO TIES DETECTED or TB round evaluating clean winners)
        segment.is_active = False # Safely lock the current round
        
        next_seg = db.query(Segment).filter(Segment.event_id == event.id, Segment.order_index > segment.order_index).order_by(Segment.order_index.asc()).first()
        
        if next_seg:
            # THE FIX: Append rather than overwrite!
            existing = next_seg.participating_contestants.split(',') if next_seg.participating_contestants else []
            new_ids = [str(s.id) for s in final_advancing]
            next_seg.participating_contestants = ",".join(list(set(existing + new_ids)))
            next_seg.is_active = True # AUTO-ACTIVATE next round
            db.commit()
            flash(f'Evaluation complete. {next_seg.name} automatically started!', 'success')
        else:
            db.commit()
            flash('Evaluation complete. Tournament finished!', 'info')
            
        return redirect(url_for('events.manage', event_id=event.id))
    finally:
        db.close()

@events_bp.route('/pb_add_question/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def pb_add_question(segment_id):
    """Sudden death: Adds 1 extra question to the live segment."""
    db = SessionLocal()
    try:
        segment = db.query(Segment).filter(Segment.id == segment_id).first()
        segment.total_questions += 1
        db.commit()
        flash(f'+1 Question added to {segment.name}!', 'success')
        return redirect(url_for('events.manage', event_id=segment.event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/pb_edit_segment/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def pb_edit_segment(event_id, segment_id):
    """Updates an existing Quiz Bee Segment/Round."""
    db = SessionLocal()
    try:
        segment = db.query(Segment).filter(Segment.id == segment_id).first()
        if segment:
            segment.name = request.form.get('name')
            segment.order_index = request.form.get('order_index')
            segment.points_per_question = request.form.get('points_per_question')
            segment.total_questions = request.form.get('total_questions')
            segment.qualifying_count = int(request.form.get('qualifying_count') or 0)
            segment.is_final = request.form.get('is_final') == 'on'
            db.commit() # Using pure SQLAlchemy commit to prevent session error!
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/pb_edit_contestant/<int:contestant_id>', methods=['POST'])
@require_role(['admin'])
def pb_edit_contestant(event_id, contestant_id):
    """Updates an existing Team and Tabulator assignment."""
    db = SessionLocal()
    try:
        contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
        if contestant:
            contestant.candidate_number = request.form.get('candidate_number')
            contestant.name = request.form.get('name')
            contestant.assigned_judge_id = request.form.get('assigned_judge_id')
            db.commit() # Using pure SQLAlchemy commit
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()
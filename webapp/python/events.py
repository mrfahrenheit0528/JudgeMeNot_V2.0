import os
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify
from webapp.python.database import SessionLocal
# Added JudgeProgress to models import
from webapp.python.models import Event, Segment, Criteria, Contestant, User, EventJudge, JudgeProgress
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
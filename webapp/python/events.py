import os
import uuid
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app
from werkzeug.utils import secure_filename
from webapp.python.database import SessionLocal
from webapp.python.models import Event, Segment, Criteria, Contestant, User, EventJudge, Score, JudgeProgress
from webapp.python.auth import require_role, hash_password
from webapp.python.services import get_live_leaderboard

events_bp = Blueprint('events', __name__, url_prefix='/events')

@events_bp.route('/create', methods=['GET', 'POST'])
@require_role(['admin'])
def create():
    if request.method == 'POST':
        name = request.form.get('name')
        event_type = request.form.get('event_type')
        category_count = int(request.form.get('category_count') or 1)
        
        db = SessionLocal()
        try:
            new_event = Event(name=name, event_type=event_type, status='Setup', category_count=category_count)
            db.add(new_event)
            db.commit()
            flash(f'Event "{name}" created successfully!', 'success')
            return redirect(url_for('events.manage', event_id=new_event.id))
        except Exception as e:
            flash(f'Error creating event: {str(e)}', 'error')
            return redirect(url_for('events.create'))
        finally:
            db.close()
            
    return render_template('event_create.html')

@events_bp.route('/<int:event_id>/manage')
@require_role(['admin'])
def manage(event_id):
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            flash('Event not found.', 'error')
            return redirect(url_for('index'))
            
        eligible_judges = db.query(User).filter(User.role.in_(['judge', 'tabulator'])).all()
        
        # Calculate Next Available Candidate Numbers
        next_numbers = {}
        if event.category_count == 2:
            males = [c.candidate_number for c in event.contestants if c.gender == 'Male' and c.candidate_number]
            females = [c.candidate_number for c in event.contestants if c.gender == 'Female' and c.candidate_number]
            next_numbers['Male'] = max(males) + 1 if males else 1
            next_numbers['Female'] = max(females) + 1 if females else 1
        else:
            all_nums = [c.candidate_number for c in event.contestants if c.candidate_number]
            next_numbers['None'] = max(all_nums) + 1 if all_nums else 1
            
        last_added = db.query(Contestant).filter(Contestant.event_id == event_id).order_by(Contestant.id.desc()).first()
        last_category = last_added.gender if last_added else 'Male'

        # Live Progress Tracking for Score-Based Events
        segment_progress = {}
        if event.event_type == 'Score-Based':
            assigned_judges = [j.judge_id for j in event.assigned_judges]
            total_judges = len(assigned_judges)
            for seg in event.segments:
                submitted_count = db.query(JudgeProgress).filter(
                    JudgeProgress.segment_id == seg.id,
                    JudgeProgress.is_submitted == True
                ).count()
                segment_progress[seg.id] = {
                    'total': total_judges,
                    'submitted': submitted_count
                }

        return render_template('event_manage.html', 
                               event=event, 
                               eligible_judges=eligible_judges,
                               next_numbers=next_numbers,
                               last_category=last_category,
                               segment_progress=segment_progress)
    finally:
        db.close()

# =====================================================================
# CORE EVENT TOGGLES & LAUNCHERS
# =====================================================================
@events_bp.route('/<int:event_id>/launch', methods=['POST'])
@require_role(['admin'])
def launch(event_id):
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if event:
            if event.status == 'Ongoing':
                event.status = 'Paused'
                for s in event.segments:
                    s.is_active = False
                flash(f'Event {event.name} has been paused.', 'warning')
            else:
                event.status = 'Ongoing'
                flash(f'Event {event.name} is now LIVE!', 'success')
            db.commit()
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/toggle_segment/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def toggle_segment(event_id, segment_id):
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        segment = db.query(Segment).filter(Segment.id == segment_id).first()
        
        if segment:
            if not segment.is_active:
                for s in event.segments:
                    s.is_active = False
                segment.is_active = True
                
                # --- THE FIX: STRICT TOP N VAULT ENGINE ---
                # This explicitly locks only the Top N contestants into the database
                qualifying_count = getattr(segment, 'qualifying_count', 0) or 0
                
                if event.event_type == 'Score-Based' and segment.is_final and qualifying_count > 0:
                    lb = get_live_leaderboard(db, event_id)
                    
                    categories = ['Male', 'Female'] if event.category_count == 2 else ['Overall']
                    qualifiers = []
                    
                    for cat in categories:
                        cat_list = [r for r in lb if (event.category_count == 1 or r['contestant'].gender == cat)]
                        cat_list.sort(key=lambda x: x['prelim_score'], reverse=True)
                        
                        top_n = cat_list[:qualifying_count]
                        qualifiers.extend([str(r['contestant'].id) for r in top_n])
                        
                    # Vault the allowed IDs securely into the segment
                    segment.participating_contestants = ",".join(qualifiers)
                    
            else:
                segment.is_active = False
            
            db.commit()
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

# =====================================================================
# SEGMENTS (ROUNDS) MANAGEMENT
# =====================================================================
@events_bp.route('/<int:event_id>/add_segment', methods=['POST'])
@require_role(['admin'])
def add_segment(event_id):
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        name = request.form.get('name')
        percentage_weight = request.form.get('percentage_weight')
        is_final = request.form.get('is_final') == 'on'
        qualifying_count = int(request.form.get('qualifying_count') or 0)
        
        weight_val = float(percentage_weight) / 100.0 if percentage_weight else 0.0
        max_order = max([s.order_index for s in event.segments]) if event.segments else 0
        
        new_segment = Segment(
            event_id=event.id, name=name, order_index=max_order + 1,
            percentage_weight=weight_val, is_final=is_final, qualifying_count=qualifying_count
        )
        db.add(new_segment)
        db.commit()
        flash('Segment added successfully!', 'success')
        return redirect(url_for('events.manage', event_id=event.id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/edit_segment/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def edit_segment(event_id, segment_id):
    db = SessionLocal()
    try:
        segment = db.query(Segment).filter(Segment.id == segment_id).first()
        if segment:
            segment.name = request.form.get('name')
            is_final = request.form.get('is_final') == 'on'
            
            if is_final:
                segment.is_final = True
                segment.percentage_weight = 0.0
                segment.qualifying_count = int(request.form.get('qualifying_count') or 0)
            else:
                segment.is_final = False
                weight = request.form.get('percentage_weight')
                segment.percentage_weight = float(weight) / 100.0 if weight else 0.0
                segment.qualifying_count = 0
                
            db.commit()
            flash('Segment updated successfully!', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/delete_segment/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def delete_segment(event_id, segment_id):
    db = SessionLocal()
    try:
        segment = db.query(Segment).filter(Segment.id == segment_id).first()
        if segment:
            db.delete(segment)
            db.commit()
            flash('Segment deleted.', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

# =====================================================================
# CRITERIA MANAGEMENT
# =====================================================================
@events_bp.route('/<int:event_id>/add_criteria/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def add_criteria(event_id, segment_id):
    db = SessionLocal()
    try:
        name = request.form.get('name')
        weight = float(request.form.get('weight')) / 100.0
        max_score = int(request.form.get('max_score'))
        
        new_criteria = Criteria(segment_id=segment_id, name=name, weight=weight, max_score=max_score)
        db.add(new_criteria)
        db.commit()
        flash('Criteria added!', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/edit_criteria/<int:criteria_id>', methods=['POST'])
@require_role(['admin'])
def edit_criteria(event_id, criteria_id):
    db = SessionLocal()
    try:
        crit = db.query(Criteria).filter(Criteria.id == criteria_id).first()
        if crit:
            crit.name = request.form.get('name')
            crit.weight = float(request.form.get('weight')) / 100.0
            crit.max_score = int(request.form.get('max_score'))
            db.commit()
            flash('Criteria updated!', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/delete_criteria/<int:criteria_id>', methods=['POST'])
@require_role(['admin'])
def delete_criteria(event_id, criteria_id):
    db = SessionLocal()
    try:
        crit = db.query(Criteria).filter(Criteria.id == criteria_id).first()
        if crit:
            db.delete(crit)
            db.commit()
            flash('Criteria deleted.', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

# =====================================================================
# CONTESTANTS MANAGEMENT
# =====================================================================
@events_bp.route('/<int:event_id>/add_contestant', methods=['POST'])
@require_role(['admin'])
def add_contestant(event_id):
    db = SessionLocal()
    try:
        number = request.form.get('number')
        name = request.form.get('name')
        category = request.form.get('category')
        
        image_file = request.files.get('image')
        image_path = None
        
        if image_file and image_file.filename != '':
            filename = secure_filename(f"{uuid.uuid4()}_{image_file.filename}")
            upload_folder = os.path.join(current_app.root_path, 'webapp/static/uploads/contestants')
            os.makedirs(upload_folder, exist_ok=True)
            image_file.save(os.path.join(upload_folder, filename))
            image_path = f"uploads/contestants/{filename}"
            
        new_contestant = Contestant(
            event_id=event_id, candidate_number=number, name=name,
            gender=category if category != 'None' else None, image_path=image_path
        )
        db.add(new_contestant)
        db.commit()
        flash('Contestant added!', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/edit_contestant/<int:contestant_id>', methods=['POST'])
@require_role(['admin'])
def edit_contestant(event_id, contestant_id):
    db = SessionLocal()
    try:
        contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
        if contestant:
            contestant.candidate_number = request.form.get('number')
            contestant.name = request.form.get('name')
            cat = request.form.get('category')
            contestant.gender = cat if cat != 'None' else None
            
            image_file = request.files.get('image')
            if image_file and image_file.filename != '':
                filename = secure_filename(f"{uuid.uuid4()}_{image_file.filename}")
                upload_folder = os.path.join(current_app.root_path, 'webapp/static/uploads/contestants')
                os.makedirs(upload_folder, exist_ok=True)
                image_file.save(os.path.join(upload_folder, filename))
                contestant.image_path = f"uploads/contestants/{filename}"
                
            db.commit()
            flash('Contestant updated!', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/delete_contestant/<int:contestant_id>', methods=['POST'])
@require_role(['admin'])
def delete_contestant(event_id, contestant_id):
    db = SessionLocal()
    try:
        contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
        if contestant:
            db.delete(contestant)
            db.commit()
            flash('Contestant removed.', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

# =====================================================================
# JUDGE ASSIGNMENTS
# =====================================================================
@events_bp.route('/<int:event_id>/add_judge', methods=['POST'])
@require_role(['admin'])
def add_judge(event_id):
    db = SessionLocal()
    try:
        judge_id = request.form.get('judge_id')
        is_chairman = request.form.get('is_chairman') == 'on'
        
        new_assignment = EventJudge(event_id=event_id, judge_id=judge_id, is_chairman=is_chairman)
        db.add(new_assignment)
        db.commit()
        flash('Judge assigned successfully!', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/edit_judge/<int:assignment_id>', methods=['POST'])
@require_role(['admin'])
def edit_judge(event_id, assignment_id):
    db = SessionLocal()
    try:
        assignment = db.query(EventJudge).filter(EventJudge.id == assignment_id).first()
        if assignment:
            assignment.is_chairman = request.form.get('is_chairman') == 'on'
            db.commit()
            flash('Judge settings updated!', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/delete_judge/<int:assignment_id>', methods=['POST'])
@require_role(['admin'])
def delete_judge(event_id, assignment_id):
    db = SessionLocal()
    try:
        assignment = db.query(EventJudge).filter(EventJudge.id == assignment_id).first()
        if assignment:
            db.delete(assignment)
            db.commit()
            flash('Judge removed from event.', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/quick_create_judge', methods=['POST'])
@require_role(['admin'])
def quick_create_judge(event_id):
    db = SessionLocal()
    try:
        name = request.form.get('name')
        username = request.form.get('username')
        password = request.form.get('password')
        
        if db.query(User).filter(User.username == username).first():
            flash("Username already exists.", "error")
            return redirect(url_for('events.manage', event_id=event_id))
            
        hashed_pw = hash_password(password)
        new_user = User(username=username, name=name, password_hash=hashed_pw, role='judge')
        db.add(new_user)
        db.commit()
        
        new_assignment = EventJudge(event_id=event_id, judge_id=new_user.id, is_chairman=False)
        db.add(new_assignment)
        db.commit()
        
        flash(f"Judge '{name}' created and assigned!", "success")
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

# =====================================================================
# API / LIVE POLLING ENDPOINTS
# =====================================================================
@events_bp.route('/api/<int:event_id>/status')
@require_role(['admin'])
def api_event_status(event_id):
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            return jsonify({"error": "Event not found"}), 404
            
        active_segment = next((s for s in event.segments if s.is_active), None)
        progress_data = {}
        
        if event.event_type == 'Score-Based':
            assigned_judges = [j.judge_id for j in event.assigned_judges]
            total_judges = len(assigned_judges)
            for seg in event.segments:
                submitted_count = db.query(JudgeProgress).filter(
                    JudgeProgress.segment_id == seg.id,
                    JudgeProgress.is_submitted == True
                ).count()
                progress_data[seg.id] = {
                    'total': total_judges,
                    'submitted': submitted_count
                }
                
        return jsonify({
            "status": event.status,
            "active_segment_id": active_segment.id if active_segment else None,
            "progress": progress_data
        })
    finally:
        db.close()

# =====================================================================
# POINT-BASED (QUIZ BEE) HUB & EVALUATION
# =====================================================================
@events_bp.route('/api/<int:event_id>/pb_mission_control')
@require_role(['admin'])
def pb_mission_control(event_id):
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        active_seg = next((s for s in event.segments if s.is_active), None)
        
        if not active_seg:
            return jsonify({'status': 'no_active_segment'})
            
        all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event_id).all()
        
        show_cumulative = True
        is_hybrid_final = active_seg.is_final
        if 'Tie Breaker' in active_seg.name or 'Clincher' in active_seg.name or is_hybrid_final:
            show_cumulative = False
            
        previous_segments = []
        if show_cumulative:
            previous_segments = [s for s in event.segments if s.order_index < active_seg.order_index and 'Tie Breaker' not in s.name]

        live_scores = []
        all_finished = True 

        for c in event.contestants:
            if not active_seg.is_contestant_allowed(c.id):
                continue
                
            current_correct = len([s for s in all_scores if s.segment_id == active_seg.id and s.contestant_id == c.id and s.is_correct])
            current_answered = len([s for s in all_scores if s.segment_id == active_seg.id and s.contestant_id == c.id])
            
            progress_pct = (current_answered / active_seg.total_questions * 100) if active_seg.total_questions > 0 else 0
            if progress_pct < 100:
                all_finished = False 

            current_points = current_correct * active_seg.points_per_question
            
            cum_points = 0
            if show_cumulative:
                for ps in previous_segments:
                    p_correct = len([s for s in all_scores if s.segment_id == ps.id and s.contestant_id == c.id and s.is_correct])
                    cum_points += p_correct * ps.points_per_question
                    
            total_points = cum_points + current_points
            
            live_scores.append({
                'id': c.id,
                'name': c.name,
                'answered': current_answered,
                'total_q': active_seg.total_questions,
                'progress_pct': min(progress_pct, 100),
                'score': total_points,
                'display_score': f"{total_points:g}"
            })
            
        live_scores.sort(key=lambda x: x['score'], reverse=True)
        
        for idx, item in enumerate(live_scores):
            item['rank'] = idx + 1
            item['row_class'] = ''
            if idx == 0: item['row_class'] = 'table-warning fw-bold'
            elif active_seg.qualifying_count > 0 and idx < active_seg.qualifying_count: item['row_class'] = 'table-success'
            elif active_seg.qualifying_count > 0: item['row_class'] = 'table-danger opacity-75'
            
        return jsonify({
            'status': 'ok',
            'segment_name': active_seg.name,
            'show_cumulative': show_cumulative,
            'live_scores': live_scores,
            'q_count': active_seg.qualifying_count,
            'all_finished': all_finished 
        })
    finally:
        db.close()

@events_bp.route('/pb_evaluate/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def pb_evaluate_segment(segment_id):
    db = SessionLocal()
    from itertools import groupby
    import re
    try:
        segment = db.query(Segment).filter(Segment.id == segment_id).first()
        event = db.query(Event).filter(Event.id == segment.event_id).first()
        all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event.id).all()
        
        cutoff = segment.qualifying_count
        if cutoff == 0 and 'Clincher' not in segment.name:
            pass 
            
        standings = []
        for c in event.contestants:
            if not segment.is_contestant_allowed(c.id): continue
            
            score_val = 0
            if 'Tie Breaker' in segment.name or 'Clincher' in segment.name or segment.is_final:
                score_val = sum([segment.points_per_question for s in all_scores if s.contestant_id == c.id and s.segment_id == segment.id and s.is_correct])
            else:
                for s in event.segments:
                    if s.order_index <= segment.order_index and 'Tie Breaker' not in s.name:
                        score_val += sum([s.points_per_question for sc in all_scores if sc.contestant_id == c.id and sc.segment_id == s.id and sc.is_correct])
                        
            standings.append({'contestant': c, 'score': score_val})
            
        standings.sort(key=lambda x: x['score'], reverse=True)

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
                        qualifying_count=0, is_active=True, is_final=segment.is_final 
                    )
                    db.add(tb_segment)
                    ties_created += 1
            
            segment.is_active = False 
            db.commit()
            
            if ties_created > 0:
                flash(f"Created & Auto-Started {ties_created} new Clincher round(s) for remaining ties.", "warning")
                return redirect(url_for('events.manage', event_id=event.id))
            else:
                next_seg = db.query(Segment).filter(Segment.event_id == event.id, Segment.order_index > segment.order_index).order_by(Segment.order_index.asc()).first()
                if next_seg:
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

        if segment.is_final:
            for i in range(len(standings) - 1):
                if standings[i]['score'] == standings[i+1]['score']:
                    tied_score = standings[i]['score']
                    tied_group = [s['contestant'] for s in standings if s['score'] == tied_score]
                    ids_string = ",".join([str(s.id) for s in tied_group])
                    
                    tb_seg = Segment(
                        event_id=event.id, order_index=segment.order_index, name="Clincher 1",
                        points_per_question=1, total_questions=1, participating_contestants=ids_string,
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
                     qualifying_count=slots, is_active=True, is_final=segment.is_final 
                 )
                 db.add(tb_seg)
                 
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

        segment.is_active = False 
        
        next_seg = db.query(Segment).filter(Segment.event_id == event.id, Segment.order_index > segment.order_index).order_by(Segment.order_index.asc()).first()
        
        if next_seg:
            existing = next_seg.participating_contestants.split(',') if next_seg.participating_contestants else []
            new_ids = [str(s.id) for s in final_advancing]
            next_seg.participating_contestants = ",".join(list(set(existing + new_ids)))
            next_seg.is_active = True 
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
    db = SessionLocal()
    try:
        segment = db.query(Segment).filter(Segment.id == segment_id).first()
        segment.total_questions += 1
        db.commit()
        flash(f'+1 Question added to {segment.name}!', 'success')
        return redirect(url_for('events.manage', event_id=segment.event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/pb_add_segment', methods=['POST'])
@require_role(['admin'])
def pb_add_segment(event_id):
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
    db = SessionLocal()
    try:
        new_contestant = Contestant(
            event_id=event_id,
            candidate_number=request.form.get('candidate_number'),
            name=request.form.get('name'),
            gender=request.form.get('gender'), 
            assigned_judge_id=request.form.get('assigned_judge_id')
        )
        db.add(new_contestant)
        db.commit()
        flash('Team & Tabulator Linked.', 'success')
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/pb_edit_segment/<int:segment_id>', methods=['POST'])
@require_role(['admin'])
def pb_edit_segment(event_id, segment_id):
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
            db.commit()
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()

@events_bp.route('/<int:event_id>/pb_edit_contestant/<int:contestant_id>', methods=['POST'])
@require_role(['admin'])
def pb_edit_contestant(event_id, contestant_id):
    db = SessionLocal()
    try:
        contestant = db.query(Contestant).filter(Contestant.id == contestant_id).first()
        if contestant:
            contestant.candidate_number = request.form.get('candidate_number')
            contestant.name = request.form.get('name')
            contestant.assigned_judge_id = request.form.get('assigned_judge_id')
            db.commit()
        return redirect(url_for('events.manage', event_id=event_id))
    finally:
        db.close()
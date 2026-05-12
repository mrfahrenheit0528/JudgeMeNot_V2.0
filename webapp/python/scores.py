import io
from flask import Blueprint, render_template, flash, redirect, url_for, Response, send_file
from webapp.python.database import SessionLocal
from webapp.python.models import Event, Contestant, Score, JudgeProgress, Segment
from sqlalchemy import func
from webapp.python.auth import require_role
from webapp.python.services import get_live_leaderboard

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

scores_bp = Blueprint('scores', __name__, url_prefix='/admin/scores')

@scores_bp.route('/')
@require_role(['admin', 'admin-viewer'])
def index():
    db = SessionLocal()
    try:
        events = db.query(Event).order_by(Event.id.desc()).all()
        return render_template('scores_main.html', events=events)
    finally:
        db.close()

@scores_bp.route('/<int:event_id>')
@require_role(['admin', 'admin-viewer'])
def detail(event_id):
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            flash("Event not found.", "error")
            return redirect(url_for('scores.index'))
            
        raw_leaderboard = get_live_leaderboard(db, event_id)
        all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event_id).all()
        
        # Enrich leaderboard: template expects row.contestant (model object) and row.score
        contestant_map = {c.id: c for c in event.contestants}
        overall_leaderboard = []
        for r in raw_leaderboard:
            contestant_obj = contestant_map.get(r['id'])
            if contestant_obj:
                class LBRow:
                    pass
                row = LBRow()
                row.contestant = contestant_obj
                row.score = r['total_score']
                row.rank = r.get('rank', 0)
                overall_leaderboard.append(row)
        
        matrix = {}
        for seg in event.segments:
            crit_weights = {crit.id: (crit.weight / 100.0 if crit.weight > 1.0 else crit.weight) for crit in seg.criteria}
            
            matrix[seg.id] = {}
            for c in event.contestants:
                matrix[seg.id][c.id] = {}
                for assignment in event.assigned_judges:
                    judge_id = assignment.judge_id
                    
                    j_score = 0.0
                    has_scores = False
                    for s in all_scores:
                        if s.contestant_id == c.id and s.segment_id == seg.id and s.judge_id == judge_id and s.score_value is not None:
                            cw = crit_weights.get(s.criteria_id, 1.0)
                            j_score += s.score_value * cw
                            has_scores = True
                            
                    matrix[seg.id][c.id][judge_id] = j_score if has_scores else '-'

        stats = {}
        if event.event_type == 'Score-Based':
            valid_lb = [r for r in overall_leaderboard if r.score > 0]
            valid_lb.sort(key=lambda x: x.score, reverse=True)
            stats['top_scorer'] = valid_lb[0] if valid_lb else None
            stats['lowest_scorer'] = valid_lb[-1] if valid_lb else None

            progress_records = db.query(JudgeProgress).join(Segment).filter(Segment.event_id == event_id).all()
            progress_map = {}
            for p in progress_records:
                if p.segment_id not in progress_map:
                    progress_map[p.segment_id] = {}
                progress_map[p.segment_id][p.judge_id] = p.is_submitted
            stats['progress_map'] = progress_map

            seg_averages = {}
            for seg in event.segments:
                total_score = 0
                count = 0
                for c_dict in matrix.get(seg.id, {}).values():
                    for j_score in c_dict.values():
                        if j_score != '-':
                            total_score += j_score
                            count += 1
                seg_averages[seg.id] = total_score / count if count > 0 else 0

            stats['segment_averages'] = seg_averages
            stats['toughest_segment'] = None
            stats['easiest_segment'] = None

            valid_avgs = {k: v for k, v in seg_averages.items() if v > 0}
            if valid_avgs:
                toughest_id = min(valid_avgs, key=valid_avgs.get)
                easiest_id = max(valid_avgs, key=valid_avgs.get)
                toughest_seg = next(s for s in event.segments if s.id == toughest_id)
                easiest_seg = next(s for s in event.segments if s.id == easiest_id)
                stats['toughest_segment'] = {"name": toughest_seg.name, "avg": valid_avgs[toughest_id]}
                stats['easiest_segment'] = {"name": easiest_seg.name, "avg": valid_avgs[easiest_id]}

        return render_template('scores_detail.html', event=event, overall_leaderboard=overall_leaderboard, matrix=matrix, stats=stats)
    finally:
        db.close()

@scores_bp.route('/<int:event_id>/export/<string:target>')
@require_role(['admin', 'admin-viewer'])
def export(event_id, target):
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            flash("Event not found.", "error")
            return redirect(url_for('scores.index'))

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        styles = getSampleStyleSheet()

        # Build reusable signature table
        sig_data = []
        row_sigs = []
        row_names = []
        
        if event.event_type == 'Point-Based':
            tabulators = set()
            for c in event.contestants:
                if c.assigned_judge: tabulators.add(c.assigned_judge)
            sorted_tabs = sorted(list(tabulators), key=lambda x: (x.name or x.username).lower())
            
            for t in sorted_tabs:
                row_sigs.append("_________________________________")
                row_names.append(f"{t.name or t.username}\n(Tabulator)")
                if len(row_sigs) == 3:
                    sig_data.append(row_sigs)
                    sig_data.append(row_names)
                    sig_data.append(["", "", ""])
                    row_sigs = []
                    row_names = []
        else:
            judges = event.assigned_judges
            for j in judges:
                row_sigs.append("_________________________________")
                row_names.append(f"{j.judge.name or j.judge.username}\n({'Chairman Judge' if j.is_chairman else 'Judge'})")
                if len(row_sigs) == 3:
                    sig_data.append(row_sigs)
                    sig_data.append(row_names)
                    sig_data.append(["", "", ""])
                    row_sigs = []
                    row_names = []
        
        if row_sigs:
            while len(row_sigs) < 3:
                row_sigs.append("")
                row_names.append("")
            sig_data.append(row_sigs)
            sig_data.append(row_names)

        # =========================================================
        # 1. OVERALL EXPORT LOGIC
        # =========================================================
        if target == 'overall':
            filename = f"{event.name.replace(' ', '_')}_Overall_Results.pdf"
            all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event_id).all()
            sorted_segments = sorted(event.segments, key=lambda x: (x.order_index, x.id))
            
            final_started = False
            final_seg = next((s for s in event.segments if s.is_final), None)
            if final_seg:
                if final_seg.is_active or any(s.segment_id == final_seg.id and s.score_value is not None for s in all_scores):
                    final_started = True
                    
            contestants_data = []
            
            for c in event.contestants:
                segment_scores = {}
                segment_weighted = {}
                prelim_base = 0.0
                final_base = 0.0
                
                for seg in sorted_segments:
                    if not seg.is_contestant_allowed(c.id):
                        segment_scores[seg.id] = '-'
                        segment_weighted[seg.id] = '-'
                        continue
                        
                    if event.event_type == 'Point-Based':
                        pts = sum([seg.points_per_question for s in all_scores if s.contestant_id == c.id and s.segment_id == seg.id and s.is_correct])
                        segment_scores[seg.id] = pts
                        segment_weighted[seg.id] = pts
                        if not ('Clincher' in seg.name or 'Tie Breaker' in seg.name):
                            if seg.is_final: final_base += pts
                            else: prelim_base += pts
                    else:
                        crit_weights = {crit.id: (crit.weight / 100.0 if crit.weight > 1.0 else crit.weight) for crit in seg.criteria}
                        
                        seg_scores_arr = []
                        for j in event.assigned_judges:
                            j_score = 0.0
                            has_scores = False
                            for s in all_scores:
                                if s.contestant_id == c.id and s.segment_id == seg.id and s.judge_id == j.judge_id and s.score_value is not None:
                                    cw = crit_weights.get(s.criteria_id, 1.0)
                                    j_score += s.score_value * cw
                                    has_scores = True
                            if has_scores: 
                                seg_scores_arr.append(j_score)
                                
                        avg_seg = sum(seg_scores_arr) / len(seg_scores_arr) if seg_scores_arr else 0.0
                        w_seg = seg.percentage_weight or 0.0
                        if w_seg > 1.0: w_seg = w_seg / 100.0
                        pts = avg_seg * w_seg if w_seg > 0 else avg_seg
                        
                        segment_scores[seg.id] = avg_seg # THE FIX: Show 100% on PDF table
                        segment_weighted[seg.id] = pts # Use this for sorting
                        if not ('Clincher' in seg.name or 'Tie Breaker' in seg.name):
                            if seg.is_final: final_base += pts
                            else: prelim_base += pts
                            
                contestants_data.append({
                    'contestant': c,
                    'segment_scores': segment_scores,
                    'segment_weighted': segment_weighted,
                    'prelim_base': prelim_base,
                    'final_base': final_base
                })
                
            def sort_key(x):
                if final_started:
                    k1 = x['final_base']
                    k_clinchers = []
                    for s in sorted_segments:
                        if s.is_final and ('Clincher' in s.name or 'Tie Breaker' in s.name):
                            val = x['segment_weighted'][s.id]
                            k_clinchers.append(-1 if val == '-' else float(val))
                    k2 = x['prelim_base']
                    return (k1, tuple(k_clinchers), k2)
                else:
                    k1 = x['prelim_base']
                    k_clinchers = []
                    for s in sorted_segments:
                        if not s.is_final and ('Clincher' in s.name or 'Tie Breaker' in s.name):
                            val = x['segment_weighted'][s.id]
                            k_clinchers.append(-1 if val == '-' else float(val))
                    return (k1, tuple(k_clinchers))

            # --- DYNAMIC CATEGORY PAGE BREAKER ---
            categories = ['Male', 'Female'] if event.category_count == 2 else ['Overall']
            
            for cat_idx, cat in enumerate(categories):
                cat_data = [x for x in contestants_data if (event.category_count == 1 or x['contestant'].gender == cat)]
                if not cat_data: continue
                
                cat_data.sort(key=sort_key, reverse=True)
                
                # Render Header Per Page
                elements.append(Paragraph(f"<b>EVENT FINAL RESULTS: {event.name}</b>", styles['Title']))
                if len(categories) > 1:
                    elements.append(Paragraph(f"<b>{cat.upper()} CATEGORY</b>", styles['Heading3']))
                elements.append(Spacer(1, 12))
                
                headers = ['Rank', 'No.', 'Candidate Name']
                total_prelim_inserted = False
                
                for s in sorted_segments:
                    if s.is_final and not total_prelim_inserted:
                        headers.append('Total\nPrelim')
                        total_prelim_inserted = True
                    name = s.name.replace('Tie Breaker', 'TB').replace('Clincher', 'Clinch').replace(' (', '\n(')
                    headers.append(name)
                    
                if not total_prelim_inserted: headers.append('Total\nPrelim')
                if final_started: headers.append('Base\nFinal')
                    
                table_data = [headers]
                
                rank = 1
                for x in cat_data:
                    c = x['contestant']
                    row = [str(rank), str(c.candidate_number or '-'), c.name]
                    
                    total_prelim_rendered = False
                    for s in sorted_segments:
                        if s.is_final and not total_prelim_rendered:
                            val = f"{x['prelim_base']:.2f}" if event.event_type == 'Score-Based' else str(int(x['prelim_base'])) if float(x['prelim_base']).is_integer() else str(x['prelim_base'])
                            row.append(val)
                            total_prelim_rendered = True
                            
                        # Use Unweighted 100% Score for display
                        score = x['segment_scores'][s.id]
                        if score == '-': row.append('-')
                        else:
                            val = f"{score:.2f}" if event.event_type == 'Score-Based' else str(int(score)) if float(score).is_integer() else str(score)
                            row.append(val)
                            
                    if not total_prelim_rendered:
                        val = f"{x['prelim_base']:.2f}" if event.event_type == 'Score-Based' else str(int(x['prelim_base'])) if float(x['prelim_base']).is_integer() else str(x['prelim_base'])
                        row.append(val)
                        
                    if final_started:
                        val = f"{x['final_base']:.2f}" if event.event_type == 'Score-Based' else str(int(x['final_base'])) if float(x['final_base']).is_integer() else str(x['final_base'])
                        row.append(val)
                        
                    table_data.append(row)
                    rank += 1
                    
                base_width = 732 
                rank_w = 35
                no_w = 35
                name_w = 160
                dynamic_cols = len(headers) - 3
                dynamic_w = (base_width - rank_w - no_w - name_w) / max(dynamic_cols, 1)
                col_widths = [rank_w, no_w, name_w] + [dynamic_w] * dynamic_cols

                t = Table(table_data, colWidths=col_widths)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('ALIGN', (1, 1), (2, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 20))
                
                # Append Signatures Per Page
                elements.append(Paragraph("<b>Certified True and Correct By:</b>", styles['Normal']))
                elements.append(Spacer(1, 30))
                if sig_data:
                    sig_table = Table(sig_data, colWidths=[244, 244, 244])
                    sig_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
                    ]))
                    elements.append(sig_table)
                
                # Trigger Page Break
                if cat_idx < len(categories) - 1:
                    elements.append(PageBreak())

        # =========================================================
        # 2. SEGMENT EXPORT LOGIC
        # =========================================================
        elif target.startswith('segment_'):
            seg_id = int(target.split('_')[1])
            seg = next((s for s in event.segments if s.id == seg_id), None)
            
            if not seg:
                flash("Segment not found.", "error")
                return redirect(url_for('scores.detail', event_id=event_id))
                
            filename = f"{event.name.replace(' ', '_')}_{seg.name.replace(' ', '_')}_Matrix.pdf"
            all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event_id, Score.segment_id == seg.id).all()
            crit_weights = {crit.id: (crit.weight / 100.0 if crit.weight > 1.0 else crit.weight) for crit in seg.criteria}
            
            categories = ['Male', 'Female'] if event.category_count == 2 else ['Overall']
            
            for cat_idx, cat in enumerate(categories):
                cat_contestants = [c for c in event.contestants if (event.category_count == 1 or c.gender == cat)]
                if not cat_contestants: continue

                elements.append(Paragraph(f"<b>SEGMENT MATRIX: {seg.name.upper()}</b>", styles['Title']))
                if len(categories) > 1:
                    elements.append(Paragraph(f"<b>{cat.upper()} CATEGORY</b>", styles['Heading3']))
                elements.append(Paragraph(f"<b>Event:</b> {event.name} | <b>Weight:</b> {seg.percentage_weight * 100 if seg.percentage_weight else 0}%", styles['Normal']))
                elements.append(Spacer(1, 12))
                
                headers = ['No.', 'Candidate Name']
                judges = event.assigned_judges
                for j in judges:
                    headers.append(f"{j.judge.name or j.judge.username}\n{' (CH)' if j.is_chairman else ''}")
                headers.append('Average') # Fix: Average instead of Total
                table_data = [headers]
                
                for c in sorted(cat_contestants, key=lambda x: x.candidate_number or 999):
                    row_data = [str(c.candidate_number or '-'), c.name]
                    total_sum = 0
                    count = 0
                    has_scores = False
                    
                    for j in judges:
                        j_score = 0.0
                        j_has_scores = False
                        for s in all_scores:
                            if s.contestant_id == c.id and s.judge_id == j.judge_id and s.score_value is not None:
                                cw = crit_weights.get(s.criteria_id, 1.0)
                                j_score += s.score_value * cw
                                j_has_scores = True
                                
                        if j_has_scores:
                            row_data.append(f"{j_score:.2f}")
                            total_sum += j_score
                            count += 1
                            has_scores = True
                        else:
                            row_data.append('-')
                            
                    # THE FIX: Computes the 100% average exactly
                    row_data.append(f"{(total_sum / count):.2f}" if has_scores and count > 0 else '-')
                    table_data.append(row_data)

                base_width = 732
                num_judges = len(judges)
                name_width = 200
                no_width = 50
                total_width = 80
                rem_width = base_width - (name_width + no_width + total_width)
                judge_width = rem_width / max(num_judges, 1)
                col_widths = [no_width, name_width] + [judge_width]*num_judges + [total_width]
            
                t = Table(table_data, colWidths=col_widths)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 20))

                elements.append(Paragraph("<b>Certified True and Correct By:</b>", styles['Normal']))
                elements.append(Spacer(1, 30))
                if sig_data:
                    sig_table = Table(sig_data, colWidths=[244, 244, 244])
                    sig_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
                    ]))
                    elements.append(sig_table)
                
                # Trigger Page Break
                if cat_idx < len(categories) - 1:
                    elements.append(PageBreak())
        
        else:
            flash("Invalid export target.", "error")
            return redirect(url_for('scores.detail', event_id=event_id))

        doc.build(elements)
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
    finally:
        db.close()
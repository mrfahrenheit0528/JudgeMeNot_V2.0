import io
from flask import Blueprint, render_template, flash, redirect, url_for, Response, send_file
from webapp.python.database import SessionLocal
from webapp.python.models import Event, Contestant, Score
from webapp.python.auth import require_role
from webapp.python.services import get_live_leaderboard

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

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
        
        # Build comprehensive matrix map
        matrix = {}
        for seg in event.segments:
            matrix[seg.id] = {}
            for c in event.contestants:
                matrix[seg.id][c.id] = {}
                for assignment in event.assigned_judges:
                    judge_id = assignment.judge_id
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
    """Dynamically generates and downloads a PDF report with signature lines."""
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            flash("Event not found.", "error")
            return redirect(url_for('scores.index'))

        buffer = io.BytesIO()
        # Using Landscape orientation to comfortably fit multiple judge columns
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        styles = getSampleStyleSheet()

        # --- PREPARE JUDGES SIGNATURE BLOCK ---
        judges = event.assigned_judges
        sig_data = []
        row_sigs = []
        row_names = []
        
        for j in judges:
            j_name = j.judge.name or j.judge.username
            title = "Chairman Judge" if j.is_chairman else "Judge"
            row_sigs.append("_________________________________")
            row_names.append(f"{j_name}\n({title})")

            # 3 Signatures per row looks best in landscape
            if len(row_sigs) == 3:
                sig_data.append(row_sigs)
                sig_data.append(row_names)
                sig_data.append(["", "", ""]) # Spacer row
                row_sigs = []
                row_names = []
        
        # Catch any remaining signatures that didn't fill a row of 3
        if row_sigs:
            while len(row_sigs) < 3:
                row_sigs.append("")
                row_names.append("")
            sig_data.append(row_sigs)
            sig_data.append(row_names)


        # --- EXPORT 1: OVERALL LEADERBOARD ---
        if target == 'overall':
            filename = f"{event.name.replace(' ', '_')}_Overall_Results.pdf"
            elements.append(Paragraph(f"<b>EVENT FINAL RESULTS: {event.name}</b>", styles['Title']))
            elements.append(Spacer(1, 12))
            
            table_data = [['Rank', 'Candidate No.', 'Candidate Name', 'Category', 'Final Score']]
            
            leaderboard = get_live_leaderboard(db, event_id)
            for row in leaderboard:
                score_val = f"{row['score']:.2f}" if event.event_type == 'Score-Based' else str(row['score'])
                table_data.append([
                    str(row['rank']), 
                    str(row['contestant'].candidate_number or '-'), 
                    row['contestant'].name, 
                    row['contestant'].gender or 'Overall', 
                    score_val
                ])
                
            col_widths = [60, 100, 250, 200, 122]

        # --- EXPORT 2: SPECIFIC SEGMENT MATRIX ---
        elif target.startswith('segment_'):
            seg_id = int(target.split('_')[1])
            seg = next((s for s in event.segments if s.id == seg_id), None)
            
            if not seg:
                flash("Segment not found.", "error")
                return redirect(url_for('scores.detail', event_id=event_id))
                
            filename = f"{event.name.replace(' ', '_')}_{seg.name.replace(' ', '_')}_Matrix.pdf"
            elements.append(Paragraph(f"<b>SEGMENT MATRIX: {seg.name.upper()}</b>", styles['Title']))
            elements.append(Paragraph(f"<b>Event:</b> {event.name} | <b>Weight:</b> {seg.percentage_weight * 100 if seg.percentage_weight else 0}%", styles['Normal']))
            elements.append(Spacer(1, 12))
            
            headers = ['No.', 'Candidate Name']
            for j in judges:
                j_name = j.judge.name or j.judge.username
                headers.append(f"{j_name}\n{' (CH)' if j.is_chairman else ''}")
            headers.append('Raw Total')
            table_data = [headers]
            
            all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event_id, Score.segment_id == seg.id).all()
            
            for c in sorted(event.contestants, key=lambda x: x.candidate_number or 999):
                row_data = [str(c.candidate_number or '-'), c.name]
                raw_total = 0
                has_scores = False
                
                for j in judges:
                    j_scores = [s.score_value for s in all_scores if s.contestant_id == c.id and s.judge_id == j.judge_id and s.score_value is not None]
                    if j_scores:
                        j_sum = sum(j_scores)
                        row_data.append(f"{j_sum:.2f}")
                        raw_total += j_sum
                        has_scores = True
                    else:
                        row_data.append('-')
                        
                row_data.append(f"{raw_total:.2f}" if has_scores else '-')
                table_data.append(row_data)

            # Auto-calculate dynamic column widths to fit landscape page perfectly
            base_width = 732
            num_judges = len(judges)
            name_width = 200
            no_width = 50
            total_width = 80
            rem_width = base_width - (name_width + no_width + total_width)
            judge_width = rem_width / max(num_judges, 1)
            
            col_widths = [no_width, name_width] + [judge_width]*num_judges + [total_width]
        
        else:
            flash("Invalid export target.", "error")
            return redirect(url_for('scores.detail', event_id=event_id))


        # --- BUILD TABLE AND APPLY STYLES ---
        t = Table(table_data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 1), (2 if target == 'overall' else 1, -1), 'LEFT'), # Keep names left aligned
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 40))

        # --- APPEND SIGNATURE BLOCKS ---
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

        doc.build(elements)
        buffer.seek(0)
        
        # Return as downloadable PDF
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
        
    finally:
        db.close()
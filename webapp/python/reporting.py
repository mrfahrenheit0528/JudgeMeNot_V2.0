import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from webapp.python.database import SessionLocal
from webapp.python.models import Event, User
from webapp.python.services import get_live_leaderboard

def generate_pdf_report(event_id: int, output_dir: str = "reports"):
    """
    Generates a PDF report for a given event.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            return False, "Event not found"

        file_name = f"{event.name.replace(' ', '_')}_Results_{datetime.now().strftime('%Y%m%d%H%M')}.pdf"
        file_path = os.path.join(output_dir, file_name)

        doc = SimpleDocTemplate(file_path, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        elements.append(Paragraph(f"<b>Official Results: {event.name}</b>", styles['Title']))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f"Event Type: {event.event_type} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
        elements.append(Spacer(1, 24))

        leaderboard = get_live_leaderboard(db, event_id)
        table_data = [["Rank", "Candidate / School", "Total Score"]]

        for row in leaderboard:
            table_data.append([
                str(row["rank"]),
                row["contestant"].name,
                # UPDATED DB LOGIC CHECK
                f"{row['score']:.2f}" if event.event_type == "Score-Based" else str(row["score"])
            ])

        if len(table_data) == 1:
            table_data.append(["-", "No entries yet", "-"])

        table = Table(table_data, colWidths=[60, 250, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        elements.append(table)
        elements.append(Spacer(1, 48))

        admins = db.query(User).filter(User.role == "admin").all()
        elements.append(Paragraph("<b>Certified True and Correct:</b>", styles['Normal']))
        elements.append(Spacer(1, 24))

        signatory_data = []
        for admin in admins:
            signatory_data.append([
                "__________________________",
                ""
            ])
            signatory_data.append([
                admin.name or admin.username,
                ""
            ])
            signatory_data.append([
                "System Administrator",
                ""
            ])
            signatory_data.append(["", ""])

        if signatory_data:
            sig_table = Table(signatory_data, colWidths=[200, 200])
            elements.append(sig_table)

        doc.build(elements)
        return True, file_path
    except Exception as e:
        return False, str(e)
    finally:
        db.close()
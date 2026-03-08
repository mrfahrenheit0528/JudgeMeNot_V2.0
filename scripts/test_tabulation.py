from webapp.python.database import SessionLocal
from webapp.python.models import Event, User
from webapp.python.services import get_live_leaderboard, submit_quizbee_score, submit_pageant_score
from webapp.python.reporting import generate_pdf_report

def main():
    db = SessionLocal()
    
    print("--- Testing Pageant Logic ---")
    pageant = db.query(Event).filter(Event.name == "Miss Universe 2026").first()
    if pageant:
        board = get_live_leaderboard(db, pageant.id)
        for row in board:
            print(f"Rank {row['rank']}: {row['contestant'].name} - {row['score']}")
            
        print("Generating Pageant Report...")
        success, path = generate_pdf_report(pageant.id)
        print(f"Report Generated: {success} -> {path}")

    print("\n--- Testing Quiz Bee Logic ---")
    quizbee = db.query(Event).filter(Event.name == "National IOI 2026").first()
    if quizbee:
        board = get_live_leaderboard(db, quizbee.id)
        for row in board:
            print(f"Rank {row['rank']}: {row['contestant'].name} - {row['score']}")
            
        print("Generating Quiz Bee Report...")
        success, path = generate_pdf_report(quizbee.id)
        print(f"Report Generated: {success} -> {path}")

    db.close()

if __name__ == "__main__":
    main()

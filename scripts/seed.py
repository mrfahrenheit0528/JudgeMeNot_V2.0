from webapp.python.database import engine, SessionLocal
from webapp.python.models import User, Event, Segment, Criteria, Contestant, Score, Base
from webapp.python.auth import hash_password

def run_seed():
    print("Dropping old tables...")
    Base.metadata.drop_all(bind=engine)
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    print("Cleaning up old data if any...")
    db.query(Score).delete()
    db.query(Criteria).delete()
    db.query(Segment).delete()
    db.query(Contestant).delete()
    db.query(Event).delete()
    db.query(User).delete()
    db.commit()

    print("Adding Users...")
    default_pw = hash_password("hash")
    admin = User(username="admin", password_hash=default_pw, name="Super Admin", role="admin")
    judge1 = User(username="judge1", password_hash=default_pw, name="Judge A", role="judge")
    tabulator1 = User(username="tab1", password_hash=default_pw, name="Tabulator A", role="tabulator")
    db.add_all([admin, judge1, tabulator1])
    db.flush()

    # --- PAGEANT TEST ---
    print("Creating Pageant Event...")
    pageant = Event(name="Miss Universe 2026", event_type="PAGEANT")
    db.add(pageant)
    db.flush()

    swimwear = Segment(event_id=pageant.id, name="Swimwear", order_index=1, percentage_weight=0.5, is_active=True)
    evenly_g = Segment(event_id=pageant.id, name="Evening Gown", order_index=2, percentage_weight=0.5)
    db.add_all([swimwear, evenly_g])
    db.flush()

    poise = Criteria(segment_id=swimwear.id, name="Poise", weight=0.6, max_score=10)
    beauty = Criteria(segment_id=swimwear.id, name="Beauty", weight=0.4, max_score=10)
    db.add_all([poise, beauty])
    db.flush()

    c1 = Contestant(event_id=pageant.id, name="Candidate Alpha", candidate_number=1)
    db.add(c1)
    db.flush()

    # Pageant Score
    s1 = Score(contestant_id=c1.id, judge_id=judge1.id, segment_id=swimwear.id, criteria_id=poise.id, score_value=9.5)
    db.add(s1)

    # --- QUIZ BEE TEST ---
    print("Creating QuizBee Event...")
    quizbee = Event(name="National IOI 2026", event_type="QUIZBEE", scoring_type="hybrid")
    db.add(quizbee)
    db.flush()

    easy_round = Segment(event_id=quizbee.id, name="Easy Round", order_index=1, points_per_question=1, total_questions=10, is_active=True)
    db.add(easy_round)
    db.flush()

    school1 = Contestant(event_id=quizbee.id, name="High School A", assigned_tabulator_id=tabulator1.id)
    school2 = Contestant(event_id=quizbee.id, name="High School B", assigned_tabulator_id=tabulator1.id)
    db.add_all([school1, school2])
    db.flush()

    # Quiz Bee Score (Question 1)
    qb_s1 = Score(contestant_id=school1.id, segment_id=easy_round.id, question_number=1, is_correct=True)
    qb_s2 = Score(contestant_id=school2.id, segment_id=easy_round.id, question_number=1, is_correct=False)
    db.add_all([qb_s1, qb_s2])

    db.commit()
    print("Seeding successful!")

    # Verifications
    print("\n--- Verification ---")
    p_event = db.query(Event).filter(Event.name == "Miss Universe 2026").first()
    print(f"Pageant Event ID {p_event.id}: {p_event.name} has {len(p_event.segments)} segments and {len(p_event.contestants)} contestants.")
    
    q_event = db.query(Event).filter(Event.name == "National IOI 2026").first()
    print(f"QuizBee Event ID {q_event.id}: {q_event.name} has {len(q_event.segments)} rounds and {len(q_event.contestants)} schools.")

    db.close()

if __name__ == "__main__":
    run_seed()

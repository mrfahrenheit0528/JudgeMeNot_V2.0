from webapp.python.database import engine, SessionLocal
from webapp.python.models import User, Event, Segment, Criteria, Contestant, Score, EventJudge, Base
from webapp.python.auth import hash_password

def run_seed():
    print("Dropping old tables (if any)...")
    Base.metadata.drop_all(bind=engine)
    print("Creating fresh tables from updated schemas...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()

    print("Adding Superstar Users...")
    universal_pw = hash_password("pass123")
    
    # Super Admin
    mj = User(username="mj", password_hash=universal_pw, name="Michael Jackson", role="admin")
    
    # Pageant Judges
    sc = User(username="sc", password_hash=universal_pw, name="Sabrina Carpenter", role="judge")
    ts = User(username="ts", password_hash=universal_pw, name="Taylor Swift", role="judge")
    
    # Quiz Bee Tabulators
    bm = User(username="bm", password_hash=universal_pw, name="Bruno Mars", role="tabulator")
    ag = User(username="ag", password_hash=universal_pw, name="Ariana Grande", role="tabulator")
    
    db.add_all([mj, sc, ts, bm, ag])
    db.flush()

    # =========================================================================
    # 1. SCORE-BASED TEST (PAGEANT)
    # =========================================================================
    print("Creating Score-Based Event (Pageant)...")
    pageant = Event(name="Miss Universe 2026", event_type="Score-Based", category_count=1)
    db.add(pageant)
    db.flush()

    # Assign Judges to the Pageant
    db.add(EventJudge(event_id=pageant.id, judge_id=sc.id, is_chairman=False))
    db.add(EventJudge(event_id=pageant.id, judge_id=ts.id, is_chairman=True))

    swimwear = Segment(event_id=pageant.id, name="Swimwear", order_index=1, percentage_weight=0.5, is_active=True, is_revealed=True)
    evening_gown = Segment(event_id=pageant.id, name="Evening Gown", order_index=2, percentage_weight=0.5)
    db.add_all([swimwear, evening_gown])
    db.flush()

    poise = Criteria(segment_id=swimwear.id, name="Poise", weight=0.6, max_score=10)
    beauty = Criteria(segment_id=swimwear.id, name="Beauty", weight=0.4, max_score=10)
    db.add_all([poise, beauty])
    db.flush()

    c1 = Contestant(event_id=pageant.id, name="Kendall Jenner", candidate_number=1, gender="Female")
    c2 = Contestant(event_id=pageant.id, name="Gigi Hadid", candidate_number=2, gender="Female")
    db.add_all([c1, c2])
    db.flush()

    # Mock Pageant Scores (From Sabrina Carpenter)
    s1 = Score(contestant_id=c1.id, judge_id=sc.id, segment_id=swimwear.id, criteria_id=poise.id, score_value=9.5)
    s2 = Score(contestant_id=c1.id, judge_id=sc.id, segment_id=swimwear.id, criteria_id=beauty.id, score_value=9.8)
    db.add_all([s1, s2])


    # =========================================================================
    # 2. POINT-BASED TEST (QUIZ BEE)
    # =========================================================================
    print("Creating Point-Based Event (Quiz Bee)...")
    quizbee = Event(name="National Science Olympiad", event_type="Point-Based", scoring_type="hybrid")
    db.add(quizbee)
    db.flush()

    easy_round = Segment(event_id=quizbee.id, name="Easy Round", order_index=1, points_per_question=1.0, total_questions=5, qualifying_count=0, is_active=True)
    final_round = Segment(event_id=quizbee.id, name="Final Round", order_index=2, points_per_question=3.0, total_questions=5, is_final=True)
    db.add_all([easy_round, final_round])
    db.flush()

    # Strict Tabulator Assignment: Bruno Mars -> Harvard, Ariana Grande -> Oxford
    school1 = Contestant(event_id=quizbee.id, name="Harvard University", candidate_number=1, assigned_judge_id=bm.id, gender="Overall")
    school2 = Contestant(event_id=quizbee.id, name="Oxford University", candidate_number=2, assigned_judge_id=ag.id, gender="Overall")
    db.add_all([school1, school2])
    db.flush()

    # Mock Quiz Bee Scores
    # Harvard got Q1 Correct (scored by Bruno Mars)
    qb_s1 = Score(contestant_id=school1.id, judge_id=bm.id, segment_id=easy_round.id, question_number=1, is_correct=True)
    # Oxford got Q1 Wrong (scored by Ariana Grande)
    qb_s2 = Score(contestant_id=school2.id, judge_id=ag.id, segment_id=easy_round.id, question_number=1, is_correct=False)
    db.add_all([qb_s1, qb_s2])

    db.commit()
    
    print("\n✅ Seeding successful!")
    print("========================================")
    print("Account Credentials (Password: pass123)")
    print("----------------------------------------")
    print("Admin: mj (Michael Jackson)")
    print("Pageant Judges: sc (Sabrina Carpenter), ts (Taylor Swift)")
    print("Quiz Bee Tabulators: bm (Bruno Mars), ag (Ariana Grande)")
    print("========================================")

    db.close()

if __name__ == "__main__":
    run_seed()
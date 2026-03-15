from sqlalchemy.orm import Session
from sqlalchemy import func
from webapp.python.models import Event, Segment, Criteria, Contestant, Score, User

def get_live_leaderboard(db: Session, event_id: int):
    """
    Returns a sorted list of contestants based on the event's scoring logic.
    Supports Score-Based (weighted averages) and Point-Based (points accumulation).
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return []
        
    contestants = db.query(Contestant).filter(Contestant.event_id == event_id).all()
    results = []

    # UPDATED DB LOGIC CHECK
    if event.event_type == "Score-Based":
        for contestant in contestants:
            total_weighted_score = 0
            segments = db.query(Segment).filter(Segment.event_id == event_id, Segment.is_revealed == True).all()
            
            for segment in segments:
                criteria_list = db.query(Criteria).filter(Criteria.segment_id == segment.id).all()
                segment_score = 0
                
                for crit in criteria_list:
                    avg_score = db.query(func.avg(Score.score_value)).filter(
                        Score.contestant_id == contestant.id,
                        Score.criteria_id == crit.id
                    ).scalar() or 0
                    
                    segment_score += (avg_score * crit.weight)
                    
                total_weighted_score += (segment_score * segment.percentage_weight)
                
            results.append({
                "contestant": contestant,
                "score": round(total_weighted_score, 2)
            })
            
    # UPDATED DB LOGIC CHECK
    elif event.event_type == "Point-Based":
        all_scores = db.query(Score).join(Contestant).filter(Contestant.event_id == event_id).all()
        
        # Check if final round exists and has started/finished
        final_segments = [s for s in event.segments if s.is_final]
        final_started = any(s.is_active for s in final_segments) or any(sc.segment_id in [s.id for s in final_segments] for sc in all_scores)
        
        for contestant in contestants:
            prelim_score = 0
            final_score = 0
            
            for segment in event.segments:
                points_for_segment = len([s for s in all_scores if s.contestant_id == contestant.id and s.segment_id == segment.id and s.is_correct])
                pts = points_for_segment * segment.points_per_question
                
                if segment.is_final:
                    final_score += pts
                else:
                    prelim_score += pts
                    
            if event.scoring_type == "cumulative":
                total_points = prelim_score + final_score
            else:
                total_points = final_score if final_started else prelim_score
                
            results.append({
                "contestant": contestant,
                "score": total_points
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    
    rank = 1
    for r in results:
        r["rank"] = rank
        rank += 1
        
    return results

def submit_quizbee_score(db: Session, tabulator_id: int, contestant_id: int, segment_id: int, question_number: int, is_correct: bool):
    existing_score = db.query(Score).filter(
        Score.contestant_id == contestant_id,
        Score.segment_id == segment_id,
        Score.question_number == question_number
    ).first()
    
    if existing_score:
        existing_score.is_correct = is_correct
        existing_score.judge_id = tabulator_id
    else:
        new_score = Score(
            contestant_id=contestant_id,
            judge_id=tabulator_id,
            segment_id=segment_id,
            question_number=question_number,
            is_correct=is_correct
        )
        db.add(new_score)
        
    db.commit()

def submit_pageant_score(db: Session, judge_id: int, contestant_id: int, criteria_id: int, score_value: float):
    criteria = db.query(Criteria).filter(Criteria.id == criteria_id).first()
    if not criteria:
        return False, "Criteria not found"
        
    existing_score = db.query(Score).filter(
        Score.contestant_id == contestant_id,
        Score.judge_id == judge_id,
        Score.criteria_id == criteria_id
    ).first()
    
    if existing_score:
        existing_score.score_value = score_value
    else:
        new_score = Score(
            contestant_id=contestant_id,
            judge_id=judge_id,
            segment_id=criteria.segment_id,
            criteria_id=criteria_id,
            score_value=score_value
        )
        db.add(new_score)
        
    db.commit()
    return True, "Success"
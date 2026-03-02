from collections import defaultdict
from webapp.python.models import Event, Segment, Contestant, Score

def generate_clincher_round(db_session, event_id: int, tied_contestant_ids: list):
    """
    Creates a new 'Clincher' round segment for Quiz Bees to break a tie.
    Only the provided 'tied_contestant_ids' will be permitted to participate.
    """
    event = db_session.query(Event).filter(Event.id == event_id).first()
    
    # Check existing clincher rounds to decide the name (Clincher 1, Clincher 2, etc.)
    existing_clinchers = db_session.query(Segment).filter(
        Segment.event_id == event_id,
        Segment.name.like("Clincher%")
    ).count()
    
    clincher_num = existing_clinchers + 1
    new_segment_name = f"Clincher {clincher_num}"
    
    # Get highest order index
    max_order = 0
    segments = db_session.query(Segment).filter(Segment.event_id == event_id).all()
    if segments:
        max_order = max([s.order_index for s in segments if s.order_index is not None] + [0])
        
    # Create the Clincher Segment
    # Typically, Sudden Death clinchers only have 1 question per round
    clincher_segment = Segment(
        event_id=event_id,
        name=new_segment_name,
        order_index=max_order + 1,
        is_active=False,
        is_revealed=False,
        is_final=False, # Wait until we know this resolves the whole event
        points_per_question=1,
        total_questions=1, 
        participating_contestant_ids=','.join(map(str, tied_contestant_ids))
    )
    
    db_session.add(clincher_segment)
    db_session.commit()
    db_session.refresh(clincher_segment)
    return clincher_segment


def check_tie_breakers(db_session, event_id: int):
    """
    Evaluates the live leaderboard and detects if there are any deadlocks 
    at the qualifying counts (e.g. 5 schools qualify but 5th and 6th are tied).
    Returns a list of tied contestant IDs if a tiebreaker is needed.
    """
    from webapp.python.services import get_live_leaderboard
    
    leaderboard = get_live_leaderboard(db_session, event_id)
    if not leaderboard:
        return []
        
    active_segment = db_session.query(Segment).filter(
        Segment.event_id == event_id, 
        Segment.is_active == True
    ).first()
    
    if not active_segment or active_segment.qualifier_limit <= 0:
        return [] # No cutoffs defined for this round
        
    cutoff = active_segment.qualifier_limit
    
    # If we have less candidates than the cutoff, everyone just passes
    if len(leaderboard) <= cutoff:
        return []
        
    # The score of the person precisely at the cutoff boundary
    cutoff_score = leaderboard[cutoff - 1]["score"]
    
    # Who else has exactly this score?
    tied_contestant_ids = []
    
    # We want to find EVERYONE with the cutoff score
    for row in leaderboard:
        if row["score"] == cutoff_score:
            tied_contestant_ids.append(row["contestant"].id)
            
    # If the cutoff score is shared by more people than the remaining slots
    # Examples:
    # 3 qualify. R1 (90), R2 (85), R3 (85), R4 (85). Cutoff score = 85.
    # Tied contestants = [R2, R3, R4] (3 people). But only 2 slots exist for 85.
    
    slots_available_for_score = 0
    # calculate how many slots are above the tie
    people_above = len([r for r in leaderboard if r["score"] > cutoff_score])
    slots_available_for_score = cutoff - people_above
    
    if len(tied_contestant_ids) > slots_available_for_score:
        return tied_contestant_ids
        
    return []

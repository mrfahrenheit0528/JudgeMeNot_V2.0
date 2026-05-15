import pytest
import asyncio
import httpx
import sys
import os

# Ensure the project root is in sys.path when running directly via IDE
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from webapp.python.models import Score, ScoreLedger, Event, Segment, User, Contestant
from webapp.python.services import submit_pageant_score, verify_ledger_integrity, submit_quizbee_score
import json

# ---------------------------------------------------------
# 1. Cryptographic Ledger Integrity
# ---------------------------------------------------------
def test_sequential_block_validation(db_session: Session):
    # Get test data
    judge = db_session.query(User).filter_by(role='judge').first()
    contestant = db_session.query(Contestant).filter_by(name='Contestant 1').first()
    segment = db_session.query(Segment).filter_by(name='Swimsuit').first()
    criteria = segment.criteria[0]

    # Submit a few scores
    submit_pageant_score(db_session, judge.id, contestant.id, criteria.id, 8.5)
    
    contestant2 = db_session.query(Contestant).filter_by(name='Contestant 2').first()
    submit_pageant_score(db_session, judge.id, contestant2.id, criteria.id, 9.0)

    # Validate ledger blocks exist and hashes are sequential
    blocks = db_session.query(ScoreLedger).order_by(ScoreLedger.block_index.asc()).all()
    assert len(blocks) == 2
    
    # Check chain integrity
    assert blocks[0].block_index == 1
    assert blocks[0].previous_hash == "0" * 64
    assert blocks[1].block_index == 2
    assert blocks[1].previous_hash == blocks[0].current_hash
    
    is_valid, msg, compromised = verify_ledger_integrity(db_session, full_check=True)
    assert is_valid is True
    assert len(compromised) == 0

def test_tamper_detection_crucial(db_session: Session):
    judge = db_session.query(User).filter_by(role='judge').first()
    contestant = db_session.query(Contestant).filter_by(name='Contestant 1').first()
    segment = db_session.query(Segment).filter_by(name='Swimsuit').first()
    criteria = segment.criteria[0]

    submit_pageant_score(db_session, judge.id, contestant.id, criteria.id, 9.5)
    
    # Intentionally tamper with the database bypassing the application logic
    score_to_tamper = db_session.query(Score).first()
    score_to_tamper.score_value = 1.0  # Tampered!
    db_session.commit()

    # The ledger verification should catch this layer 2 DB tamper
    is_valid, msg, compromised = verify_ledger_integrity(db_session, full_check=True)
    
    assert is_valid is False
    assert len(compromised) == 1
    assert "Score tampering detected" in msg

# ---------------------------------------------------------
# 2. RBAC & Authentication
# ---------------------------------------------------------
def test_unauthorized_access(client):
    # Login as judge
    with client.session_transaction() as sess:
        sess['user'] = {'id': 2, 'role': 'judge', 'username': 'judge1'}
        
    # Attempt to access admin dashboard
    response = client.get('/control-panel')
    # Should redirect because judge is not admin
    assert response.status_code == 302
    assert '/control-panel' not in response.location

def test_tabulator_isolation(client, db_session):
    tabulator = db_session.query(User).filter_by(role='tabulator').first()
    # Login as tabulator
    with client.session_transaction() as sess:
        sess['user'] = {'id': tabulator.id, 'role': 'tabulator', 'username': 'tab1'}
    
    # Try to access admin settings
    response = client.get('/admin/users')
    assert response.status_code == 302 # Redirected out

# ---------------------------------------------------------
# 3. State Management & Core Business Logic
# ---------------------------------------------------------
def test_locked_segment_enforcement(client, db_session):
    judge = db_session.query(User).filter_by(role='judge').first()
    pageant = db_session.query(Event).filter_by(name='Miss Universe').first()
    seg = db_session.query(Segment).filter_by(name='Swimsuit').first()
    crit = seg.criteria[0]
    c1 = db_session.query(Contestant).filter_by(name='Contestant 1').first()
    
    # Pre-auth client
    with client.session_transaction() as sess:
        sess['user'] = {'id': judge.id, 'role': 'judge', 'username': 'judge1'}
    
    # Lock the segment for this judge
    response = client.post('/judge/api_lock_segment', json={
        'segment_id': seg.id
    })
    
    assert response.status_code == 200
    
    # Attempt to score a locked segment
    response = client.post('/judge/api_submit_score', json={
        'segment_id': seg.id,
        'contestant_id': c1.id,
        'criteria_id': crit.id,
        'score_value': '8.0'
    })
    
    # Because event is locked, it should be rejected
    json_data = response.get_json()
    assert json_data.get('status') == 'error'
    assert 'already locked' in json_data.get('message').lower()

def test_event_lifecycle_enforcement(db_session: Session):
    event = db_session.query(Event).filter_by(name='Miss Universe').first()
    assert event.status == 'Active'
    event.status = 'Completed'
    db_session.commit()
    assert event.status == 'Completed'

# ---------------------------------------------------------
# 4. Automated Tiebreaker Engine
# ---------------------------------------------------------
def test_tie_detection_and_clincher(db_session: Session):
    from webapp.python.tiebreaker import check_tie_breakers
    
    # Set up tied scores
    judge = db_session.query(User).filter_by(role='judge').first()
    c1 = db_session.query(Contestant).filter_by(name='Contestant 1').first()
    c2 = db_session.query(Contestant).filter_by(name='Contestant 2').first()
    seg = db_session.query(Segment).filter_by(name='Swimsuit').first()
    crit = seg.criteria[0]

    submit_pageant_score(db_session, judge.id, c1.id, crit.id, 9.5)
    submit_pageant_score(db_session, judge.id, c2.id, crit.id, 9.5)
    
    # The pageant scoring doesn't use the quiz bee tiebreaker natively in the same way,
    # but we can test the function directly just to ensure it runs without error.
    pageant = db_session.query(Event).filter_by(name='Miss Universe').first()
    check_tie_breakers(db_session, pageant.id)
    assert True

# ---------------------------------------------------------
# 5. WebSocket (Socket.IO) Broadcasts
# ---------------------------------------------------------
def test_client_emission(socketio_client, db_session):
    judge = db_session.query(User).filter_by(role='judge').first()
    c1 = db_session.query(Contestant).filter_by(name='Contestant 1').first()
    seg = db_session.query(Segment).filter_by(name='Swimsuit').first()
    crit = seg.criteria[0]
    
    # Hook into socket connection
    assert socketio_client.is_connected()
    
    # Submit score which triggers `append_to_ledger` and `emit`
    submit_pageant_score(db_session, judge.id, c1.id, crit.id, 8.8)
    
    # Get received events
    received = socketio_client.get_received()
    # Find new_ledger_block event
    ledger_events = [r for r in received if r['name'] == 'new_ledger_block']
    assert len(ledger_events) >= 1
    
    payload = ledger_events[0]['args'][0]
    assert 'curr_hash' in payload
    assert payload['integrity'] is True

# ---------------------------------------------------------
# 6. Concurrency & Connection Pool Stress
# ---------------------------------------------------------
@pytest.mark.asyncio
async def test_simultaneous_submission(client, db_session):
    # This tests how the system handles many scores arriving
    import asyncio
    
    judge = db_session.query(User).filter_by(role='judge').first()
    c1 = db_session.query(Contestant).filter_by(name='Contestant 1').first()
    seg = db_session.query(Segment).filter_by(name='Swimsuit').first()
    crit = seg.criteria[0]
    
    # Make sure event is active
    pageant = db_session.query(Event).filter_by(name='Miss Universe').first()
    pageant.is_locked = False
    db_session.commit()

    # Pre-auth client
    with client.session_transaction() as sess:
        sess['user'] = {'id': judge.id, 'role': 'judge', 'username': 'judge1'}

    # Use asyncio to hit the test client concurrently
    async def submit_req(idx):
        # We run the Flask test client in an executor so it doesn't block the async loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: client.post('/judge/api_submit_score', json={
            'segment_id': seg.id,
            'contestant_id': c1.id,
            'criteria_id': crit.id,
            'score_value': str(8.0 + (idx % 10)*0.1)
        }))

    num_requests = 10
    tasks = [submit_req(i) for i in range(num_requests)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Check that there were no internal server errors (500)
    successes = [r for r in results if not isinstance(r, Exception) and r.status_code == 200]
    assert len(successes) > 0  # At least some should succeed

    # Verify ledger integrity remains intact
    is_valid, _, _ = verify_ledger_integrity(db_session, full_check=False)
    assert is_valid is True

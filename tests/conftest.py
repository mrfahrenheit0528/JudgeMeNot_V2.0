import pytest
import os
import sys
import tempfile

# Ensure the project root is in sys.path when running directly via IDE
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from webapp.python.models import Base, User, Event, Segment, Contestant, Criteria, Score, ScoreLedger
from main import create_app

@pytest.fixture(scope="session")
def app():
    # Setup the application and test DB
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test_secret'
    })
    
    # Push app context so we can use it throughout tests
    with app.app_context():
        yield app

@pytest.fixture(scope="session")
def client(app):
    return app.test_client()

@pytest.fixture(scope="session")
def socketio_client(app):
    from main import socketio
    client = socketio.test_client(app)
    return client

@pytest.fixture(scope="session", autouse=True)
def patch_db():
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    import webapp.python.database as db_module
    db_module.engine = engine
    db_module.SessionLocal = TestingSessionLocal
    
    yield TestingSessionLocal
    
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session(patch_db):
    # Setup test DB schema and session
    session = patch_db()

    # Create dummy users for RBAC testing
    admin_user = User(username='admin', password_hash='hash', name='Admin User', role='admin')
    judge_user = User(username='judge1', password_hash='hash', name='Judge One', role='judge')
    tabulator_user = User(username='tab1', password_hash='hash', name='Tabulator One', role='tabulator')
    session.add_all([admin_user, judge_user, tabulator_user])
    
    # Create a dummy Pageant event
    pageant = Event(name='Miss Universe', event_type='Score-Based', status='Active')
    session.add(pageant)
    session.flush()
    
    seg1 = Segment(event_id=pageant.id, name='Swimsuit', is_active=True, percentage_weight=50)
    session.add(seg1)
    session.flush()

    crit1 = Criteria(segment_id=seg1.id, name='Poise', weight=100.0, max_score=10)
    session.add(crit1)

    c1 = Contestant(event_id=pageant.id, name='Contestant 1', candidate_number=1, status='Active')
    c2 = Contestant(event_id=pageant.id, name='Contestant 2', candidate_number=2, status='Active')
    session.add_all([c1, c2])

    # Create a dummy Quiz Bee event
    quizbee = Event(name='Math Bee', event_type='Point-Based', status='Active', scoring_type='cumulative')
    session.add(quizbee)
    session.flush()

    q_seg1 = Segment(event_id=quizbee.id, name='Easy Round', is_active=True, points_per_question=1.0, total_questions=5)
    session.add(q_seg1)
    
    qc1 = Contestant(event_id=quizbee.id, name='School A', assigned_judge_id=tabulator_user.id)
    qc2 = Contestant(event_id=quizbee.id, name='School B')
    session.add_all([qc1, qc2])

    session.commit()

    yield session

    session.rollback()
    session.close()
    
    # Drop all and recreate to isolate tests
    from webapp.python.database import engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

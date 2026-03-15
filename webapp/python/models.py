import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

# ---------------------------------------------------------
# 1. USERS & ROLES
# ---------------------------------------------------------
class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False) 
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100)) 
    
    # "admin", "judge", "tabulator", "viewer"
    role = Column(String(20), nullable=False) 
    
    is_active = Column(Boolean, default=True)
    is_chairman = Column(Boolean, default=False) 
    
    scores_given = relationship("Score", back_populates="judge")
    audit_logs = relationship("AuditLog", back_populates="user")
    assigned_schools = relationship("Contestant", back_populates="assigned_judge")

# ---------------------------------------------------------
# 2. EVENTS
# ---------------------------------------------------------
class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False) 
    
    # "PAGEANT" or "QUIZBEE" (Score-Based vs Point-Based)
    event_type = Column(String(20), nullable=False) 
    
    # Used mainly for Quiz Bees: "per_round", "cumulative", "hybrid"
    scoring_type = Column(String(50), default='per_round') 
    
    status = Column(String(20), default='Active') 
    is_locked = Column(Boolean, default=False)
    show_public_rankings = Column(Boolean, default=False)
    category_count = Column(Integer, default=1)
    
    last_active = Column(DateTime, default=datetime.datetime.now)
    
    segments = relationship("Segment", back_populates="event", cascade="all, delete-orphan")
    contestants = relationship("Contestant", back_populates="event", cascade="all, delete-orphan")
    assigned_judges = relationship("EventJudge", back_populates="event", cascade="all, delete-orphan")

# ---------------------------------------------------------
# 3. SEGMENTS (ROUNDS)
# ---------------------------------------------------------
class Segment(Base):
    __tablename__ = 'segments'
    
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    name = Column(String(100), nullable=False)
    order_index = Column(Integer)
    
    is_active = Column(Boolean, default=False)
    is_revealed = Column(Boolean, default=False) 
    is_final = Column(Boolean, default=False) 
    
    # --- Pageant Specific Fields ---
    percentage_weight = Column(Float, default=0.0)
    
    # --- Quiz Bee Specific Fields ---
    points_per_question = Column(Float, default=1.0)
    total_questions = Column(Integer, default=0)
    qualifying_count = Column(Integer, default=0) 
    participating_contestants = Column(String(255), nullable=True) # CSV of allowed contestant IDs
    
    event = relationship("Event", back_populates="segments")
    criteria = relationship("Criteria", back_populates="segment", cascade="all, delete-orphan")
    scores = relationship("Score", back_populates="segment", cascade="all, delete-orphan")
    
    def is_contestant_allowed(self, contestant_id):
        if not self.participating_contestants:
            return True
        allowed_list = self.participating_contestants.split(',')
        return str(contestant_id) in allowed_list

# ---------------------------------------------------------
# 4. CRITERIA (Pageant Only)
# ---------------------------------------------------------
class Criteria(Base):
    __tablename__ = 'criteria'
    
    id = Column(Integer, primary_key=True)
    segment_id = Column(Integer, ForeignKey('segments.id'))
    name = Column(String(100), nullable=False)
    weight = Column(Float, default=1.0) 
    max_score = Column(Integer, default=10)
    
    segment = relationship("Segment", back_populates="criteria")
    scores = relationship("Score", back_populates="criteria", cascade="all, delete-orphan")

# ---------------------------------------------------------
# 5. CONTESTANTS
# ---------------------------------------------------------
class Contestant(Base):
    __tablename__ = 'contestants'
    
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    
    candidate_number = Column(Integer, nullable=True)
    name = Column(String(100), nullable=False) # Name of Candidate OR School
    gender = Column(String(10), nullable=True) 
    status = Column(String(20), default='Active') 
    image_path = Column(String(255), nullable=True) 
    
    # --- Quiz Bee Specific Fields ---
    # Strict 1-to-1 relationship for Tabulators
    assigned_judge_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    event = relationship("Event", back_populates="contestants")
    scores = relationship("Score", back_populates="contestant", cascade="all, delete-orphan")
    assigned_judge = relationship("User", back_populates="assigned_schools")

    __table_args__ = (
        UniqueConstraint('name', 'event_id', name='unique_contestant_per_event'),
    )

# ---------------------------------------------------------
# 6. SCORES
# ---------------------------------------------------------
class Score(Base):
    __tablename__ = 'scores'
    
    id = Column(Integer, primary_key=True)
    contestant_id = Column(Integer, ForeignKey('contestants.id'), nullable=False)
    judge_id = Column(Integer, ForeignKey('users.id')) # nullable for QuizBee Tabulators
    segment_id = Column(Integer, ForeignKey('segments.id'), nullable=False)
    
    # --- Pageant Specific Fields ---
    criteria_id = Column(Integer, ForeignKey('criteria.id'), nullable=True) 
    score_value = Column(Float, default=0.0) 
    
    # --- Quiz Bee Specific Fields ---
    question_number = Column(Integer, nullable=True) 
    is_correct = Column(Boolean, default=False)
    
    contestant = relationship("Contestant", back_populates="scores")
    judge = relationship("User", back_populates="scores_given")
    segment = relationship("Segment", back_populates="scores")
    criteria = relationship("Criteria", back_populates="scores")

# ---------------------------------------------------------
# 7. LOGS / JUDGE ASSIGNMENTS
# ---------------------------------------------------------
class JudgeProgress(Base):
    __tablename__ = 'judge_progress'
    id = Column(Integer, primary_key=True)
    judge_id = Column(Integer, ForeignKey('users.id'))
    segment_id = Column(Integer, ForeignKey('segments.id'))
    is_finished = Column(Boolean, default=False) 
    is_submitted = Column(Boolean, default=False) # True when scores are permanently locked

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    action = Column(String(50)) 
    details = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.now)
    user = relationship("User", back_populates="audit_logs")

class EventJudge(Base):
    __tablename__ = 'event_judges'
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    judge_id = Column(Integer, ForeignKey('users.id'))
    is_chairman = Column(Boolean, default=False) 
    
    event = relationship("Event", back_populates="assigned_judges")
    judge = relationship("User")
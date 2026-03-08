import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import relationship, backref
from core.database import Base

# ---------------------------------------------------------
# 1. USERS & ROLES
# ---------------------------------------------------------
class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=True) 
    password_hash = Column(String(255), nullable=True)
    name = Column(String(100)) 
    
    role = Column(String(20), nullable=False) 
    
    is_active = Column(Boolean, default=True)
    is_chairman = Column(Boolean, default=False) 
    
    email = Column(String(100), unique=True, nullable=True)
    google_id = Column(String(255), unique=True, nullable=True)
    is_pending = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    reset_token = Column(String(100), nullable=True)
    reset_token_expiry = Column(DateTime, nullable=True)

    scores_given = relationship("Score", back_populates="judge")
    audit_logs = relationship("AuditLog", back_populates="user")

# ---------------------------------------------------------
# 2. EVENTS
# ---------------------------------------------------------
class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False) 
    event_type = Column(String(20), nullable=False) 
    status = Column(String(20), default='Active') 
    is_locked = Column(Boolean, default=False)
    show_public_rankings = Column(Boolean, default=False)
    
    segments = relationship("Segment", back_populates="event")
    contestants = relationship("Contestant", back_populates="event")
    assigned_judges = relationship("EventJudge", back_populates="event")

class Segment(Base):
    __tablename__ = 'segments'
    
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    name = Column(String(100), nullable=False)
    order_index = Column(Integer)
    
    percentage_weight = Column(Float, default=0.0)
    is_active = Column(Boolean, default=False)
    is_revealed = Column(Boolean, default=False) 
    
    is_final = Column(Boolean, default=False) 
    qualifier_limit = Column(Integer, default=0) 

    points_per_question = Column(Integer, default=1)
    total_questions = Column(Integer, default=10)
    
    participating_school_ids = Column(String(255), nullable=True) 
    related_segment_id = Column(Integer, ForeignKey('segments.id'), nullable=True)
    
    event = relationship("Event", back_populates="segments")
    criteria = relationship("Criteria", back_populates="segment")
    
    # This property is named 'scores'
    scores = relationship("Score", back_populates="segment")
    
    children = relationship("Segment", backref=backref('parent', remote_side=[id]))


class Criteria(Base):
    __tablename__ = 'criteria'
    
    id = Column(Integer, primary_key=True)
    segment_id = Column(Integer, ForeignKey('segments.id'))
    name = Column(String(100), nullable=False)
    weight = Column(Float, default=1.0) 
    max_score = Column(Integer, default=10)
    
    segment = relationship("Segment", back_populates="criteria")
    scores = relationship("Score", back_populates="criteria")

# ---------------------------------------------------------
# 3. CONTESTANTS
# ---------------------------------------------------------
class Contestant(Base):
    __tablename__ = 'contestants'
    
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'))
    
    candidate_number = Column(Integer)
    name = Column(String(100), nullable=False)
    gender = Column(String(10)) 
    status = Column(String(20), default='Active') 
    image_path = Column(String(255), nullable=True) 
    assigned_tabulator_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    event = relationship("Event", back_populates="contestants")
    scores = relationship("Score", back_populates="contestant")

# ---------------------------------------------------------
# 4. SCORES & LOGS
# ---------------------------------------------------------
class Score(Base):
    __tablename__ = 'scores'
    
    id = Column(Integer, primary_key=True)
    contestant_id = Column(Integer, ForeignKey('contestants.id'))
    judge_id = Column(Integer, ForeignKey('users.id')) 
    segment_id = Column(Integer, ForeignKey('segments.id'))
    criteria_id = Column(Integer, ForeignKey('criteria.id'), nullable=True) 
    
    score_value = Column(Float, default=0.0) 
    question_number = Column(Integer, nullable=True) 
    is_correct = Column(Boolean, default=False)
    
    contestant = relationship("Contestant", back_populates="scores")
    judge = relationship("User", back_populates="scores_given")
    
    # --- FIXED LINE BELOW ---
    # Was: back_populates="segment" (Wrong, Segment doesn't have 'segment' property)
    # Now: back_populates="scores" (Correct, Segment has 'scores' property)
    segment = relationship("Segment", back_populates="scores")
    
    criteria = relationship("Criteria", back_populates="scores")

class JudgeProgress(Base):
    __tablename__ = 'judge_progress'
    id = Column(Integer, primary_key=True)
    judge_id = Column(Integer, ForeignKey('users.id'))
    segment_id = Column(Integer, ForeignKey('segments.id'))
    is_finished = Column(Boolean, default=False) 

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
from . import db
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint

# User Model (Admin or Tabulator)
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    first_name = db.Column(db.String(150))
    role = db.Column(db.String(50))  # 'admin' or 'tabulator'
    
    # Relationship: One Tabulator can have many Schools (across different events)
    schools_assigned = db.relationship('School', backref='tabulator', lazy=True)

# Event Model
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    is_active = db.Column(db.Boolean, default=False, index=True)
    
    # 'per_round' (default) or 'cumulative'
    scoring_type = db.Column(db.String(50), default='per_round') 
    
    schools = db.relationship('School', backref='event', cascade='all, delete-orphan')
    rounds = db.relationship('Round', backref='event', cascade='all, delete-orphan')

# Round Model
class Round(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    difficulty = db.Column(db.String(50), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, nullable=False)
    
    # Control Logic
    is_active = db.Column(db.Boolean, default=False)
    qualifying_count = db.Column(db.Integer, default=0)
    is_final = db.Column(db.Boolean, default=False)
    
    # Filter for Tie Breakers / Qualifiers (Stores IDs like "1,4,5")
    participating_school_ids = db.Column(db.String(200), nullable=True)
    
    scores = db.relationship('Score', backref='round', cascade='all, delete-orphan')

    # Helper to check if school is allowed in this round
    def is_school_allowed(self, school_id):
        if not self.participating_school_ids:
            return True
        allowed_list = self.participating_school_ids.split(',')
        return str(school_id) in allowed_list

# School Model (The Contestants)
class School(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False) # Removed unique=True
    
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    scores = db.relationship('Score', backref='school', cascade='all, delete-orphan')

    # THIS IS THE FIX:
    # Make name unique ONLY within the same event.
    # Allows "School A" in Event 1 and "School A" in Event 2.
    __table_args__ = (
        UniqueConstraint('name', 'event_id', name='unique_school_per_event'),
    )

# Score Model
class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey('round.id'), nullable=False)
    school_id = db.Column(db.Integer, db.ForeignKey('school.id'), nullable=False)
    question_number = db.Column(db.Integer, nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
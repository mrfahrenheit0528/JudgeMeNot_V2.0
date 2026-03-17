import os
from flask import Flask, render_template, session, redirect, url_for

def create_app(test_config=None):
    # Create and configure the app
    app = Flask(__name__, 
                instance_relative_config=True,
                template_folder='webapp/templates',
                static_folder='webapp/static')
    
    app.config.from_mapping(
        SECRET_KEY='dev',
    )

    if test_config is None:
        # Load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # Load the test config if passed in
        app.config.from_mapping(test_config)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Register Blueprints
    from webapp.python.auth import auth_bp, require_role
    from webapp.python.events import events_bp
    from webapp.python.admin import admin_bp
    from webapp.python.judge import judge_bp  
    from webapp.python.leaderboard import leaderboard_bp 
    from webapp.python.scores import scores_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(judge_bp)          
    app.register_blueprint(leaderboard_bp)                
    app.register_blueprint(scores_bp)  
    
    # Database and Service Imports
    from webapp.python.models import Event, Contestant, EventJudge, Base
    from webapp.python.database import SessionLocal, engine
    from webapp.python.services import calculate_dashboard_progress
    
    # =========================================================
    # CREATE ALL MISSING DATABASE TABLES AUTOMATICALLY
    # =========================================================
    Base.metadata.create_all(bind=engine)
    
    @app.route('/')
    @require_role()
    def index():
        user = session.get('user')
        db = SessionLocal()
        try:
            if user['role'] == 'judge' or user['role'] == 'tabulator':
                # Fetch events assigned to this specific judge
                assignments = db.query(EventJudge).filter(EventJudge.judge_id == user['id']).all()
                assigned_event_ids = [a.event_id for a in assignments]
                
                # Fetch Pageant (Score-Based) Events
                events = db.query(Event).filter(Event.id.in_(assigned_event_ids)).all()
                
                # Fetch Quiz Bee (Point-Based) Events
                pb_assignments = db.query(Contestant).filter(Contestant.assigned_judge_id == user['id']).all()
                pb_event_ids = [c.event_id for c in pb_assignments]
                pb_events = db.query(Event).filter(Event.id.in_(pb_event_ids)).all()
                
                # Combine unique events
                all_assigned_events = list({e.id: e for e in (events + pb_events)}.values())
                
                return render_template('judge_dashboard.html', title="Judge Dashboard", events=all_assigned_events)
                
            # =========================================================
            # ADMIN DASHBOARD 
            # =========================================================
            active_events = db.query(Event).filter(Event.status == 'Ongoing').all()
            active_events_count = len(active_events)
            total_participants = db.query(Contestant).count()
            
            # Fetch the 3 most recently active events for the list
            recent_events = db.query(Event).order_by(Event.last_active.desc()).limit(3).all()
            
            # Offload heavy progress calculations to the external service engine
            global_progress_pct, event_progress = calculate_dashboard_progress(db, active_events, recent_events)

            return render_template('index.html', 
                                   title="Dashboard", 
                                   events=recent_events,
                                   active_events_count=active_events_count,
                                   total_participants=total_participants,
                                   global_progress_pct=global_progress_pct,
                                   event_progress=event_progress)
        finally:
            db.close()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
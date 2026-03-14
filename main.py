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
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(admin_bp)

    @app.route('/leaderboard')
    def leaderboard():
        return render_template('leaderboard.html')

    @app.route('/')
    @require_role()
    def index():
        user = session.get('user')
        if user['role'] == 'judge':
            return "Judge Dashboard Placeholder"
        elif user['role'] == 'tabulator':
            return "Tabulator Dashboard Placeholder"
            
        # Admin / Admin-Viewer scope
        from webapp.python.database import SessionLocal
        from webapp.python.models import Event, Contestant
        db = SessionLocal()
        try:
            events = db.query(Event).all()
            # Active events calculation strictly based on Event status
            active_events_count = sum(1 for e in events if e.status == 'Ongoing')
            total_participants = db.query(Contestant).count()
            
            return render_template('index.html', 
                                   title="Dashboard", 
                                   events=events,
                                   active_events_count=active_events_count,
                                   total_participants=total_participants)
        finally:
            db.close()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
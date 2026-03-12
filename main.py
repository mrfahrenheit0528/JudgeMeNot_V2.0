import os
from flask import Flask, render_template

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
    app.register_blueprint(auth_bp)

    @app.route('/')
    @require_role()
    def index():
        return render_template('index.html', title="Dashboard")

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
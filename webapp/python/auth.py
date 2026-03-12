import bcrypt
from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, request, flash, redirect, url_for, session

from webapp.python.database import SessionLocal
from webapp.python.models import User, AuditLog

auth_bp = Blueprint('auth', __name__)

def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    password_raw = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_raw, salt).decode('utf-8')

def check_password(hashed_password: str, plain_password: str) -> bool:
    """Checks a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def authenticate_user(username: str, password: str):
    """
    Attempts to connect and authenticate a user by querying the database.
    Returns (User, error_message).
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None, "Invalid username or password"
            
        if not user.is_active:
            return None, "Account is disabled. Please contact an administrator."
            
        if check_password(user.password_hash, password):
            # Log successful login
            log = AuditLog(user_id=user.id, action="LOGIN", details=f"User '{user.username}' logged in successfully.")
            db.add(log)
            db.commit()
            
            # We return a detached instance (or dict) to avoid SQLAlchemy session issues in Flet
            # but for simplicity, we retrieve the row data
            user_data = {
                "id": user.id,
                "username": user.username,
                "name": user.name,
                "role": user.role,
                "is_chairman": user.is_chairman
            }
            return user_data, None
            
        else:
            return None, "Invalid username or password"
    except Exception as e:
        return None, f"Database error: {str(e)}"
    finally:
        db.close()

def require_role(allowed_roles=None):
    """
    Decorator for Flask routes to check if current user in session has permission to view a page.
    Call this on protected view functions using @require_role(["admin"]).
    """
    if allowed_roles is None:
        allowed_roles = []
        
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            if not user:
                return redirect(url_for('auth.login'))
                
            if allowed_roles and user.get('role') not in allowed_roles:
                print(f"Unauthorized access attempt by {user.get('username')} to require_role {allowed_roles}")
                flash("You do not have permission to view this page.", "error")
                return redirect(url_for('index'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_data, error = authenticate_user(username, password)
        if error:
            flash(error, "error")
        else:
            session['user'] = user_data
            return redirect(url_for('index'))
            
    # Redirect if already logged in
    if session.get('user'):
        return redirect(url_for('index'))
        
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("You have been successfully logged out.", "success")
    return redirect(url_for('auth.login'))

def log_audit_action(user_id: int, action: str, details: str):
    """Utility to quickly record an audit log"""
    db = SessionLocal()
    try:
        log = AuditLog(user_id=user_id, action=action, details=details, timestamp=datetime.now())
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"Failed to write audit log: {e}")
    finally:
        db.close()

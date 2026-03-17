from flask import Blueprint, render_template, request, flash, redirect, url_for
from webapp.python.auth import require_role, hash_password
from webapp.python.database import SessionLocal
from webapp.python.models import Event, User, AuditLog
import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def get_local_ip():
    """Fetches the local LAN IP address so devices on the same network can connect."""
    import socket
    try:
        # Create a dummy socket to connect to an external IP to get the local IP used for routing
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

@admin_bp.route('/events')
@require_role(['admin', 'admin-viewer']) 
def events():
    db = SessionLocal()
    try:
        # Order by newest created/launched
        all_events = db.query(Event).order_by(Event.id.desc()).all()
        return render_template('admin_events.html', events=all_events)
    finally:
        db.close()

@admin_bp.route('/users')
@require_role(['admin', 'admin-viewer']) 
def users():
    db = SessionLocal()
    try:
        all_users = db.query(User).order_by(User.role, User.name).all()
        return render_template('admin_users.html', users=all_users)
    finally:
        db.close()

@admin_bp.route('/users/add', methods=['POST'])
@require_role(['admin'])
def add_user():
    name = request.form.get('name')
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == username).first():
            flash("Username already exists. Please choose a different one.", "error")
            return redirect(url_for('admin.users'))
            
        hashed_pw = hash_password(password)
        new_user = User(username=username, name=name, password_hash=hashed_pw, role=role)
        db.add(new_user)
        db.commit()
        flash(f"User account '{username}' created successfully.", "success")
    except Exception as e:
        flash(f"Error creating user: {str(e)}", "error")
    finally:
        db.close()
        
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/edit/<int:user_id>', methods=['POST'])
@require_role(['admin'])
def edit_user(user_id):
    name = request.form.get('name')
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            flash("User not found.", "error")
            return redirect(url_for('admin.users'))
            
        # Prevent renaming username to one that already exists
        existing = db.query(User).filter(User.username == username, User.id != user_id).first()
        if existing:
            flash("That username is already taken by another account.", "error")
            return redirect(url_for('admin.users'))
            
        user.name = name
        user.username = username
        user.role = role
        
        # Only update password if a new one was provided
        if password and password.strip() != "":
            user.password_hash = hash_password(password)
            
        db.commit()
        flash(f"User '{username}' updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating user: {str(e)}", "error")
    finally:
        db.close()
        
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@require_role(['admin'])
def delete_user(user_id):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            if user.username == 'admin':
                flash("Cannot delete the primary admin account.", "error")
            else:
                db.delete(user)
                db.commit()
                flash("User deleted successfully.", "success")
        else:
            flash("User not found.", "error")
    finally:
        db.close()
    return redirect(url_for('admin.users'))

@admin_bp.route('/logs')
@require_role(['admin', 'admin-viewer'])
def logs():
    db = SessionLocal()
    try:
        # Fetch the most recent 150 logs to prevent massive page load times
        audit_logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(150).all()
        return render_template('admin_logs.html', logs=audit_logs)
    finally:
        db.close()

@admin_bp.route('/settings')
@require_role(['admin', 'admin-viewer'])
def settings():
    import io
    import base64
    
    try:
        import qrcode
        
        # Determine the URL for the QR code
        # If running locally (localhost), use the LAN IP so other devices can connect
        if 'localhost' in request.host or '127.0.0.1' in request.host:
            local_ip = get_local_ip()
            url = f"http://{local_ip}:5000"
        else:
            # If running on cloud or accessed via IP, use the current host URL
            url = request.url_root.rstrip('/')
            
        # Generate QR Code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64 for embedding directly in the HTML
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
    except ImportError:
        img_str = None
        url = "Dependencies missing: run 'pip install qrcode pillow'"
        flash("Please install 'qrcode' and 'Pillow' packages to view the connection QR code.", "error")

    return render_template('admin_settings.html', qr_code=img_str, url=url)
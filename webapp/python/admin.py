from flask import Blueprint, render_template, request, flash, redirect, url_for
from webapp.python.auth import require_role, hash_password
from webapp.python.database import SessionLocal
from webapp.python.models import Event, User, AuditLog
import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/events')
@require_role(['admin'])
def events():
    db = SessionLocal()
    try:
        # Order by newest created/launched
        all_events = db.query(Event).order_by(Event.id.desc()).all()
        return render_template('admin_events.html', events=all_events)
    finally:
        db.close()

@admin_bp.route('/users')
@require_role(['admin'])
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
@require_role(['admin'])
def logs():
    db = SessionLocal()
    try:
        # Fetch the most recent 150 logs to prevent massive page load times
        audit_logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(150).all()
        return render_template('admin_logs.html', logs=audit_logs)
    finally:
        db.close()

@admin_bp.route('/settings')
@require_role(['admin'])
def settings():
    return render_template('admin_settings.html')
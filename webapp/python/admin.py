from flask import Blueprint, render_template
from webapp.python.auth import require_role

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/criteria')
@require_role(['admin'])
def criteria():
    return render_template('admin_criteria.html')

@admin_bp.route('/judges')
@require_role(['admin'])
def judges():
    return render_template('admin_judges.html')

@admin_bp.route('/settings')
@require_role(['admin'])
def settings():
    return render_template('admin_settings.html')

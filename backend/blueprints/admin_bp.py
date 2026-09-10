"""
System Administrator & Support Panel Blueprint
Provides platform-level tenant management, verification reviews, system-wide statistics,
global security audit trail inspection, and support management.
"""

from flask import Blueprint, request, jsonify
from backend.database import get_db_connection
from backend.services.audit_service import AuditService

admin_bp = Blueprint('admin', __name__, url_prefix='/api/v1/admin')

def require_sysadmin():
    user_role = request.headers.get('X-User-Role')
    if user_role != 'SYSTEM_ADMIN':
        return False
    return True

@admin_bp.route('/stats', methods=['GET'])
def get_platform_stats():
    """Returns platform super-admin global KPIs."""
    if not require_sysadmin():
        return jsonify({"error": "Unauthorized. Requires SYSTEM_ADMIN role."}), 403

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as cnt FROM organizations")
    total_orgs = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) as cnt FROM users")
    total_users = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) as cnt FROM borrowers")
    total_borrowers = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(principal_amount), 0.0) as sum_p FROM loans")
    loan_stats = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) as cnt FROM audit_logs")
    total_audits = cursor.fetchone()['cnt']

    conn.close()

    return jsonify({
        "total_organizations": total_orgs,
        "total_users": total_users,
        "total_borrowers": total_borrowers,
        "total_loans_disbursed": loan_stats['cnt'],
        "total_portfolio_volume": float(loan_stats['sum_p']),
        "total_audit_events": total_audits
    }), 200

@admin_bp.route('/organizations', methods=['GET'])
def list_organizations():
    """Lists all registered financier organizations."""
    if not require_sysadmin():
        return jsonify({"error": "Unauthorized. Requires SYSTEM_ADMIN role."}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT o.*, COUNT(l.id) as total_loans
        FROM organizations o
        LEFT JOIN loans l ON o.id = l.org_id
        GROUP BY o.id
        ORDER BY o.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    return jsonify([dict(r) for r in rows]), 200

@admin_bp.route('/organizations/<org_id>/verify', methods=['POST'])
def update_org_verification(org_id):
    """Updates verification status for a tenant organization."""
    if not require_sysadmin():
        return jsonify({"error": "Unauthorized. Requires SYSTEM_ADMIN role."}), 403

    data = request.json or {}
    status = data.get('status', 'VERIFIED') # VERIFIED, SUSPENDED, PENDING

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE organizations SET verification_status = ? WHERE id = ?", (status, org_id))
    conn.commit()
    conn.close()

    admin_user_id = request.headers.get('X-User-Id', 'user_admin')
    AuditService.log(org_id, admin_user_id, 'UPDATE_ORG_STATUS', 'ORGANIZATION', org_id, new_state=status)

    return jsonify({"message": f"Organization status updated to {status}."}), 200

@admin_bp.route('/global-audit-logs', methods=['GET'])
def get_global_audit_logs():
    """Returns platform-wide audit log trail."""
    if not require_sysadmin():
        return jsonify({"error": "Unauthorized. Requires SYSTEM_ADMIN role."}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.*, u.full_name as user_name, u.role as user_role, o.name as org_name
        FROM audit_logs a
        LEFT JOIN users u ON a.user_id = u.id
        LEFT JOIN organizations o ON a.org_id = o.id
        ORDER BY a.created_at DESC LIMIT 100
    """)
    rows = cursor.fetchall()
    conn.close()

    return jsonify([dict(r) for r in rows]), 200

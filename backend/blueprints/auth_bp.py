"""
Authentication & User Management Blueprint
Handles Financier business registration, login, session tokens, and user profiles.
"""

from flask import Blueprint, request, jsonify
import uuid
import datetime
from backend.database import get_db_connection, hash_password
from backend.services.audit_service import AuditService

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')

@auth_bp.route('/register', methods=['POST'])
def register_financier():
    """Onboards a new financier organization and owner user account."""
    data = request.json or {}
    org_name = data.get('org_name')
    reg_number = data.get('reg_number', f"REG-{uuid.uuid4().hex[:6].upper()}")
    email = data.get('email')
    phone = data.get('phone')
    address = data.get('address', '')
    owner_name = data.get('owner_name')
    password = data.get('password')

    if not org_name or not email or not phone or not password or not owner_name:
        return jsonify({"error": "Missing required fields for registration."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if email/phone exists
        cursor.execute("SELECT id FROM users WHERE email = ? OR phone = ?", (email, phone))
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "User with this email or mobile number already exists."}), 400

        org_id = f"org_{uuid.uuid4().hex[:10]}"
        cursor.execute("""
            INSERT INTO organizations (id, name, registration_number, email, phone, address, verification_status)
            VALUES (?, ?, ?, ?, ?, ?, 'VERIFIED')
        """, (org_id, org_name, reg_number, email, phone, address))

        user_id = f"user_{uuid.uuid4().hex[:10]}"
        cursor.execute("""
            INSERT INTO users (id, org_id, role, full_name, email, phone, password_hash, status)
            VALUES (?, ?, 'FINANCIER_OWNER', ?, ?, ?, ?, 'ACTIVE')
        """, (user_id, org_id, owner_name, email, phone, hash_password(password)))

        conn.commit()
        conn.close()

        AuditService.log(org_id, user_id, 'REGISTER_ORGANIZATION', 'ORGANIZATION', org_id, new_state=org_name)

        return jsonify({
            "message": "Organization registered successfully.",
            "user": {
                "id": user_id,
                "org_id": org_id,
                "org_name": org_name,
                "full_name": owner_name,
                "email": email,
                "phone": phone,
                "role": "FINANCIER_OWNER"
            }
        }), 201
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"Registration failed: {str(e)}"}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticates user and returns profile."""
    data = request.json or {}
    identifier = data.get('identifier') # email or phone
    password = data.get('password')

    if not identifier or not password:
        return jsonify({"error": "Identifier and password required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.*, o.name as org_name
        FROM users u
        LEFT JOIN organizations o ON u.org_id = o.id
        WHERE (u.email = ? OR u.phone = ?) AND u.password_hash = ?
    """, (identifier, identifier, hash_password(password)))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "Invalid credentials."}), 401

    if user['status'] != 'ACTIVE':
        return jsonify({"error": "Account deactivated. Contact administrator."}), 403

    user_dict = {
        "id": user['id'],
        "org_id": user['org_id'],
        "org_name": user['org_name'] or "System Administrator",
        "full_name": user['full_name'],
        "email": user['email'],
        "phone": user['phone'],
        "role": user['role']
    }

    AuditService.log(user['org_id'], user['id'], 'LOGIN_SUCCESS', 'USER', user['id'])

    return jsonify({
        "message": "Login successful.",
        "user": user_dict,
        "token": f"token_simulated_{user['id']}"
    }), 200

@auth_bp.route('/users', methods=['GET'])
def list_users():
    """Lists users for the active tenant organization."""
    org_id = request.headers.get('X-Org-Id')
    if not org_id:
        return jsonify({"error": "Organization header required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, org_id, role, full_name, email, phone, status, created_at FROM users WHERE org_id = ?", (org_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows]), 200

@auth_bp.route('/profile', methods=['GET'])
def get_profile():
    """Fetches user and organization profile details."""
    user_id = request.headers.get('X-User-Id')
    org_id = request.headers.get('X-Org-Id')

    if not user_id:
        return jsonify({"error": "User ID header required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id as user_id, u.full_name, u.email, u.phone, u.role, u.status, u.created_at,
               o.id as org_id, o.name as org_name, o.registration_number, o.email as org_email,
               o.phone as org_phone, o.address as org_address
        FROM users u
        LEFT JOIN organizations o ON u.org_id = o.id
        WHERE u.id = ?
    """, (user_id,))
    prof = cursor.fetchone()
    conn.close()

    if not prof:
        return jsonify({"error": "Profile not found."}), 404

    return jsonify(dict(prof)), 200

@auth_bp.route('/profile', methods=['PUT'])
def update_profile():
    """Updates user and organization profile details."""
    user_id = request.headers.get('X-User-Id')
    org_id = request.headers.get('X-Org-Id')

    if not user_id:
        return jsonify({"error": "User ID header required."}), 400

    data = request.json or {}
    full_name = data.get('full_name')
    email = data.get('email')
    phone = data.get('phone')
    org_name = data.get('org_name')
    org_address = data.get('org_address')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if full_name or email or phone:
            cursor.execute("""
                UPDATE users
                SET full_name = COALESCE(?, full_name),
                    email = COALESCE(?, email),
                    phone = COALESCE(?, phone)
                WHERE id = ?
            """, (full_name, email, phone, user_id))

        if org_id and (org_name or org_address):
            cursor.execute("""
                UPDATE organizations
                SET name = COALESCE(?, name),
                    address = COALESCE(?, address)
                WHERE id = ?
            """, (org_name, org_address, org_id))

        conn.commit()
        conn.close()

        AuditService.log(org_id, user_id, 'UPDATE_PROFILE', 'USER', user_id, new_state=full_name)
        return jsonify({"message": "Profile updated successfully."}), 200
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"Profile update failed: {str(e)}"}), 500


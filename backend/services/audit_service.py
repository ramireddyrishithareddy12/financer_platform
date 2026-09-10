"""
Audit Service Module
Provides immutable audit trail creation and lookup.
"""

import uuid
import datetime
from backend.database import get_db_connection

class AuditService:
    @staticmethod
    def log(org_id: str | None, user_id: str | None, action: str, entity_type: str, entity_id: str, previous_state: str | None = None, new_state: str | None = None, ip_address: str = "127.0.0.1"):
        """Logs an event into the audit trail table."""
        conn = get_db_connection()
        cursor = conn.cursor()
        audit_id = f"aud_{uuid.uuid4().hex[:12]}"
        
        cursor.execute("""
            INSERT INTO audit_logs (id, org_id, user_id, action, entity_type, entity_id, previous_state, new_state, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (audit_id, org_id, user_id, action, entity_type, entity_id, previous_state, new_state, ip_address))
        
        conn.commit()
        conn.close()
        return audit_id

    @staticmethod
    def get_logs(org_id: str, limit: int = 50):
        """Fetches audit logs for an organization."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, u.full_name as user_name, u.role as user_role
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            WHERE a.org_id = ? OR a.org_id IS NULL
            ORDER BY a.created_at DESC
            LIMIT ?
        """, (org_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

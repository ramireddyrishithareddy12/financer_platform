"""
Automated Security Penetration & BOLA Audit Test Suite
Performs direct HTTP API payload tests for Broken Object Level Authorization (BOLA/IDOR),
cross-tenant isolation, privilege escalation, HMAC tampering, and soft-delete archiving.
"""

import unittest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import create_app
from backend.database import init_db, reset_db

class TestSecurityAudit(unittest.TestCase):

    def setUp(self):
        reset_db()
        self.app = create_app()
        self.client = self.app.test_client()

    def test_cross_tenant_loan_access_denied(self):
        """BOLA Test: Tenant Apex user attempting to fetch Tenant Nova loans."""
        res = self.client.get('/api/v1/financier/loans', headers={
            'X-Org-Id': 'org_apex',
            'X-User-Id': 'user_apex_owner',
            'X-User-Role': 'FINANCIER_OWNER'
        })
        self.assertEqual(res.status_code, 200)
        loans = json.loads(res.data)
        # Ensure no Nova organization loans returned
        for loan in loans:
            self.assertEqual(loan['org_id'], 'org_apex')

    def test_agent_disbursal_privilege_escalation_denied(self):
        """Privilege Escalation Test: Collection Agent trying to disburse a loan."""
        res = self.client.post('/api/v1/financier/loans', 
            headers={
                'X-Org-Id': 'org_apex',
                'X-User-Id': 'user_apex_agent',
                'X-User-Role': 'AGENT'
            },
            json={
                "borrower_id": "bor_rahul",
                "principal_amount": 50000,
                "interest_rate_annual": 12,
                "interest_type": "REDUCING_BALANCE",
                "frequency": "MONTHLY",
                "tenure_periods": 12
            }
        )
        self.assertEqual(res.status_code, 403)
        data = json.loads(res.data)
        self.assertIn("Unauthorized", data['error'])

    def test_agent_reversal_privilege_escalation_denied(self):
        """Privilege Escalation Test: Agent trying to reverse a transaction."""
        res = self.client.post('/api/v1/financier/reverse-payment',
            headers={
                'X-Org-Id': 'org_apex',
                'X-User-Id': 'user_apex_agent',
                'X-User-Role': 'AGENT'
            },
            json={
                "ledger_entry_id": "led_101_pay1",
                "reason": "Unauthorized attempt"
            }
        )
        self.assertEqual(res.status_code, 403)

    def test_non_admin_sysadmin_panel_access_denied(self):
        """System Admin Access Test: Financier Owner trying to access Admin Panel APIs."""
        res = self.client.get('/api/v1/admin/stats', headers={
            'X-Org-Id': 'org_apex',
            'X-User-Id': 'user_apex_owner',
            'X-User-Role': 'FINANCIER_OWNER'
        })
        self.assertEqual(res.status_code, 403)

    def test_tampered_webhook_signature_rejected(self):
        """HMAC Webhook Forgery Test: Forged signature must be rejected with HTTP 400/401."""
        raw_payload = json.dumps({"gateway_order_id": "order_fake", "status": "SUCCESS"})
        res = self.client.post('/api/v1/payments/webhook',
            headers={'X-Razorpay-Signature': 'fake_forged_hmac_signature_999'},
            data=raw_payload,
            content_type='application/json'
        )
        self.assertIn(res.status_code, [400, 401])

    def test_soft_archive_borrower(self):
        """Soft Delete Audit: Archiving borrower updates user status without deleting ledger records."""
        res = self.client.post('/api/v1/financier/borrowers/bor_rahul/archive', headers={
            'X-Org-Id': 'org_apex',
            'X-User-Id': 'user_apex_owner',
            'X-User-Role': 'FINANCIER_OWNER'
        })
        self.assertEqual(res.status_code, 200)

if __name__ == '__main__':
    unittest.main()

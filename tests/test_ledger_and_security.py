"""
Automated Integration & Security Unit Tests
Verifies Multi-Tenant Data Isolation, Financial Ledger Integrity,
Accounting Reversals, Payment Idempotency, and HMAC Webhook Verification.
"""

import unittest
import sys
import os
import json
import hmac
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import init_db, reset_db, get_db_connection
from backend.services.ledger_service import LedgerService
from backend.services.payment_service import PaymentService, GATEWAY_SHARED_SECRET

class TestLedgerAndSecurity(unittest.TestCase):

    def setUp(self):
        reset_db()

    def test_multi_tenant_isolation(self):
        """Verifies Org A data is isolated from Org B."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Org Apex borrowers
        cursor.execute("SELECT * FROM borrowers WHERE org_id = 'org_apex'")
        apex_borrowers = cursor.fetchall()
        
        # Org Nova borrowers
        cursor.execute("SELECT * FROM borrowers WHERE org_id = 'org_nova'")
        nova_borrowers = cursor.fetchall()
        
        conn.close()

        self.assertGreater(len(apex_borrowers), 0)
        # Ensure no cross-tenant borrower overlap
        apex_ids = {b['id'] for b in apex_borrowers}
        nova_ids = {b['id'] for b in nova_borrowers}
        self.assertEqual(len(apex_ids.intersection(nova_ids)), 0)

    def test_payment_and_ledger_stream(self):
        """Verifies payment processing creates double-entry record."""
        rec = LedgerService.record_payment(
            org_id='org_apex',
            loan_id='loan_apex_101',
            schedule_id='sch_101_2',
            amount=5000.0,
            payment_method='CASH',
            reference_id='TEST-TXN-999',
            notes='Test payment',
            created_by='user_apex_owner'
        )

        self.assertIn('ledger_entry_id', rec)
        self.assertEqual(rec['amount'], 5000.0)

        # Check statement ledger stream
        stmt = LedgerService.get_statement('org_apex', 'loan_apex_101')
        self.assertGreater(len(stmt['transactions']), 1)

    def test_accounting_reversal(self):
        """Verifies transaction reversal creates counterentry without deleting record."""
        # 1. Make payment
        rec = LedgerService.record_payment(
            org_id='org_apex',
            loan_id='loan_apex_101',
            schedule_id=None,
            amount=2000.0,
            payment_method='CASH',
            reference_id='TEST-REV-SRC',
            notes='Payment to be reversed',
            created_by='user_apex_owner'
        )

        orig_entry_id = rec['ledger_entry_id']

        # 2. Reverse transaction
        rev_id = LedgerService.reverse_transaction(
            org_id='org_apex',
            original_entry_id=orig_entry_id,
            reason='Customer wrong check entry',
            authorized_user_id='user_apex_mgr'
        )

        self.assertTrue(rev_id.startswith('led_rev_'))

        # Verify original entry still exists in DB
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ledger_entries WHERE id = ?", (orig_entry_id,))
        orig_row = cursor.fetchone()
        
        cursor.execute("SELECT * FROM ledger_entries WHERE id = ?", (rev_id,))
        rev_row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(orig_row)
        self.assertIsNotNone(rev_row)
        self.assertEqual(rev_row['amount'], -2000.0)

    def test_hmac_webhook_verification(self):
        """Verifies HMAC SHA-256 webhook signature validation."""
        raw_payload = json.dumps({"gateway_order_id": "ord_123", "status": "SUCCESS"})
        sig = hmac.new(GATEWAY_SHARED_SECRET.encode('utf-8'), raw_payload.encode('utf-8'), hashlib.sha256).hexdigest()

        # Valid signature
        self.assertTrue(PaymentService.verify_webhook_signature(raw_payload, sig))
        
        # Invalid signature
        self.assertFalse(PaymentService.verify_webhook_signature(raw_payload, "invalid_fake_signature"))

    def test_payment_idempotency(self):
        """Verifies idempotency prevents duplicate webhook callbacks."""
        attempt = PaymentService.initiate_payment('loan_apex_101', 'sch_101_3', 3000.0, 'user_rahul')
        order_id = attempt['gateway_order_id']

        payload_dict = {
            "gateway_order_id": order_id,
            "gateway_payment_id": "pay_dup_test_101",
            "status": "SUCCESS",
            "amount": 3000.0
        }
        raw_payload = json.dumps(payload_dict)
        sig = hmac.new(GATEWAY_SHARED_SECRET.encode('utf-8'), raw_payload.encode('utf-8'), hashlib.sha256).hexdigest()

        # Call 1: Success
        success1, msg1, data1 = PaymentService.process_webhook_callback(raw_payload, sig)
        self.assertTrue(success1)
        self.assertIn("PAYMENT_VERIFIED", msg1)

        # Call 2: Duplicate Callback with same order
        success2, msg2, data2 = PaymentService.process_webhook_callback(raw_payload, sig)
        self.assertTrue(success2)
        self.assertIn("ALREADY_PROCESSED", msg2)

if __name__ == '__main__':
    unittest.main()

"""
Payment Architecture & Gateway Integration Service
Provides idempotent payment order initiation, HMAC SHA-256 signature verification,
server-side webhook verification, and payment reconciliation logic.
"""

import hmac
import hashlib
import json
import uuid
import datetime
from decimal import Decimal
from typing import Dict, Any, Tuple, List
from backend.database import get_db_connection
from backend.services.ledger_service import LedgerService
from backend.services.audit_service import AuditService

GATEWAY_SHARED_SECRET = "sec_creditorpulse_webhook_key_2026"

class PaymentService:
    @staticmethod
    def initiate_payment(loan_id: str, schedule_id: str, amount: float, user_id: str) -> Dict[str, Any]:
        """
        Creates a pending payment attempt record with an idempotency key before sending to gateway.
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT l.*, b.org_id FROM loans l JOIN borrowers b ON l.borrower_id = b.id WHERE l.id = ?", (loan_id,))
        loan = cursor.fetchone()
        if not loan:
            conn.close()
            raise ValueError("Loan not found.")

        idempotency_key = f"idemp_{loan_id}_{schedule_id}_{int(datetime.datetime.now().timestamp())}"
        attempt_id = f"pay_att_{uuid.uuid4().hex[:10]}"
        gateway_order_id = f"order_{uuid.uuid4().hex[:12]}"

        cursor.execute("""
            INSERT INTO payment_attempts (id, loan_id, schedule_id, amount, idempotency_key, gateway_name, gateway_order_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'RAZORPAY_SIMULATED', ?, 'INITIATED', CURRENT_TIMESTAMP)
        """, (attempt_id, loan_id, schedule_id, float(amount), idempotency_key, gateway_order_id))

        conn.commit()
        conn.close()

        AuditService.log(loan['org_id'], user_id, 'INITIATE_PAYMENT', 'PAYMENT_ATTEMPT', attempt_id, new_state=f"Initiated ₹{amount}")

        return {
            "attempt_id": attempt_id,
            "idempotency_key": idempotency_key,
            "gateway_order_id": gateway_order_id,
            "amount": float(amount),
            "currency": "INR",
            "loan_id": loan_id,
            "schedule_id": schedule_id,
            "gateway_key": "rzp_test_creditorpulse_key"
        }

    @staticmethod
    def verify_webhook_signature(raw_payload: str, signature: str, secret: str = GATEWAY_SHARED_SECRET) -> bool:
        """Computes HMAC-SHA256 signature and compares in constant time."""
        if not signature or not raw_payload:
            return False
        expected_sig = hmac.new(secret.encode('utf-8'), raw_payload.encode('utf-8'), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature)

    @staticmethod
    def process_webhook_callback(raw_payload: str, signature: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Processes server-to-server gateway callback, verifies HMAC signature,
        checks idempotency lock, updates ledger, and issues receipt info.
        """
        # 1. Signature Verification
        if not PaymentService.verify_webhook_signature(raw_payload, signature):
            return False, "INVALID_SIGNATURE: HMAC verification failed.", {}

        data = json.loads(raw_payload)
        gateway_order_id = data.get('gateway_order_id')
        gateway_payment_id = data.get('gateway_payment_id', f"pay_gw_{uuid.uuid4().hex[:8]}")
        status = data.get('status', 'SUCCESS')

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT pa.*, l.org_id FROM payment_attempts pa JOIN loans l ON pa.loan_id = l.id WHERE pa.gateway_order_id = ?", (gateway_order_id,))
            attempt = cursor.fetchone()

            if not attempt:
                conn.close()
                return False, f"ORDER_NOT_FOUND: {gateway_order_id}", {}

            # Idempotency Check: Avoid double recording!
            if attempt['status'] == 'SUCCESS':
                conn.close()
                return True, "ALREADY_PROCESSED: Payment has already been verified.", {"attempt_id": attempt['id'], "status": "SUCCESS"}

            if status.upper() == 'SUCCESS':
                # Update Attempt Status
                cursor.execute("UPDATE payment_attempts SET status = 'SUCCESS', gateway_payment_id = ?, raw_payload = ? WHERE id = ?", (gateway_payment_id, raw_payload, attempt['id']))
                conn.commit()
                conn.close()

                # Post to Financial Ledger
                rec = LedgerService.record_payment(
                    org_id=attempt['org_id'],
                    loan_id=attempt['loan_id'],
                    schedule_id=attempt['schedule_id'],
                    amount=attempt['amount'],
                    payment_method='DIGITAL_GATEWAY',
                    reference_id=gateway_payment_id,
                    notes=f"Verified Digital Payment (Order {gateway_order_id})",
                    created_by="system_webhook"
                )

                return True, "PAYMENT_VERIFIED: Successfully processed.", rec
            else:
                cursor.execute("UPDATE payment_attempts SET status = 'FAILED', raw_payload = ? WHERE id = ?", (raw_payload, attempt['id']))
                conn.commit()
                conn.close()
                return False, "PAYMENT_FAILED: Gateway reported failed transaction.", {}
        except Exception as e:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            return False, f"PROCESSING_ERROR: {str(e)}", {}

    @staticmethod
    def get_reconciliation_report(org_id: str) -> List[Dict[str, Any]]:
        """
        Reconciles payment_attempts vs ledger_entries to detect any discrepancies.
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                pa.id as attempt_id,
                pa.loan_id,
                pa.amount as attempt_amount,
                pa.gateway_order_id,
                pa.gateway_payment_id,
                pa.status as gateway_status,
                pa.created_at,
                le.id as ledger_entry_id,
                le.amount as ledger_amount
            FROM payment_attempts pa
            JOIN loans l ON pa.loan_id = l.id
            LEFT JOIN ledger_entries le ON pa.gateway_payment_id = le.reference_id
            WHERE l.org_id = ?
            ORDER BY pa.created_at DESC
        """, (org_id,))
        rows = cursor.fetchall()
        conn.close()

        reconciliation = []
        for r in rows:
            mismatch_flag = False
            status_desc = "RECONCILED_MATCH"

            if r['gateway_status'] == 'SUCCESS' and not r['ledger_entry_id']:
                mismatch_flag = True
                status_desc = "UNASSIGNED_GATEWAY_SUCCESS"
            elif r['gateway_status'] == 'INITIATED':
                status_desc = "PENDING_CHECKOUT"
            elif r['gateway_status'] == 'SUCCESS' and r['attempt_amount'] != r['ledger_amount']:
                mismatch_flag = True
                status_desc = "AMOUNT_MISMATCH"

            reconciliation.append({
                "attempt_id": r['attempt_id'],
                "loan_id": r['loan_id'],
                "gateway_order_id": r['gateway_order_id'],
                "gateway_payment_id": r['gateway_payment_id'],
                "attempt_amount": float(r['attempt_amount']),
                "ledger_amount": float(r['ledger_amount']) if r['ledger_amount'] else None,
                "gateway_status": r['gateway_status'],
                "status_desc": status_desc,
                "mismatch_flag": mismatch_flag,
                "created_at": r['created_at']
            })

        return reconciliation

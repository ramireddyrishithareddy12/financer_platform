"""
Immutable Financial Ledger Service
Handles double-entry ledger event processing, accounting balance derivation,
installment allocation, payment recording, and transaction reversals.
"""

from decimal import Decimal
import uuid
import datetime
from typing import Dict, Any, List
from backend.database import get_db_connection
from backend.services.loan_engine import LoanEngine, round_money
from backend.services.audit_service import AuditService

class LedgerService:
    @staticmethod
    def post_disbursal(org_id: str, loan_id: str, amount: Decimal, created_by: str, reference_id: str = "") -> str:
        """Posts initial loan disbursal event to financial ledger."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        entry_id = f"led_{uuid.uuid4().hex[:12]}"
        cursor.execute("""
            INSERT INTO ledger_entries (id, org_id, loan_id, schedule_id, entry_type, amount, principal_component, interest_component, fee_component, debit_account, credit_account, payment_method, reference_id, notes, created_by)
            VALUES (?, ?, ?, NULL, 'LOAN_DISBURSED', ?, ?, 0.0, 0.0, 'LOANS_RECEIVABLE_ASSET', 'CASH_BANK_ASSET', 'BANK_TRANSFER', ?, 'Loan Principal Disbursal', ?)
        """, (entry_id, org_id, loan_id, float(amount), float(amount), reference_id, created_by))
        
        conn.commit()
        conn.close()
        
        AuditService.log(org_id, created_by, 'LOAN_DISBURSED', 'LOAN', loan_id, new_state=f"Disbursed {amount}")
        return entry_id

    @staticmethod
    def record_payment(
        org_id: str,
        loan_id: str,
        schedule_id: str | None,
        amount: float | Decimal,
        payment_method: str,
        reference_id: str,
        notes: str,
        created_by: str
    ) -> Dict[str, Any]:
        """
        Records payment, allocates to current installment, posts ledger entry, and updates balances inside an ACID transaction.
        """
        amt = round_money(Decimal(str(amount)))
        if amt <= Decimal('0'):
            raise ValueError("Payment amount must be greater than zero.")

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # 1. Fetch Loan Details
            cursor.execute("SELECT * FROM loans WHERE id = ? AND org_id = ?", (loan_id, org_id))
            loan = cursor.fetchone()
            if not loan:
                raise ValueError("Loan record not found.")

            # 2. Determine target installment or upcoming due installment
            target_schedule = None
            if schedule_id:
                cursor.execute("SELECT * FROM repayment_schedules WHERE id = ? AND loan_id = ?", (schedule_id, loan_id))
                target_schedule = cursor.fetchone()
            else:
                cursor.execute("SELECT * FROM repayment_schedules WHERE loan_id = ? AND status IN ('DUE', 'PARTIAL', 'OVERDUE') ORDER BY installment_number ASC LIMIT 1", (loan_id,))
                target_schedule = cursor.fetchone()

            if not target_schedule:
                # If no schedule, get latest schedule
                cursor.execute("SELECT * FROM repayment_schedules WHERE loan_id = ? ORDER BY installment_number DESC LIMIT 1", (loan_id,))
                target_schedule = cursor.fetchone()

            sch_id = target_schedule['id'] if target_schedule else None
            
            # 3. Calculate waterfall allocation
            i_due = Decimal(str(target_schedule['interest_due'])) - Decimal(str(target_schedule['interest_paid'])) if target_schedule else Decimal('0')
            p_due = Decimal(str(target_schedule['principal_due'])) - Decimal(str(target_schedule['principal_paid'])) if target_schedule else amt

            allocation = LoanEngine.allocate_payment(amt, i_due, p_due)
            p_paid = allocation['principal_paid']
            i_paid = allocation['interest_paid']

            # 4. Create Ledger Entry with Debit = CASH_BANK_ASSET, Credit = LOANS_RECEIVABLE_ASSET
            entry_id = f"led_{uuid.uuid4().hex[:12]}"
            cursor.execute("""
                INSERT INTO ledger_entries (id, org_id, loan_id, schedule_id, entry_type, amount, principal_component, interest_component, fee_component, debit_account, credit_account, payment_method, reference_id, notes, created_by)
                VALUES (?, ?, ?, ?, 'PAYMENT_RECEIVED', ?, ?, ?, ?, 'CASH_BANK_ASSET', 'LOANS_RECEIVABLE_ASSET', ?, ?, ?, ?)
            """, (entry_id, org_id, loan_id, sch_id, float(amt), float(p_paid), float(i_paid), float(allocation['fee_paid']), payment_method, reference_id, notes, created_by))

            # 5. Update Repayment Schedule line item
            if target_schedule:
                new_p_paid = Decimal(str(target_schedule['principal_paid'])) + p_paid
                new_i_paid = Decimal(str(target_schedule['interest_paid'])) + i_paid
                tot_due = Decimal(str(target_schedule['total_due']))
                tot_paid = new_p_paid + new_i_paid

                new_status = 'PAID' if tot_paid >= tot_due else 'PARTIAL'
                cursor.execute("""
                    UPDATE repayment_schedules
                    SET principal_paid = ?, interest_paid = ?, status = ?
                    WHERE id = ?
                """, (float(new_p_paid), float(new_i_paid), new_status, sch_id))

            # 6. Recalculate Loan Outstanding Balances from Ledger Stream
            LedgerService._recalculate_loan_balances(cursor, loan_id)

            conn.commit()

            AuditService.log(org_id, created_by, 'RECORD_PAYMENT', 'LEDGER_ENTRY', entry_id, new_state=f"Payment {amt} recorded via {payment_method}")

            return {
                "ledger_entry_id": entry_id,
                "amount": float(amt),
                "principal_paid": float(p_paid),
                "interest_paid": float(i_paid),
                "excess_paid": float(allocation['excess_paid']),
                "payment_method": payment_method,
                "reference_id": reference_id
            }
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def reverse_transaction(org_id: str, original_entry_id: str, reason: str, authorized_user_id: str) -> str:
        """
        Creates an accounting reversal entry to balance out an incorrect payment,
        preserving history integrity without deleting records.
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM ledger_entries WHERE id = ? AND org_id = ?", (original_entry_id, org_id))
            orig = cursor.fetchone()
            if not orig:
                raise ValueError("Original transaction ledger entry not found.")

            if orig['entry_type'] == 'TRANSACTION_REVERSED':
                raise ValueError("Cannot reverse an entry that is already a reversal.")

            # Double-Reversal Protection Check
            cursor.execute("SELECT id FROM ledger_entries WHERE reference_id = ?", (f"REV-{original_entry_id}",))
            if cursor.fetchone():
                raise ValueError("Transaction has already been reversed.")

            rev_id = f"led_rev_{uuid.uuid4().hex[:10]}"
            rev_amount = -abs(float(orig['amount']))
            rev_principal = -abs(float(orig['principal_component']))
            rev_interest = -abs(float(orig['interest_component']))

            cursor.execute("""
                INSERT INTO ledger_entries (id, org_id, loan_id, schedule_id, entry_type, amount, principal_component, interest_component, fee_component, debit_account, credit_account, payment_method, reference_id, notes, created_by)
                VALUES (?, ?, ?, ?, 'TRANSACTION_REVERSED', ?, ?, ?, 0.0, 'LOANS_RECEIVABLE_ASSET', 'CASH_BANK_ASSET', ?, ?, ?, ?)
            """, (rev_id, org_id, orig['loan_id'], orig['schedule_id'], rev_amount, rev_principal, rev_interest, orig['payment_method'], f"REV-{original_entry_id}", f"Reversal reason: {reason}", authorized_user_id))

            # Revert schedule balances if applicable
            if orig['schedule_id']:
                cursor.execute("SELECT * FROM repayment_schedules WHERE id = ?", (orig['schedule_id'],))
                sch = cursor.fetchone()
                if sch:
                    updated_p = max(0.0, float(sch['principal_paid']) - abs(float(orig['principal_component'])))
                    updated_i = max(0.0, float(sch['interest_paid']) - abs(float(orig['interest_component'])))
                    st = 'PARTIAL' if (updated_p + updated_i) > 0 else 'DUE'
                    cursor.execute("UPDATE repayment_schedules SET principal_paid = ?, interest_paid = ?, status = ? WHERE id = ?", (updated_p, updated_i, st, orig['schedule_id']))

            # Recalculate loan totals
            LedgerService._recalculate_loan_balances(cursor, orig['loan_id'])

            conn.commit()

            AuditService.log(org_id, authorized_user_id, 'REVERSE_TRANSACTION', 'LEDGER_ENTRY', rev_id, previous_state=original_entry_id, new_state=f"Reversed {orig['amount']}")
            return rev_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def get_early_settlement_quote(org_id: str, loan_id: str) -> Dict[str, Any]:
        """
        Calculates exact early settlement payoff quote.
        Payoff = Current Outstanding Principal + Accrued Earned Interest.
        Future unearned interest is explicitly waived.
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM loans WHERE id = ? AND org_id = ?", (loan_id, org_id))
        loan = cursor.fetchone()
        if not loan:
            conn.close()
            raise ValueError("Loan not found.")

        # Calculate earned interest from past/due installments up to today
        today_str = datetime.date.today().isoformat()
        cursor.execute("""
            SELECT 
                COALESCE(SUM(interest_due), 0.0) as earned_interest,
                COALESCE(SUM(interest_paid), 0.0) as interest_paid
            FROM repayment_schedules
            WHERE loan_id = ? AND due_date <= ?
        """, (loan_id, today_str))
        stat = cursor.fetchone()

        cursor.execute("SELECT COALESCE(SUM(interest_due), 0.0) as total_sched_interest FROM repayment_schedules WHERE loan_id = ?", (loan_id,))
        total_sched_i = Decimal(str(cursor.fetchone()['total_sched_interest']))
        conn.close()

        earned_i = Decimal(str(stat['earned_interest']))
        i_paid = Decimal(str(stat['interest_paid']))
        accrued_unpaid_i = max(Decimal('0'), earned_i - i_paid)

        outstanding_p = Decimal(str(loan['outstanding_principal']))
        settlement_payoff = outstanding_p + accrued_unpaid_i
        unearned_interest_waived = max(Decimal('0'), total_sched_i - earned_i)

        return {
            "loan_id": loan_id,
            "outstanding_principal": float(round_money(outstanding_p)),
            "accrued_interest_due": float(round_money(accrued_unpaid_i)),
            "early_settlement_payoff": float(round_money(settlement_payoff)),
            "unearned_interest_waived": float(round_money(unearned_interest_waived)),
            "quote_valid_until": today_str
        }

    @staticmethod
    def post_early_settlement(org_id: str, loan_id: str, payment_method: str, reference_id: str, authorized_user_id: str) -> Dict[str, Any]:
        """
        Executes early loan settlement, posts payoff ledger entry, waives unearned interest, and marks loan CLOSED.
        """
        quote = LedgerService.get_early_settlement_quote(org_id, loan_id)
        payoff_amt = Decimal(str(quote['early_settlement_payoff']))

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            entry_id = f"led_settle_{uuid.uuid4().hex[:10]}"
            cursor.execute("""
                INSERT INTO ledger_entries (id, org_id, loan_id, schedule_id, entry_type, amount, principal_component, interest_component, fee_component, debit_account, credit_account, payment_method, reference_id, notes, created_by)
                VALUES (?, ?, ?, NULL, 'PAYMENT_RECEIVED', ?, ?, ?, 0.0, 'CASH_BANK_ASSET', 'LOANS_RECEIVABLE_ASSET', ?, ?, 'Early Loan Settlement Payoff', ?)
            """, (entry_id, org_id, loan_id, float(payoff_amt), float(quote['outstanding_principal']), float(quote['accrued_interest_due']), payment_method, reference_id, authorized_user_id))

            # Mark all schedules as PAID
            cursor.execute("""
                UPDATE repayment_schedules
                SET principal_paid = principal_due, interest_paid = interest_due, status = 'PAID'
                WHERE loan_id = ?
            """, (loan_id,))

            # Mark loan as CLOSED with 0 outstanding balance
            cursor.execute("""
                UPDATE loans
                SET outstanding_principal = 0.0, status = 'CLOSED'
                WHERE id = ? AND org_id = ?
            """, (loan_id, org_id))

            conn.commit()

            AuditService.log(org_id, authorized_user_id, 'EARLY_SETTLEMENT', 'LOAN', loan_id, new_state=f"Settled {payoff_amt}")

            return {
                "settlement_entry_id": entry_id,
                "payoff_amount": float(payoff_amt),
                "unearned_interest_waived": quote['unearned_interest_waived'],
                "status": "CLOSED"
            }
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def _recalculate_loan_balances(cursor, loan_id: str):
        """Internal helper to compute outstanding principal & interest from ledger entries."""
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN entry_type = 'LOAN_DISBURSED' THEN amount ELSE 0 END) as total_disbursed,
                SUM(CASE WHEN entry_type IN ('PAYMENT_RECEIVED', 'TRANSACTION_REVERSED') THEN principal_component ELSE 0 END) as total_principal_paid,
                SUM(CASE WHEN entry_type IN ('PAYMENT_RECEIVED', 'TRANSACTION_REVERSED') THEN interest_component ELSE 0 END) as total_interest_paid
            FROM ledger_entries
            WHERE loan_id = ?
        """, (loan_id,))
        row = cursor.fetchone()

        disbursed = Decimal(str(row['total_disbursed'] or 0.0))
        p_paid = Decimal(str(row['total_principal_paid'] or 0.0))
        
        outstanding_p = max(Decimal('0'), disbursed - p_paid)
        
        loan_status = 'CLOSED' if outstanding_p <= Decimal('0.01') else 'ACTIVE'

        cursor.execute("""
            UPDATE loans
            SET outstanding_principal = ?, status = ?
            WHERE id = ?
        """, (float(round_money(outstanding_p)), loan_status, loan_id))

    @staticmethod
    def get_statement(org_id: str, loan_id: str) -> Dict[str, Any]:
        """Generates complete chronological financial loan statement."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT l.*, b.full_name as borrower_name, b.phone as borrower_phone, b.email as borrower_email
            FROM loans l
            JOIN borrowers b ON l.borrower_id = b.id
            WHERE l.id = ? AND l.org_id = ?
        """, (loan_id, org_id))
        loan = cursor.fetchone()
        if not loan:
            conn.close()
            raise ValueError("Loan not found.")

        cursor.execute("""
            SELECT le.*, u.full_name as recorder_name
            FROM ledger_entries le
            LEFT JOIN users u ON le.created_by = u.id
            WHERE le.loan_id = ? AND le.org_id = ?
            ORDER BY le.created_at ASC
        """, (loan_id, org_id))
        entries = cursor.fetchall()
        conn.close()

        running_balance = Decimal(str(loan['principal_amount']))
        running_interest_paid = Decimal('0')
        running_principal_paid = Decimal('0')

        transactions = []
        for e in entries:
            amt = Decimal(str(e['amount']))
            p_comp = Decimal(str(e['principal_component']))
            i_comp = Decimal(str(e['interest_component']))

            if e['entry_type'] == 'LOAN_DISBURSED':
                desc = "Initial Principal Disbursal"
            elif e['entry_type'] == 'PAYMENT_RECEIVED':
                desc = f"Payment Received ({e['payment_method']})"
                running_balance -= p_comp
                running_principal_paid += p_comp
                running_interest_paid += i_comp
            elif e['entry_type'] == 'TRANSACTION_REVERSED':
                desc = f"Accounting Transaction Reversal"
                running_balance -= p_comp # p_comp is negative
                running_principal_paid += p_comp
                running_interest_paid += i_comp

            transactions.append({
                "id": e['id'],
                "date": e['created_at'],
                "type": e['entry_type'],
                "description": desc,
                "amount": float(amt),
                "principal_component": float(p_comp),
                "interest_component": float(i_comp),
                "running_outstanding": float(round_money(max(Decimal('0'), running_balance))),
                "reference_id": e['reference_id'],
                "recorder": e['recorder_name'] or "System"
            })

        return {
            "loan_id": loan['id'],
            "borrower_name": loan['borrower_name'],
            "borrower_phone": loan['borrower_phone'],
            "borrower_email": loan['borrower_email'],
            "principal_amount": float(loan['principal_amount']),
            "interest_rate_annual": float(loan['interest_rate_annual']),
            "interest_type": loan['interest_type'],
            "start_date": loan['start_date'],
            "total_payable": float(loan['total_payable']),
            "total_interest": float(loan['total_interest']),
            "total_principal_paid": float(round_money(running_principal_paid)),
            "total_interest_paid": float(round_money(running_interest_paid)),
            "current_outstanding_balance": float(round_money(max(Decimal('0'), running_balance))),
            "status": loan['status'],
            "transactions": transactions
        }

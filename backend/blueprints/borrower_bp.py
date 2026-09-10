"""
Borrower Portal Blueprint
Provides transparent, simple self-service endpoints for borrowers to view
loan summaries, repayment schedules, digital receipts, and chronological statements.
"""

from flask import Blueprint, request, jsonify
from decimal import Decimal
from backend.database import get_db_connection
from backend.services.ledger_service import LedgerService
from backend.services.loan_engine import round_money

borrower_bp = Blueprint('borrower', __name__, url_prefix='/api/v1/borrower')

@borrower_bp.route('/my-loan', methods=['GET'])
def get_my_loan_summary():
    """Fetches clean, simple loan summary for logged-in borrower."""
    borrower_user_id = request.headers.get('X-User-Id')
    
    if not borrower_user_id:
        return jsonify({"error": "User ID header required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Find borrower profile
    cursor.execute("SELECT * FROM borrowers WHERE user_id = ?", (borrower_user_id,))
    bor = cursor.fetchone()

    if not bor:
        conn.close()
        return jsonify({"error": "No borrower profile found."}), 404

    # Fetch active loan
    cursor.execute("""
        SELECT l.*, o.name as financier_name, o.phone as financier_phone
        FROM loans l
        JOIN organizations o ON l.org_id = o.id
        WHERE l.borrower_id = ? AND l.status IN ('ACTIVE', 'COMPLETED')
        ORDER BY l.created_at DESC LIMIT 1
    """, (bor['id'],))
    loan = cursor.fetchone()

    if not loan:
        conn.close()
        return jsonify({"error": "No active loan found for borrower."}), 404

    # Fetch Next Due Installment
    cursor.execute("""
        SELECT * FROM repayment_schedules
        WHERE loan_id = ? AND status IN ('DUE', 'PARTIAL', 'OVERDUE')
        ORDER BY installment_number ASC LIMIT 1
    """, (loan['id'],))
    next_inst = cursor.fetchone()

    # Total Paid Calculation from Ledger
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0.0) as total_paid
        FROM ledger_entries
        WHERE loan_id = ? AND entry_type = 'PAYMENT_RECEIVED'
    """, (loan['id'],))
    total_paid_amt = cursor.fetchone()['total_paid']

    conn.close()

    p_orig = Decimal(str(loan['principal_amount']))
    tot_payable = Decimal(str(loan['total_payable']))
    tot_paid = Decimal(str(total_paid_amt))
    outstanding = max(Decimal('0'), Decimal(str(loan['outstanding_principal'])))
    progress_pct = float(round((tot_paid / tot_payable * 100), 1)) if tot_payable > 0 else 0.0

    return jsonify({
        "loan_id": loan['id'],
        "financier_name": loan['financier_name'],
        "financier_phone": loan['financier_phone'],
        "borrower_name": bor['full_name'],
        "original_principal": float(round_money(p_orig)),
        "total_payable": float(round_money(tot_payable)),
        "total_paid": float(round_money(tot_paid)),
        "outstanding_balance": float(round_money(outstanding)),
        "repayment_progress_pct": min(100.0, progress_pct),
        "interest_type": loan['interest_type'],
        "interest_rate_annual": float(loan['interest_rate_annual']),
        "next_payment": {
            "schedule_id": next_inst['id'] if next_inst else None,
            "installment_number": next_inst['installment_number'] if next_inst else None,
            "due_date": next_inst['due_date'] if next_inst else None,
            "amount_due": float(round_money(Decimal(str(next_inst['total_due'])) - (Decimal(str(next_inst['principal_paid'])) + Decimal(str(next_inst['interest_paid']))))) if next_inst else 0.0,
            "status": next_inst['status'] if next_inst else "COMPLETED"
        }
    }), 200

@borrower_bp.route('/schedule', methods=['GET'])
def get_my_schedule():
    """Fetches full repayment schedule for borrower's active loan."""
    loan_id = request.args.get('loan_id')
    borrower_user_id = request.headers.get('X-User-Id')

    conn = get_db_connection()
    cursor = conn.cursor()

    if not loan_id and borrower_user_id:
        cursor.execute("""
            SELECT l.id FROM loans l
            JOIN borrowers b ON l.borrower_id = b.id
            WHERE b.user_id = ? ORDER BY l.created_at DESC LIMIT 1
        """, (borrower_user_id,))
        row = cursor.fetchone()
        if row:
            loan_id = row['id']

    if not loan_id:
        conn.close()
        return jsonify({"loan_id": None, "schedule": []}), 200

    cursor.execute("""
        SELECT * FROM repayment_schedules
        WHERE loan_id = ?
        ORDER BY installment_number ASC
    """, (loan_id,))
    rows = cursor.fetchall()
    conn.close()

    schedule_list = []
    for r in rows:
        schedule_list.append({
            "id": r['id'],
            "installment_number": r['installment_number'],
            "due_date": r['due_date'],
            "principal_due": float(r['principal_due']),
            "interest_due": float(r['interest_due']),
            "total_due": float(r['total_due']),
            "principal_paid": float(r['principal_paid']),
            "interest_paid": float(r['interest_paid']),
            "status": r['status']
        })

    return jsonify({"loan_id": loan_id, "schedule": schedule_list}), 200

@borrower_bp.route('/statement', methods=['GET'])
def get_my_statement():
    """Fetches chronological loan statement."""
    loan_id = request.args.get('loan_id')
    org_id = request.headers.get('X-Org-Id')
    borrower_user_id = request.headers.get('X-User-Id')

    conn = get_db_connection()
    cursor = conn.cursor()

    if not loan_id and borrower_user_id:
        cursor.execute("""
            SELECT l.id, l.org_id FROM loans l
            JOIN borrowers b ON l.borrower_id = b.id
            WHERE b.user_id = ? ORDER BY l.created_at DESC LIMIT 1
        """, (borrower_user_id,))
        row = cursor.fetchone()
        if row:
            loan_id = row['id']
            org_id = row['org_id']

    conn.close()

    if not loan_id or not org_id:
        return jsonify({"error": "Loan ID and Organization context required."}), 400

    stmt = LedgerService.get_statement(org_id, loan_id)
    return jsonify(stmt), 200


@borrower_bp.route('/receipt/<receipt_id>', methods=['GET'])
def get_receipt(receipt_id):
    """Fetches printable cryptographic digital receipt."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT le.*, l.principal_amount, l.interest_rate_annual, b.full_name as borrower_name, b.phone as borrower_phone, o.name as financier_name, o.address as financier_address
        FROM ledger_entries le
        JOIN loans l ON le.loan_id = l.id
        JOIN borrowers b ON l.borrower_id = b.id
        JOIN organizations o ON le.org_id = o.id
        WHERE le.id = ?
    """, (receipt_id,))
    rec = cursor.fetchone()
    conn.close()

    if not rec:
        return jsonify({"error": "Receipt not found."}), 404

    import hashlib
    verification_raw = f"{rec['id']}:{rec['loan_id']}:{rec['amount']}:{rec['created_at']}"
    verification_hash = hashlib.sha256(verification_raw.encode('utf-8')).hexdigest()[:16].upper()

    return jsonify({
        "receipt_number": f"RCPT-{rec['id'].upper()}",
        "date": rec['created_at'],
        "financier_name": rec['financier_name'],
        "financier_address": rec['financier_address'],
        "borrower_name": rec['borrower_name'],
        "borrower_phone": rec['borrower_phone'],
        "loan_id": rec['loan_id'],
        "amount_paid": float(rec['amount']),
        "principal_component": float(rec['principal_component']),
        "interest_component": float(rec['interest_component']),
        "fee_component": float(rec['fee_component']),
        "payment_method": rec['payment_method'],
        "reference_id": rec['reference_id'],
        "notes": rec['notes'],
        "verification_hash": f"CP-{verification_hash}"
    }), 200

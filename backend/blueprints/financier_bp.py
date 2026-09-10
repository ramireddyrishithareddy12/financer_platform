"""
Financier Portal Blueprint
Provides dashboard KPIs, borrower CRUD, loan creation & schedule generation,
staff management, cash desk, transaction reversals, audit logs, and reports.
"""

from flask import Blueprint, request, jsonify
from decimal import Decimal
import uuid
import datetime
from backend.database import get_db_connection, hash_password
from backend.services.loan_engine import LoanEngine, round_money
from backend.services.ledger_service import LedgerService
from backend.services.audit_service import AuditService
from backend.services.payment_service import PaymentService

financier_bp = Blueprint('financier', __name__, url_prefix='/api/v1/financier')

def get_request_context():
    """Extracts header tenant and user context."""
    org_id = request.headers.get('X-Org-Id')
    user_id = request.headers.get('X-User-Id')
    user_role = request.headers.get('X-User-Role', 'FINANCIER_OWNER')
    return org_id, user_id, user_role

@financier_bp.route('/dashboard', methods=['GET'])
def get_dashboard_metrics():
    """Calculates executive portfolio KPIs for the financier organization."""
    org_id, user_id, role = get_request_context()
    if not org_id:
        return jsonify({"error": "Organization context required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Active loans count & total principal outstanding
    cursor.execute("""
        SELECT 
            COUNT(*) as active_loans_count,
            COALESCE(SUM(outstanding_principal), 0.0) as total_principal_outstanding,
            COALESCE(SUM(total_payable), 0.0) as total_portfolio_payable
        FROM loans
        WHERE org_id = ? AND status = 'ACTIVE'
    """, (org_id,))
    loans_stat = cursor.fetchone()

    # Active borrowers
    cursor.execute("SELECT COUNT(DISTINCT id) as cnt FROM borrowers WHERE org_id = ?", (org_id,))
    borrowers_cnt = cursor.fetchone()['cnt']

    # Total collected from ledger
    cursor.execute("""
        SELECT 
            COALESCE(SUM(amount), 0.0) as total_collected,
            COALESCE(SUM(principal_component), 0.0) as principal_collected,
            COALESCE(SUM(interest_component), 0.0) as interest_collected
        FROM ledger_entries
        WHERE org_id = ? AND entry_type = 'PAYMENT_RECEIVED'
    """, (org_id,))
    coll_stat = cursor.fetchone()

    today_str = datetime.date.today().isoformat()

    # Due today
    cursor.execute("""
        SELECT COALESCE(SUM(total_due - (principal_paid + interest_paid)), 0.0) as due_today
        FROM repayment_schedules rs
        JOIN loans l ON rs.loan_id = l.id
        WHERE l.org_id = ? AND rs.due_date = ? AND rs.status IN ('DUE', 'PARTIAL')
    """, (org_id, today_str))
    due_today_amt = cursor.fetchone()['due_today']

    # Overdue
    cursor.execute("""
        SELECT 
            COALESCE(SUM(total_due - (principal_paid + interest_paid)), 0.0) as overdue_amt,
            COUNT(DISTINCT l.borrower_id) as overdue_borrowers_count
        FROM repayment_schedules rs
        JOIN loans l ON rs.loan_id = l.id
        WHERE l.org_id = ? AND rs.due_date < ? AND rs.status IN ('DUE', 'PARTIAL', 'OVERDUE')
    """, (org_id, today_str))
    overdue_stat = cursor.fetchone()

    conn.close()

    return jsonify({
        "total_principal_outstanding": float(round_money(Decimal(str(loans_stat['total_principal_outstanding'])))),
        "active_loans_count": loans_stat['active_loans_count'],
        "active_borrowers_count": borrowers_cnt,
        "total_collected": float(round_money(Decimal(str(coll_stat['total_collected'])))),
        "principal_collected": float(round_money(Decimal(str(coll_stat['principal_collected'])))),
        "interest_collected": float(round_money(Decimal(str(coll_stat['interest_collected'])))),
        "due_today": float(round_money(Decimal(str(due_today_amt)))),
        "overdue_amount": float(round_money(Decimal(str(overdue_stat['overdue_amt'])))),
        "overdue_borrowers_count": overdue_stat['overdue_borrowers_count']
    }), 200

# ----------------- BORROWER MANAGEMENT ----------------- #

@financier_bp.route('/borrowers', methods=['GET'])
def list_borrowers():
    """Lists borrowers for current tenant with loan summaries and search/filtering."""
    org_id, user_id, role = get_request_context()
    if not org_id:
        return jsonify({"error": "Organization header required."}), 400

    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip().upper()

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT b.*, u.full_name as agent_name,
               l.id as loan_id, l.principal_amount, l.interest_rate_annual, l.interest_type,
               l.total_payable, l.outstanding_principal, l.status as loan_status
        FROM borrowers b
        LEFT JOIN users u ON b.assigned_agent_id = u.id
        LEFT JOIN loans l ON b.id = l.borrower_id AND l.status IN ('ACTIVE', 'COMPLETED')
        WHERE b.org_id = ?
    """
    params = [org_id]

    if role == 'AGENT' and user_id:
        query += " AND b.assigned_agent_id = ?"
        params.append(user_id)

    if q:
        query += " AND (b.full_name LIKE ? OR b.phone LIKE ? OR l.id LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    if status_filter:
        if status_filter == 'ARCHIVED':
            query += " AND b.id IN (SELECT b2.id FROM borrowers b2 JOIN users u2 ON b2.user_id = u2.id WHERE u2.status = 'ARCHIVED')"
        elif status_filter == 'COMPLETED':
            query += " AND l.status = 'COMPLETED'"
        elif status_filter == 'ACTIVE':
            query += " AND (l.status = 'ACTIVE' OR l.id IS NULL)"

    query += " ORDER BY b.created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    borrowers_list = []
    today_str = datetime.date.today().isoformat()

    for r in rows:
        bor = dict(r)
        loan_id = bor.get('loan_id')
        bor['total_paid'] = 0.0
        bor['next_due_amount'] = 0.0
        bor['next_due_date'] = None

        if loan_id:
            # Calculate total paid from ledger
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0.0) as total_paid
                FROM ledger_entries
                WHERE loan_id = ? AND entry_type = 'PAYMENT_RECEIVED'
            """, (loan_id,))
            bor['total_paid'] = float(cursor.fetchone()['total_paid'])

            # Fetch next due schedule item
            cursor.execute("""
                SELECT due_date, total_due, principal_paid, interest_paid
                FROM repayment_schedules
                WHERE loan_id = ? AND status IN ('DUE', 'PARTIAL', 'OVERDUE')
                ORDER BY installment_number ASC LIMIT 1
            """, (loan_id,))
            next_s = cursor.fetchone()
            if next_s:
                rem_due = float(Decimal(str(next_s['total_due'])) - (Decimal(str(next_s['principal_paid'])) + Decimal(str(next_s['interest_paid']))))
                bor['next_due_amount'] = max(0.0, rem_due)
                bor['next_due_date'] = next_s['due_date']

        borrowers_list.append(bor)

    conn.close()
    return jsonify(borrowers_list), 200

@financier_bp.route('/borrowers/<borrower_id>/detail', methods=['GET'])
def get_borrower_detail(borrower_id):
    """Returns complete borrower module: Profile, Loan Summary, Schedule, & Ledger Payment History."""
    org_id, user_id, role = get_request_context()
    if not org_id:
        return jsonify({"error": "Organization header required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Borrower profile
    cursor.execute("SELECT * FROM borrowers WHERE id = ? AND org_id = ?", (borrower_id, org_id))
    bor = cursor.fetchone()
    if not bor:
        conn.close()
        return jsonify({"error": "Borrower not found."}), 404

    bor_dict = dict(bor)

    # Active or latest loan
    cursor.execute("SELECT * FROM loans WHERE borrower_id = ? AND org_id = ? ORDER BY created_at DESC LIMIT 1", (borrower_id, org_id))
    loan = cursor.fetchone()

    loan_detail = None
    schedule_list = []
    payment_history = []

    if loan:
        loan_dict = dict(loan)
        loan_id = loan_dict['id']

        # Total paid & principal/interest split from ledger
        cursor.execute("""
            SELECT 
                COALESCE(SUM(amount), 0.0) as total_paid,
                COALESCE(SUM(principal_component), 0.0) as principal_paid,
                COALESCE(SUM(interest_component), 0.0) as interest_paid
            FROM ledger_entries
            WHERE loan_id = ? AND entry_type = 'PAYMENT_RECEIVED'
        """, (loan_id,))
        coll = cursor.fetchone()

        tot_paid = Decimal(str(coll['total_paid']))
        p_paid = Decimal(str(coll['principal_paid']))
        i_paid = Decimal(str(coll['interest_paid']))
        tot_payable = Decimal(str(loan_dict['total_payable']))
        tot_interest = Decimal(str(loan_dict['total_interest']))
        p_orig = Decimal(str(loan_dict['principal_amount']))

        outstanding_bal = max(Decimal('0'), tot_payable - tot_paid)
        rem_interest = max(Decimal('0'), tot_interest - i_paid)

        # Repayment schedule
        cursor.execute("SELECT * FROM repayment_schedules WHERE loan_id = ? ORDER BY installment_number ASC", (loan_id,))
        s_rows = cursor.fetchall()
        
        rem_installments_count = 0
        next_due_item = None

        for s in s_rows:
            sd = dict(s)
            sd['remaining_amount'] = float(Decimal(str(sd['total_due'])) - (Decimal(str(sd['principal_paid'])) + Decimal(str(sd['interest_paid']))))
            schedule_list.append(sd)
            if sd['status'] in ['DUE', 'PARTIAL', 'OVERDUE']:
                rem_installments_count += 1
                if not next_due_item:
                    next_due_item = sd

        # Payment Ledger History
        cursor.execute("""
            SELECT le.*, u.full_name as recorder_name
            FROM ledger_entries le
            LEFT JOIN users u ON le.created_by = u.id
            WHERE le.loan_id = ? AND le.entry_type IN ('PAYMENT_RECEIVED', 'REVERSAL')
            ORDER BY le.created_at DESC
        """, (loan_id,))
        p_rows = cursor.fetchall()
        payment_history = [dict(pr) for pr in p_rows]

        loan_detail = {
            "loan_id": loan_id,
            "principal_amount": float(round_money(p_orig)),
            "interest_rate_annual": float(loan_dict['interest_rate_annual']),
            "interest_type": loan_dict['interest_type'],
            "frequency": loan_dict['frequency'],
            "tenure_periods": loan_dict['tenure_periods'],
            "start_date": loan_dict['start_date'],
            "status": loan_dict['status'],
            "total_interest": float(round_money(tot_interest)),
            "total_payable": float(round_money(tot_payable)),
            "total_paid": float(round_money(tot_paid)),
            "principal_paid": float(round_money(p_paid)),
            "interest_paid": float(round_money(i_paid)),
            "outstanding_balance": float(round_money(outstanding_bal)),
            "remaining_interest": float(round_money(rem_interest)),
            "remaining_installments": rem_installments_count,
            "next_amount_due": next_due_item['remaining_amount'] if next_due_item else 0.0,
            "next_due_date": next_due_item['due_date'] if next_due_item else None
        }

    conn.close()

    return jsonify({
        "borrower": bor_dict,
        "loan": loan_detail,
        "schedule": schedule_list,
        "payment_history": payment_history
    }), 200


@financier_bp.route('/borrowers', methods=['POST'])
def add_borrower():
    """Adds a new borrower and creates borrower user account."""
    org_id, user_id, role = get_request_context()
    if not org_id:
        return jsonify({"error": "Organization header required."}), 400

    data = request.json or {}
    full_name = data.get('full_name')
    phone = data.get('phone')
    email = data.get('email')
    address = data.get('address', '')
    kyc_id_type = data.get('kyc_id_type', 'AADHAAR')
    kyc_id_number = data.get('kyc_id_number', '')
    assigned_agent_id = data.get('assigned_agent_id')

    if not full_name or not phone:
        return jsonify({"error": "Name and Mobile number are required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check duplicate mobile in tenant
        cursor.execute("SELECT id FROM borrowers WHERE org_id = ? AND phone = ?", (org_id, phone))
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "Borrower with this phone number already registered."}), 400

        # Create User Account for Borrower Portal Access
        user_id_bor = f"user_{uuid.uuid4().hex[:10]}"
        default_pwd = f"pass_{phone[-4:]}" if len(phone) >= 4 else "password123"
        
        cursor.execute("""
            INSERT INTO users (id, org_id, role, full_name, email, phone, password_hash)
            VALUES (?, ?, 'BORROWER', ?, ?, ?, ?)
        """, (user_id_bor, org_id, full_name, email, phone, hash_password(default_pwd)))

        bor_id = f"bor_{uuid.uuid4().hex[:10]}"
        cursor.execute("""
            INSERT INTO borrowers (id, org_id, user_id, full_name, phone, email, address, kyc_id_type, kyc_id_number, assigned_agent_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (bor_id, org_id, user_id_bor, full_name, phone, email, address, kyc_id_type, kyc_id_number, assigned_agent_id))

        conn.commit()
        conn.close()

        AuditService.log(org_id, user_id, 'ADD_BORROWER', 'BORROWER', bor_id, new_state=full_name)

        return jsonify({
            "message": "Borrower created successfully.",
            "borrower_id": bor_id,
            "login_phone": phone,
            "default_password": default_pwd
        }), 201
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"Failed to add borrower: {str(e)}"}), 500

@financier_bp.route('/borrowers/<borrower_id>/archive', methods=['POST'])
def archive_borrower(borrower_id):
    """Soft archives a borrower while maintaining all financial history intact."""
    org_id, user_id, role = get_request_context()
    if role not in ['FINANCIER_OWNER', 'MANAGER']:
        return jsonify({"error": "Unauthorized. Only Owners & Managers can archive borrowers."}), 403

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status = 'ARCHIVED' WHERE id = (SELECT user_id FROM borrowers WHERE id = ? AND org_id = ?)", (borrower_id, org_id))
    conn.commit()
    conn.close()

    AuditService.log(org_id, user_id, 'ARCHIVE_BORROWER', 'BORROWER', borrower_id, new_state="ARCHIVED")
    return jsonify({"message": "Borrower account archived successfully."}), 200

@financier_bp.route('/loans/<loan_id>/early-settlement-quote', methods=['GET'])
def get_early_settlement_quote(loan_id):
    """Calculates payoff quote for early loan settlement."""
    org_id, user_id, role = get_request_context()
    try:
        quote = LedgerService.get_early_settlement_quote(org_id, loan_id)
        return jsonify(quote), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@financier_bp.route('/loans/<loan_id>/early-settlement', methods=['POST'])
def post_early_settlement(loan_id):
    """Executes early settlement, waives unearned interest, and closes loan."""
    org_id, user_id, role = get_request_context()
    if role not in ['FINANCIER_OWNER', 'MANAGER']:
        return jsonify({"error": "Unauthorized. Early settlement requires Owner or Manager authorization."}), 403

    data = request.json or {}
    payment_method = data.get('payment_method', 'CASH')
    reference_id = data.get('reference_id', f"SETTLE-{uuid.uuid4().hex[:6].upper()}")

    try:
        res = LedgerService.post_early_settlement(org_id, loan_id, payment_method, reference_id, user_id or "staff")
        return jsonify(res), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ----------------- LOAN ORIGINATION STUDIO ----------------- #

@financier_bp.route('/loans/calculate', methods=['POST'])
def calculate_loan_preview():
    """Pure calculation endpoint for schedule preview before disbursal."""
    data = request.json or {}
    try:
        schedule = LoanEngine.generate_schedule(
            principal=data.get('principal_amount', 100000),
            annual_rate=data.get('interest_rate_annual', 12),
            interest_type=data.get('interest_type', 'REDUCING_BALANCE'),
            frequency=data.get('frequency', 'MONTHLY'),
            tenure_periods=data.get('tenure_periods', 12),
            start_date=data.get('start_date', datetime.date.today().isoformat())
        )
        return jsonify(schedule), 200
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

@financier_bp.route('/loans', methods=['POST'])
def disburse_loan():
    """Disburses loan, generates schedule, and posts ledger record."""
    org_id, user_id, role = get_request_context()
    if role in ['AGENT', 'ACCOUNTANT']:
        return jsonify({"error": "Unauthorized. Only Owners & Managers can create loans."}), 403

    data = request.json or {}
    borrower_id = data.get('borrower_id')
    principal = data.get('principal_amount')
    rate = data.get('interest_rate_annual')
    interest_type = data.get('interest_type', 'REDUCING_BALANCE')
    frequency = data.get('frequency', 'MONTHLY')
    tenure = data.get('tenure_periods')
    start_date = data.get('start_date', datetime.date.today().isoformat())

    if not borrower_id or not principal or not rate or not tenure:
        return jsonify({"error": "Missing loan fields."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Generate schedule using loan engine
        sched = LoanEngine.generate_schedule(principal, rate, interest_type, frequency, tenure, start_date)

        loan_id = f"loan_{uuid.uuid4().hex[:10]}"
        cursor.execute("""
            INSERT INTO loans (id, org_id, borrower_id, principal_amount, interest_rate_annual, interest_type, frequency, tenure_periods, start_date, total_interest, total_payable, outstanding_principal, outstanding_interest, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 'ACTIVE')
        """, (loan_id, org_id, borrower_id, sched['principal'], sched['annual_rate'], interest_type, frequency, tenure, start_date, sched['total_interest'], sched['total_payable'], sched['principal']))

        # Insert Schedule Line Items
        for inst in sched['installments']:
            sch_id = f"sch_{loan_id}_{inst['installment_number']}"
            cursor.execute("""
                INSERT INTO repayment_schedules (id, loan_id, installment_number, due_date, principal_due, interest_due, total_due, principal_paid, interest_paid, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 'DUE')
            """, (sch_id, loan_id, inst['installment_number'], inst['due_date'], inst['principal_due'], inst['interest_due'], inst['total_due']))

        conn.commit()
        conn.close()

        # Post ledger disbursal event
        LedgerService.post_disbursal(org_id, loan_id, Decimal(str(principal)), user_id or "system")

        return jsonify({
            "message": "Loan created and disbursed successfully.",
            "loan_id": loan_id,
            "schedule": sched
        }), 201
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"Loan disbursal failed: {str(e)}"}), 500

@financier_bp.route('/loans', methods=['GET'])
def list_loans():
    """Lists loans for organization with borrower names and outstanding balances."""
    org_id, user_id, role = get_request_context()
    if not org_id:
        return jsonify({"error": "Organization header required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.*, b.full_name as borrower_name, b.phone as borrower_phone
        FROM loans l
        JOIN borrowers b ON l.borrower_id = b.id
        WHERE l.org_id = ?
        ORDER BY l.created_at DESC
    """, (org_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200

# ----------------- CASH DESK & REVERSALS ----------------- #

@financier_bp.route('/cash-payment', methods=['POST'])
def record_cash_payment():
    """Records an authorized offline/cash payment."""
    org_id, user_id, role = get_request_context()
    data = request.json or {}
    loan_id = data.get('loan_id')
    amount = data.get('amount')
    reference_id = data.get('reference_id', f"CASH-{uuid.uuid4().hex[:6].upper()}")
    notes = data.get('notes', 'Cash Payment')

    if not loan_id or not amount:
        return jsonify({"error": "Loan ID and Amount required."}), 400

    try:
        rec = LedgerService.record_payment(
            org_id=org_id,
            loan_id=loan_id,
            schedule_id=data.get('schedule_id'),
            amount=amount,
            payment_method='CASH',
            reference_id=reference_id,
            notes=notes,
            created_by=user_id or "staff"
        )
        return jsonify({"message": "Offline cash payment recorded successfully.", "payment": rec}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@financier_bp.route('/reverse-payment', methods=['POST'])
def reverse_payment():
    """Submits an authorized transaction reversal with audit trail."""
    org_id, user_id, role = get_request_context()
    if role not in ['FINANCIER_OWNER', 'MANAGER']:
        return jsonify({"error": "Unauthorized. Reversals require Owner or Manager approval."}), 403

    data = request.json or {}
    ledger_entry_id = data.get('ledger_entry_id')
    reason = data.get('reason')

    if not ledger_entry_id or not reason:
        return jsonify({"error": "Ledger Entry ID and Reason are required."}), 400

    try:
        rev_id = LedgerService.reverse_transaction(org_id, ledger_entry_id, reason, user_id or "manager")
        return jsonify({"message": "Transaction reversed successfully.", "reversal_entry_id": rev_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ----------------- STAFF MANAGEMENT ----------------- #

@financier_bp.route('/staff', methods=['POST'])
def invite_staff():
    """Invites/creates an employee user account."""
    org_id, user_id, role = get_request_context()
    if role != 'FINANCIER_OWNER':
        return jsonify({"error": "Unauthorized. Only Organization Owners can invite staff."}), 403

    data = request.json or {}
    full_name = data.get('full_name')
    email = data.get('email')
    phone = data.get('phone')
    staff_role = data.get('role', 'AGENT') # MANAGER, ACCOUNTANT, AGENT
    password = data.get('password', 'password123')

    if not full_name or not phone or not email:
        return jsonify({"error": "Full name, email, and phone required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        staff_id = f"user_staff_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
            INSERT INTO users (id, org_id, role, full_name, email, phone, password_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (staff_id, org_id, staff_role, full_name, email, phone, hash_password(password)))

        conn.commit()
        conn.close()

        AuditService.log(org_id, user_id, 'INVITE_STAFF', 'USER', staff_id, new_state=f"Role: {staff_role}")

        return jsonify({"message": f"Staff user created with role {staff_role}.", "user_id": staff_id}), 201
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"Failed to add staff: {str(e)}"}), 500

# ----------------- REMINDERS & NOTIFICATIONS ----------------- #

@financier_bp.route('/send-reminder', methods=['POST'])
def send_reminder():
    """Dispatches professional compliance-first repayment reminder."""
    org_id, user_id, role = get_request_context()
    data = request.json or {}
    loan_id = data.get('loan_id')
    channel = data.get('channel', 'SMS') # SMS, EMAIL, WHATSAPP

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT l.*, b.id as bor_id, b.full_name, b.phone, b.email, rs.due_date, rs.total_due
        FROM loans l
        JOIN borrowers b ON l.borrower_id = b.id
        JOIN repayment_schedules rs ON l.id = rs.loan_id
        WHERE l.id = ? AND l.org_id = ? AND rs.status IN ('DUE', 'PARTIAL', 'OVERDUE')
        ORDER BY rs.installment_number ASC LIMIT 1
    """, (loan_id, org_id))
    item = cursor.fetchone()

    if not item:
        conn.close()
        return jsonify({"error": "No active due installment found for loan."}), 400

    msg = f"Dear {item['full_name']}, your loan installment of ₹{item['total_due']:.2f} for Loan #{loan_id[:8]} is due on {item['due_date']}. Thank you for your partnership."
    
    notif_id = f"notif_{uuid.uuid4().hex[:10]}"
    cursor.execute("""
        INSERT INTO notifications (id, org_id, borrower_id, loan_id, channel, message, status)
        VALUES (?, ?, ?, ?, ?, ?, 'DELIVERED')
    """, (notif_id, org_id, item['bor_id'], loan_id, channel, msg))

    conn.commit()
    conn.close()

    AuditService.log(org_id, user_id, 'SEND_REMINDER', 'NOTIFICATION', notif_id, new_state=channel)

    return jsonify({"message": f"Reminder dispatched via {channel}.", "notification": {"id": notif_id, "message": msg}}), 200

# ----------------- AUDIT LOGS & REPORTS ----------------- #

@financier_bp.route('/audit-logs', methods=['GET'])
def get_audit_logs():
    """Returns organization immutable audit logs."""
    org_id, user_id, role = get_request_context()
    logs = AuditService.get_logs(org_id)
    return jsonify(logs), 200

@financier_bp.route('/reports/reconciliation', methods=['GET'])
def get_reconciliation():
    """Gets gateway vs ledger reconciliation report."""
    org_id, user_id, role = get_request_context()
    report = PaymentService.get_reconciliation_report(org_id)
    return jsonify(report), 200

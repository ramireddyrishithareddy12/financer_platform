"""
Database Module for CreditorPulse Platform
Handles SQLite initialization, schema creation, connection pooling,
WAL mode, foreign key enforcement, and seed initialization.
"""

import sqlite3
import os
import hashlib
import uuid
import datetime
from decimal import Decimal

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creditorpulse.db")

def hash_password(password: str) -> str:
    """Standard PBKDF2 password hashing."""
    salt = "creditorpulse_salt_2026"
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()

def get_db_connection():
    """Establishes SQLite connection with WAL mode, foreign keys, & 20s timeout."""
    conn = sqlite3.connect(DB_PATH, timeout=20.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    """Initializes normalized relational schema."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Organizations (Tenants)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS organizations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        registration_number TEXT,
        email TEXT UNIQUE NOT NULL,
        phone TEXT NOT NULL,
        address TEXT,
        verification_status TEXT DEFAULT 'VERIFIED',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Users (System Admin, Financier Staff, Borrowers)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        org_id TEXT,
        role TEXT NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE,
        phone TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        status TEXT DEFAULT 'ACTIVE',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE CASCADE
    );
    """)

    # 3. Borrowers
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS borrowers (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        user_id TEXT UNIQUE,
        full_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT,
        address TEXT,
        kyc_id_type TEXT,
        kyc_id_number TEXT,
        assigned_agent_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
        FOREIGN KEY(assigned_agent_id) REFERENCES users(id) ON DELETE SET NULL
    );
    """)

    # 4. Loans
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS loans (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        borrower_id TEXT NOT NULL,
        principal_amount DECIMAL(12,4) NOT NULL,
        interest_rate_annual DECIMAL(6,4) NOT NULL,
        interest_type TEXT NOT NULL,
        frequency TEXT NOT NULL,
        tenure_periods INTEGER NOT NULL,
        start_date DATE NOT NULL,
        total_interest DECIMAL(12,4) NOT NULL,
        total_payable DECIMAL(12,4) NOT NULL,
        outstanding_principal DECIMAL(12,4) NOT NULL,
        outstanding_interest DECIMAL(12,4) NOT NULL,
        status TEXT DEFAULT 'ACTIVE',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE CASCADE,
        FOREIGN KEY(borrower_id) REFERENCES borrowers(id) ON DELETE CASCADE
    );
    """)

    # 5. Repayment Schedules
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS repayment_schedules (
        id TEXT PRIMARY KEY,
        loan_id TEXT NOT NULL,
        installment_number INTEGER NOT NULL,
        due_date DATE NOT NULL,
        principal_due DECIMAL(12,4) NOT NULL,
        interest_due DECIMAL(12,4) NOT NULL,
        total_due DECIMAL(12,4) NOT NULL,
        principal_paid DECIMAL(12,4) DEFAULT 0.0000,
        interest_paid DECIMAL(12,4) DEFAULT 0.0000,
        status TEXT DEFAULT 'DUE',
        FOREIGN KEY(loan_id) REFERENCES loans(id) ON DELETE CASCADE
    );
    """)

    # 6. Immutable Financial Ledger (Double-Entry Source of Truth)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ledger_entries (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        loan_id TEXT NOT NULL,
        schedule_id TEXT,
        entry_type TEXT NOT NULL,
        amount DECIMAL(12,4) NOT NULL,
        principal_component DECIMAL(12,4) DEFAULT 0.0000,
        interest_component DECIMAL(12,4) DEFAULT 0.0000,
        fee_component DECIMAL(12,4) DEFAULT 0.0000,
        debit_account TEXT DEFAULT 'CASH_BANK_ASSET',
        credit_account TEXT DEFAULT 'LOANS_RECEIVABLE_ASSET',
        payment_method TEXT,
        reference_id TEXT,
        notes TEXT,
        created_by TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(org_id) REFERENCES organizations(id) ON DELETE CASCADE,
        FOREIGN KEY(loan_id) REFERENCES loans(id) ON DELETE CASCADE,
        FOREIGN KEY(created_by) REFERENCES users(id)
    );
    """)

    try:
        cursor.execute("ALTER TABLE ledger_entries ADD COLUMN debit_account TEXT DEFAULT 'CASH_BANK_ASSET';")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE ledger_entries ADD COLUMN credit_account TEXT DEFAULT 'LOANS_RECEIVABLE_ASSET';")
    except Exception:
        pass

    # 7. Payment Gateway Attempts & Idempotency
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payment_attempts (
        id TEXT PRIMARY KEY,
        loan_id TEXT NOT NULL,
        schedule_id TEXT,
        amount DECIMAL(12,4) NOT NULL,
        idempotency_key TEXT UNIQUE NOT NULL,
        gateway_name TEXT NOT NULL,
        gateway_order_id TEXT,
        gateway_payment_id TEXT,
        status TEXT DEFAULT 'INITIATED',
        raw_payload TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(loan_id) REFERENCES loans(id) ON DELETE CASCADE
    );
    """)

    # 8. Immutable Audit Logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        org_id TEXT,
        user_id TEXT,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        previous_state TEXT,
        new_state TEXT,
        notes TEXT,
        ip_address TEXT DEFAULT '127.0.0.1',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 9. Reminders & Notifications Log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        borrower_id TEXT NOT NULL,
        loan_id TEXT NOT NULL,
        channel TEXT NOT NULL, -- SMS, EMAIL, WHATSAPP
        message TEXT NOT NULL,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'DELIVERED'
    );
    """)

    # Create Indexes for Tenant Isolation & Speed
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_org ON users(org_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_borrowers_org ON borrowers(org_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_loans_org ON loans(org_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_loan ON ledger_entries(loan_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_logs(org_id);")

    conn.commit()
    seed_database(conn)
    conn.close()

def seed_database(conn):
    """Zero-seeding policy: Production database starts 100% empty for user registration."""
    pass

def seed_test_fixtures(conn):
    """Populates isolated test environment entities for test suite assertions."""
    cursor = conn.cursor()

    # Admin & Webhook user
    cursor.execute("INSERT OR IGNORE INTO users (id, org_id, role, full_name, email, phone, password_hash) VALUES ('user_admin', NULL, 'SYSTEM_ADMIN', 'Platform Administrator', 'admin@local', '9000000000', ?)", (hash_password("admin123"),))
    cursor.execute("INSERT OR IGNORE INTO users (id, org_id, role, full_name, email, phone, password_hash) VALUES ('system_webhook', NULL, 'SYSTEM_ADMIN', 'System Webhook Listener', 'system_webhook@local', '0000000001', ?)", (hash_password("admin123"),))

    # Org 1: Apex Capital
    org1_id = "org_apex"
    cursor.execute("INSERT OR IGNORE INTO organizations (id, name, registration_number, email, phone, address, verification_status) VALUES (?, 'Apex Capital Finance', 'FIN-2026-APEX-88', 'contact@apexcapital.com', '9876500000', 'Mumbai', 'VERIFIED')", (org1_id,))

    # Staff
    owner_id = "user_apex_owner"
    mgr_id = "user_apex_mgr"
    acct_id = "user_apex_acct"
    agent_id = "user_apex_agent"

    cursor.execute("INSERT OR IGNORE INTO users (id, org_id, role, full_name, email, phone, password_hash) VALUES (?, ?, 'FINANCIER_OWNER', 'Vikram Malhotra', 'owner@apex.com', '9876500001', ?)", (owner_id, org1_id, hash_password("password123")))
    cursor.execute("INSERT OR IGNORE INTO users (id, org_id, role, full_name, email, phone, password_hash) VALUES (?, ?, 'MANAGER', 'Ananya Roy', 'manager@apex.com', '9876500002', ?)", (mgr_id, org1_id, hash_password("password123")))
    cursor.execute("INSERT OR IGNORE INTO users (id, org_id, role, full_name, email, phone, password_hash) VALUES (?, ?, 'ACCOUNTANT', 'Suresh Kumar', 'accountant@apex.com', '9876500003', ?)", (acct_id, org1_id, hash_password("password123")))
    cursor.execute("INSERT OR IGNORE INTO users (id, org_id, role, full_name, email, phone, password_hash) VALUES (?, ?, 'AGENT', 'Rohan Verma', 'agent@apex.com', '9876500004', ?)", (agent_id, org1_id, hash_password("password123")))

    # Borrower 1 Profile
    bor_user_id = "user_rahul"
    cursor.execute("INSERT OR IGNORE INTO users (id, org_id, role, full_name, email, phone, password_hash) VALUES (?, ?, 'BORROWER', 'Rahul Sharma', 'rahul@example.com', '9876543210', ?)", (bor_user_id, org1_id, hash_password("password123")))

    bor1_id = "bor_rahul"
    cursor.execute("INSERT OR IGNORE INTO borrowers (id, org_id, user_id, full_name, phone, email, address, kyc_id_type, kyc_id_number, assigned_agent_id) VALUES (?, ?, ?, 'Rahul Sharma', '9876543210', 'rahul@example.com', 'Mumbai', 'AADHAAR', '1234-5678-9012', ?)", (bor1_id, org1_id, bor_user_id, agent_id))

    # Borrower 2 Profile
    bor2_id = "bor_priya"
    cursor.execute("INSERT OR IGNORE INTO borrowers (id, org_id, user_id, full_name, phone, email, address, kyc_id_type, kyc_id_number, assigned_agent_id) VALUES (?, ?, NULL, 'Priya Patel', '9876543211', 'priya@example.com', 'Gurgaon', 'PAN', 'ABCDE1234F', ?)", (bor2_id, org1_id, agent_id))

    # Loan 1
    loan1_id = "loan_apex_101"
    p1 = 100000.0
    rate1 = 14.0
    start_date1 = datetime.date.today().isoformat()

    from backend.services.loan_engine import LoanEngine
    from backend.services.ledger_service import LedgerService

    sched1 = LoanEngine.generate_schedule(p1, rate1, 'REDUCING_BALANCE', 'MONTHLY', 12, start_date1)

    cursor.execute("""
        INSERT OR IGNORE INTO loans (id, org_id, borrower_id, principal_amount, interest_rate_annual, interest_type, frequency, tenure_periods, start_date, total_interest, total_payable, outstanding_principal, outstanding_interest, status)
        VALUES (?, ?, ?, ?, ?, 'REDUCING_BALANCE', 'MONTHLY', 12, ?, ?, ?, ?, 0.0000, 'ACTIVE')
    """, (loan1_id, org1_id, bor1_id, p1, rate1, start_date1, float(sched1['total_interest']), float(sched1['total_payable']), p1))

    for inst in sched1['installments']:
        sch_id = f"sch_101_{inst['installment_number']}"
        cursor.execute("""
            INSERT OR IGNORE INTO repayment_schedules (id, loan_id, installment_number, due_date, principal_due, interest_due, total_due, principal_paid, interest_paid, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0.0000, 0.0000, 'DUE')
        """, (sch_id, loan1_id, inst['installment_number'], inst['due_date'], float(inst['principal_due']), float(inst['interest_due']), float(inst['total_due'])))

    LedgerService.post_disbursal(org1_id, loan1_id, Decimal(str(p1)), owner_id)


    # Org 2: Nova
    org2_id = "org_nova"
    cursor.execute("INSERT OR IGNORE INTO organizations (id, name, registration_number, email, phone, address, verification_status) VALUES (?, 'Nova Microfinance', 'FIN-2026-NOVA-44', 'contact@novamicro.com', '9898000000', 'Bengaluru', 'VERIFIED')", (org2_id,))
    cursor.execute("INSERT OR IGNORE INTO users (id, org_id, role, full_name, email, phone, password_hash) VALUES ('user_nova_owner', ?, 'FINANCIER_OWNER', 'Siddharth Rao', 'owner@nova.com', '9898000001', ?)", (org2_id, hash_password("password123")))

    conn.commit()

def reset_db():
    """Clears all table rows and reinitializes test fixtures for test isolation."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF;")
    tables = ['notifications', 'audit_logs', 'payment_attempts', 'ledger_entries', 'repayment_schedules', 'loans', 'borrowers', 'users', 'organizations']
    for t in tables:
        try:
            cursor.execute(f"DELETE FROM {t};")
        except Exception:
            pass
    cursor.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    seed_test_fixtures(conn)
    conn.close()



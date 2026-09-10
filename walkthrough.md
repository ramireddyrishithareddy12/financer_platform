# Detailed Architectural Walkthrough & Technical Guide

This document provides an in-depth technical explanation of the **FinOffice Private Finance Office Management Platform**.

---

## 1. Project Architecture

The application is structured following clean production architecture principles:

```
[ Frontend SPA (HTML5/JS/CSS) ]
              │ (HTTPS REST API / JSON)
              ▼
[ Flask Application Core (app.py) ]
              │
    ┌─────────┼──────────┬──────────┬──────────┐
    ▼         ▼          ▼          ▼          ▼
 [Auth BP] [Financier] [Borrower] [Payments] [Admin]
    │         │          │          │          │
    └─────────┴──────────┼──────────┴──────────┘
                         ▼
        [ Business Logic & Services Layer ]
          ├── Loan Engine (Decimal Math)
          ├── Financial Ledger Service (Double-Entry)
          ├── Payment Service (Idempotency & HMAC)
          └── Audit Service (Immutable Logs)
                         │
                         ▼
     [ Relational SQLite DB (WAL Mode + FKs) ]
```

---

## 2. Folder Structure

```
financier_platform/
├── backend/
│   ├── app.py                 # Main Flask application initialization & SPA router
│   ├── database.py            # Normalized SQLite schema definition & pool connections
│   ├── blueprints/
│   │   ├── auth_bp.py         # User registration, login, profile view & updates
│   │   ├── financier_bp.py    # Executive KPIs, borrower management, loan origination, cash desk, reversals
│   │   ├── borrower_bp.py     # Borrower self-service portal, schedule, digital receipts, loan statements
│   │   ├── payment_bp.py      # Digital payment initiation, gateway simulation, HMAC webhook handling
│   │   └── admin_bp.py        # System admin tenant management & platform audit logs
│   └── services/
│       ├── loan_engine.py     # Multi-method loan calculation engine (Decimal 4-place precision)
│       ├── ledger_service.py   # Double-entry ledger, early settlement, payment recording & reversals
│       ├── payment_service.py  # Gateway attempt tracking, idempotency keys & webhook verification
│       └── audit_service.py   # System-wide immutable audit trail logging
├── frontend/
│   ├── index.html             # Auth views, Financier Dashboard, Borrower Module, Modal dialogs
│   ├── app.js                 # Frontend application state, REST API calls, UI router, UPI simulation
│   ├── styles.css             # Responsive fintech design system, theme tokens, print stylesheets
│   └── i18n.js                # Localization dictionaries (English, Hindi, Tamil, Telugu, Kannada)
├── tests/
│   ├── test_financial_invariants.py # Formally asserts 10 core financial & security invariants
│   ├── test_ledger_and_security.py   # Double-entry ledger debits=credits, reversals, tenant isolation
│   ├── test_loan_engine.py           # Reducing balance, flat rate, simple interest schedule tests
│   ├── test_rule_of_78s_audit.py     # Rule of 78s sum-of-digits formula audit
│   └── test_security_audit.py        # Privilege escalation, BOLA/IDOR, signature tampering tests
├── README.md                  # Quick start guide & run instructions
├── walkthrough.md             # Detailed technical architecture guide
├── requirements.txt           # Python dependencies
└── .env.example               # Environment variables configuration template
```

---

## 3. Database Schema

The database uses a normalized relational schema with foreign key constraints enabled:

1. **`organizations`** (Tenants):
   - `id` (TEXT PRIMARY KEY), `name`, `registration_number`, `email`, `phone`, `address`, `verification_status`, `created_at`.
2. **`users`**:
   - `id` (TEXT PRIMARY KEY), `org_id` (FK), `role` (`FINANCIER_OWNER`, `MANAGER`, `ACCOUNTANT`, `AGENT`, `BORROWER`, `SYSTEM_ADMIN`), `full_name`, `email`, `phone`, `password_hash`, `status`, `created_at`.
3. **`borrowers`**:
   - `id` (TEXT PRIMARY KEY), `org_id` (FK), `user_id` (FK), `full_name`, `phone`, `email`, `address`, `kyc_id_type`, `kyc_id_number`, `assigned_agent_id` (FK), `created_at`.
4. **`loans`**:
   - `id` (TEXT PRIMARY KEY), `org_id` (FK), `borrower_id` (FK), `principal_amount` (DECIMAL), `interest_rate_annual` (DECIMAL), `interest_type`, `frequency`, `tenure_periods`, `start_date`, `total_interest` (DECIMAL), `total_payable` (DECIMAL), `outstanding_principal` (DECIMAL), `outstanding_interest` (DECIMAL), `status` (`ACTIVE`, `COMPLETED`), `created_at`.
5. **`repayment_schedules`**:
   - `id` (TEXT PRIMARY KEY), `loan_id` (FK), `installment_number`, `due_date`, `principal_due` (DECIMAL), `interest_due` (DECIMAL), `total_due` (DECIMAL), `principal_paid` (DECIMAL), `interest_paid` (DECIMAL), `status` (`DUE`, `PARTIAL`, `PAID`, `OVERDUE`).
6. **`ledger_entries`** (Double-Entry Source of Truth):
   - `id` (TEXT PRIMARY KEY), `org_id` (FK), `loan_id` (FK), `schedule_id` (FK), `entry_type` (`LOAN_DISBURSED`, `PAYMENT_RECEIVED`, `REVERSAL`, `INTEREST_WAIVER`), `amount` (DECIMAL), `principal_component` (DECIMAL), `interest_component` (DECIMAL), `fee_component` (DECIMAL), `debit_account`, `credit_account`, `payment_method`, `reference_id`, `notes`, `created_by` (FK), `created_at`.
7. **`payment_attempts`**:
   - `id` (TEXT PRIMARY KEY), `loan_id` (FK), `schedule_id` (FK), `amount` (DECIMAL), `idempotency_key` (UNIQUE), `gateway_name`, `gateway_order_id`, `gateway_payment_id`, `status` (`INITIATED`, `SUCCESS`, `FAILED`), `created_at`.
8. **`audit_logs`**:
   - `id` (TEXT PRIMARY KEY), `org_id`, `user_id`, `action`, `entity_type`, `entity_id`, `previous_state`, `new_state`, `notes`, `ip_address`, `created_at`.

---

## 4. Authentication & Authorization

- **Password Hashing**: Passwords are hashed using **PBKDF2 with SHA-256** (100,000 iterations) with salt.
- **Tenant Context**: All API requests pass `X-Org-Id`, `X-User-Id`, and `X-User-Role` headers.
- **Role-Based Access Control (RBAC)**:
  - `FINANCIER_OWNER`: Full administrative & financial control over organization.
  - `MANAGER`: Can disburse loans, record payments, execute reversals, and archive borrowers.
  - `ACCOUNTANT`: Can record payments and inspect ledger reports.
  - `AGENT`: Can view assigned borrowers and record payments. Restricted from disbursing loans or reversing entries.
  - `BORROWER`: Restricted to self-service view of own loan details, schedule, receipts, and UPI payment initiation.
- **Tenant Isolation**: Every database query enforces `WHERE org_id = ?` to prevent cross-tenant data leakage (IDOR / BOLA protection).

---

## 5. Loan Calculation Engine

The calculation engine (`backend/services/loan_engine.py`) uses Python `Decimal` 4-place precision (`Decimal('0.0001')`) and half-up rounding rules to avoid floating-point arithmetic drift.

Supported Calculation Methods:
1. **Reducing Balance (Amortization / EMI)**:
   \[
   PMT = P \times \frac{r(1+r)^n}{(1+r)^n - 1}
   \]
   Interest is calculated per period on remaining principal balance.
2. **Flat Rate**:
   Total Interest = \(P \times r_{annual} \times t_{years}\). Interest and principal are divided equally across tenure periods.
3. **Simple Interest**:
   Interest calculated strictly on original principal.
4. **Rule of 78s (Sum-of-Digits)**:
   \[
   \text{Sum of Digits} = \frac{n(n+1)}{2}
   \]
   Interest allocated proportionately using reverse digit ordering.

---

## 6. Financial Ledger Architecture

The ledger (`backend/services/ledger_service.py`) acts as the authoritative financial source of truth:
- **Double-Entry Balance Invariant**: Every transaction creates debits and credits such that \(\sum \text{DEBITS} = \sum \text{CREDITS}\).
  - Loan Disbursal: Debit `LOANS_RECEIVABLE_ASSET`, Credit `CASH_BANK_ASSET`.
  - Payment Received: Debit `CASH_BANK_ASSET`, Credit `LOANS_RECEIVABLE_ASSET`.
- **Reversals**: Simple `DELETE` operations are forbidden. Reversing a transaction preserves the original entry and posts a counter-entry (`REVERSAL`) with explicit debit/credit swapping and audit trail reference.

---

## 7. Payment Flow & Webhook Verification

```
[ Borrower Portal ] ──(Initiate)──> [/api/v1/payments/initiate]
                                              │ (Creates payment_attempt)
                                              ▼
[ Provider Gateway ] <──(HMAC Sign)── [/simulate-gateway-payment]
          │
          ▼ (HTTP POST Callback with X-Razorpay-Signature)
[ Server Webhook Endpoint: /api/v1/payments/webhook ]
          │
          ├── 1. Compute HMAC SHA-256(raw_payload, GATEWAY_SHARED_SECRET)
          ├── 2. Verify signature matches header
          ├── 3. Check idempotency_key in payment_attempts
          ├── 4. Post Ledger Entry & update Repayment Schedule
          └── 5. Generate Cryptographic Receipt
```

---

## 8. Security Controls

- **Input Validation**: Strict field presence and type checking.
- **SQL Injection**: Parameterized SQL queries throughout SQLite driver.
- **BOLA / IDOR Protection**: Server-side tenant `org_id` and `user_id` verification on all resources.
- **Privilege Escalation Prevention**: Non-owners/managers are blocked from administrative routes.
- **Immutability**: Financial transactions and audit logs cannot be overwritten or deleted.

---

## 9. Testing & Verification

Run automated test suite:

```powershell
python -m unittest discover -s tests
```

Tests cover:
- Double-entry balance equality (\(\sum \text{DEBITS} = \sum \text{CREDITS}\))
- Idempotency protection against duplicate webhook callbacks
- Reversal entry history preservation
- Multi-tenant isolation
- Early settlement unearned interest calculation
- Security privilege escalation rejections

---

## 10. Local Setup Instructions

```powershell
# 1. Navigate to directory
cd C:\Users\rishi\.gemini\antigravity\scratch\financier_platform

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start server
python backend/app.py
```

Open browser: [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 11. Production Deployment Configuration

For production deployment:
1. **WSGI Server**: Use `gunicorn` or `waitress` instead of Flask development server:
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 "backend.app:create_app()"
   ```
2. **Database Migration**: For multi-server scalability, migrate SQLite to PostgreSQL with Decimal columns.
3. **Environment Secrets**: Store `GATEWAY_SHARED_SECRET` and `SECRET_KEY` in environment variables or cloud secret managers.
4. **HTTPS**: Enable SSL/TLS termination via Nginx or Cloudflare.
5. **Real Payment Providers**: Replace simulated gateway secret with official Razorpay / Cashfree / PayU API keys and webhook secrets.

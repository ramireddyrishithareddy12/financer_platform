# FinOffice — Private Finance Office Management Platform

FinOffice is a complete, production-oriented private finance office management platform built for individual financiers who lend money and need to manage borrowers, loan origination, repayment schedules, double-entry financial ledgers, receipts, loan statements, audit logs, and verified UPI payment integrations.

> [!IMPORTANT]
> **PRISTINE BLANK SYSTEM ON FIRST LAUNCH**
> The application initializes with an **EXACTLY ZERO-RECORD DATABASE** (`0 organizations, 0 users, 0 borrowers, 0 loans, 0 ledger entries, 0 audit logs`). No sample financiers, sample borrowers, fake names ("Rohan", "Ravi", "Suresh", "Priya"), or fake transactions exist. The first person opening the app registers their own account.

---

## 🛠️ Tech Stack & Architecture

- **Backend**: Python (Flask REST APIs, Blueprints, modular architecture)
- **Database**: Relational SQLite (WAL Mode, Foreign Key constraints, Decimal precision for monetary integrity)
- **Frontend**: HTML5, Vanilla JavaScript, Vanilla CSS (Modern fintech dark/light theme, responsive layout, glassmorphism cards, printable receipts & statements)
- **Financial Ledger**: Double-entry accounting source of truth (`DEBITS = CREDITS`)
- **Loan Math Engine**: Python `Decimal` 4-place precision supporting:
  - Reducing Balance Amortization / EMI
  - Flat Interest Rate
  - Simple Interest
  - Rule of 78s / Sum-of-Digits
- **Security**: PBKDF2 SHA-256 password hashing, server-side RBAC (`FINANCIER_OWNER`, `MANAGER`, `ACCOUNTANT`, `AGENT`, `BORROWER`, `SYSTEM_ADMIN`), tenant isolation (`X-Org-Id`), HMAC SHA-256 webhook verification, idempotency checking.

---

## 📁 Directory Structure

```
financier_platform/
├── backend/
│   ├── app.py                 # Main Flask server entrypoint & SPA static router
│   ├── database.py            # SQLite database initialization & schema definition
│   ├── blueprints/
│   │   ├── auth_bp.py         # Registration, login, profile view/edit APIs
│   │   ├── financier_bp.py    # Dashboard KPIs, borrower CRUD, loan origination, cash desk, reversals, audit
│   │   ├── borrower_bp.py     # Borrower self-service, schedule, receipt & statement endpoints
│   │   ├── payment_bp.py      # Digital payment initiation, gateway simulation, HMAC webhook
│   │   └── admin_bp.py        # System admin platform management & global audit logs
│   └── services/
│       ├── loan_engine.py     # Modular loan calculation engine & rounding rules
│       ├── ledger_service.py   # Double-entry ledger, early settlement, payment recording & reversals
│       ├── payment_service.py  # Gateway attempt management, idempotency & HMAC verification
│       └── audit_service.py   # Immutable audit trail logging
├── frontend/
│   ├── index.html             # Auth screens, Financier Dashboard, Borrower Module, Modals
│   ├── app.js                 # State management, API calls, zero-state logic, payment simulation
│   ├── styles.css             # Responsive fintech design system, theme tokens & print stylesheets
│   └── i18n.js                # Indian language localization dictionaries (English, Hindi, Tamil, Telugu, Kannada)
├── tests/                     # Automated unittest suite covering math, security, ledger, and invariants
├── README.md                  # Installation & local run instructions
├── walkthrough.md             # In-depth architectural documentation
├── requirements.txt           # Python backend dependencies
└── .env.example               # Environment variables configuration template
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.9 or higher

### 2. Environment Setup
```powershell
# Navigate to project directory
cd C:\Users\rishi\.gemini\antigravity\scratch\financier_platform

# Install dependencies (Flask & standard library)
pip install -r requirements.txt
```

### 3. Running the Server Locally
```powershell
python backend/app.py
```

The server will initialize an empty database at `backend/creditorpulse.db` and start listening at:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 🧪 Running Automated Tests

Run the automated test suite to verify math engine correctness, double-entry ledger balance invariants, tenant isolation, and security controls:

```powershell
python -m unittest discover -s tests
```

---

## 📜 User Workflow

1. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.
2. Click **Create Account** to register your own Financier account (Full Name, Mobile, Email, Business Name, Password).
3. Log in to view your clean, zero-data dashboard (`Total Borrowers: 0`, `Total Lent: ₹0`, `Outstanding: ₹0`).
4. Click **+ ADD BORROWER** to add your real borrowers.
5. Click **+ Disburse New Loan** to select a borrower and configure actual loan terms.
6. Click any Borrower Card on the dashboard to open the dedicated **Borrower Module** to record payments, send payment reminders, issue digital receipts, download loan statements, or calculate early settlement quotes.

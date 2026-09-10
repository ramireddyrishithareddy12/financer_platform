/**
 * FinOffice — Private Finance Office Application Logic
 * Pure client-side state management, REST API communication, zero-state handlers,
 * borrower modules, loan calculations, ledger updates, and dynamic payment gateways.
 */

// Application State
let currentUser = null; // { id, org_id, org_name, full_name, email, phone, role, token }
let currentModuleBorrower = null; // Active borrower detail object
let searchDebounceTimer = null;

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  // Set default start date in loan form
  const dtInput = document.getElementById('dtStartDate');
  if (dtInput) dtInput.value = new Date().toISOString().split('T')[0];

  // Restore existing session if present
  const savedUser = localStorage.getItem('finoffice_user');
  if (savedUser) {
    try {
      currentUser = JSON.parse(savedUser);
      showAuthenticatedApp();
    } catch (e) {
      localStorage.removeItem('finoffice_user');
      showAuthScreen();
    }
  } else {
    showAuthScreen();
  }
});

// Helper for API request headers
function getApiHeaders() {
  if (!currentUser) return { 'Content-Type': 'application/json' };
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${currentUser.token}`,
    'X-Org-Id': currentUser.org_id || '',
    'X-User-Id': currentUser.id || '',
    'X-User-Role': currentUser.role || 'FINANCIER_OWNER'
  };
}

// ----------------- AUTHENTICATION FLOW ----------------- //

function showAuthScreen() {
  currentUser = null;
  document.getElementById('topHeader').style.display = 'none';
  document.getElementById('mainNavbar').style.display = 'none';
  
  document.querySelectorAll('.view-panel').forEach(v => v.classList.remove('active'));
  document.getElementById('view-auth').classList.add('active');
}

function showAuthenticatedApp() {
  document.getElementById('topHeader').style.display = 'flex';
  document.getElementById('mainNavbar').style.display = 'block';

  document.getElementById('lblUserGreeting').textContent = `Welcome, ${currentUser.full_name}`;
  document.getElementById('lblOrgBadge').textContent = currentUser.org_name || 'My Finance Office';

  // Toggle nav items based on role
  const borNav = document.getElementById('navBorrowerItem');
  if (borNav) {
    borNav.style.display = (currentUser.role === 'BORROWER') ? 'inline-block' : 'none';
  }

  if (currentUser.role === 'BORROWER') {
    showTab('borrowerPortal');
  } else {
    showTab('dashboard');
  }
}

function switchAuthTab(tab) {
  document.getElementById('btnTabLogin').classList.toggle('active', tab === 'login');
  document.getElementById('btnTabRegister').classList.toggle('active', tab === 'register');
  document.getElementById('frmLogin').classList.toggle('active', tab === 'login');
  document.getElementById('frmRegister').classList.toggle('active', tab === 'register');
}

async function handleLogin(e) {
  e.preventDefault();
  const identifier = document.getElementById('loginIdentifier').value.trim();
  const password = document.getElementById('loginPassword').value.trim();
  const role = document.getElementById('loginRole').value;

  try {
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, password, role })
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "Login failed. Check your credentials.");
      return;
    }

    currentUser = data.user;
    currentUser.token = data.token;
    localStorage.setItem('finoffice_user', JSON.stringify(currentUser));

    showAuthenticatedApp();
  } catch (err) {
    alert("Network error. Server might be offline.");
  }
}

async function handleRegister(e) {
  e.preventDefault();
  const owner_name = document.getElementById('regFullName').value.trim();
  const phone = document.getElementById('regPhone').value.trim();
  const email = document.getElementById('regEmail').value.trim();
  const org_name = document.getElementById('regOrgName').value.trim() || `${owner_name}'s Finance Office`;
  const address = document.getElementById('regAddress').value.trim();
  const password = document.getElementById('regPassword').value.trim();

  try {
    const res = await fetch('/api/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner_name, phone, email, org_name, address, password })
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "Registration failed.");
      return;
    }

    // Auto-login after registration
    currentUser = data.user;
    currentUser.token = `token_${data.user.id}`;
    localStorage.setItem('finoffice_user', JSON.stringify(currentUser));

    alert("Account registered successfully! Welcome to your Finance Office.");
    showAuthenticatedApp();
  } catch (err) {
    alert("Network error during registration.");
  }
}

function handleLogout() {
  localStorage.removeItem('finoffice_user');
  showAuthScreen();
}

// ----------------- TAB ROUTER ----------------- //

function showTab(tabName) {
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.view-panel').forEach(el => el.classList.remove('active'));

  const activePanel = document.getElementById(`view-${tabName}`);
  if (activePanel) activePanel.classList.add('active');

  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(item => {
    if (item.getAttribute('onclick') && item.getAttribute('onclick').includes(tabName)) {
      item.classList.add('active');
    }
  });

  if (tabName === 'dashboard') loadDashboardMetrics();
  else if (tabName === 'borrowers') loadBorrowersDirectory();
  else if (tabName === 'origination') initLoanStudio();
  else if (tabName === 'cashdesk') initCashDesk();
  else if (tabName === 'reminders') loadReminders();
  else if (tabName === 'audit') loadAuditLogs();
  else if (tabName === 'borrowerPortal') loadBorrowerPortal();
}

// ----------------- FINANCIER DASHBOARD ----------------- //

async function loadDashboardMetrics() {
  try {
    const res = await fetch('/api/v1/financier/dashboard', { headers: getApiHeaders() });
    if (!res.ok) return;
    const data = await res.json();

    // Populate Dynamic KPI Counters
    document.getElementById('txtWelcomeTitle').textContent = `Welcome, ${currentUser.full_name}`;
    document.getElementById('kpiTotalBorrowers').textContent = data.active_borrowers_count || 0;
    document.getElementById('kpiActiveLoans').textContent = data.active_loans_count || 0;
    document.getElementById('kpiTotalLent').textContent = `₹${(data.total_principal_outstanding + data.total_collected).toLocaleString('en-IN')}`;
    document.getElementById('kpiCollected').textContent = `₹${data.total_collected.toLocaleString('en-IN')}`;
    document.getElementById('kpiOutstanding').textContent = `₹${data.total_principal_outstanding.toLocaleString('en-IN')}`;
    document.getElementById('kpiDueToday').textContent = `₹${data.due_today.toLocaleString('en-IN')}`;
    document.getElementById('kpiOverdue').textContent = `₹${data.overdue_amount.toLocaleString('en-IN')}`;
    document.getElementById('kpiOverdueBorrowers').textContent = data.overdue_borrowers_count || 0;

    // Zero-State toggle
    const emptyBox = document.getElementById('boxEmptyState');
    if (data.active_borrowers_count === 0) {
      emptyBox.style.display = 'block';
    } else {
      emptyBox.style.display = 'none';
    }

    // Load Borrower Cards Grid
    loadBorrowerCardsGrid();
  } catch (err) {
    console.error("Failed to load dashboard metrics:", err);
  }
}

function debounceSearchBorrowers() {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(loadBorrowerCardsGrid, 300);
}

async function loadBorrowerCardsGrid() {
  const grid = document.getElementById('borrowerCardsGrid');
  grid.innerHTML = '<div style="grid-column: 1/-1; padding: 20px; text-align: center;">Loading borrower cards...</div>';

  const q = document.getElementById('searchBorrower').value.trim();
  const status = document.getElementById('filterStatus').value;

  try {
    const res = await fetch(`/api/v1/financier/borrowers?q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}`, {
      headers: getApiHeaders()
    });
    const borrowers = await res.json();

    if (!borrowers.length) {
      grid.innerHTML = `
        <div style="grid-column: 1/-1; padding: 40px; text-align: center; color: var(--text-muted);">
          No borrowers match the current search filter.
        </div>
      `;
      return;
    }

    grid.innerHTML = borrowers.map(b => {
      const loanText = b.principal_amount ? `₹${b.principal_amount.toLocaleString('en-IN')}` : 'No Loan Disbursed';
      const paidText = b.total_paid ? `₹${b.total_paid.toLocaleString('en-IN')}` : '₹0';
      const outText = b.outstanding_principal ? `₹${b.outstanding_principal.toLocaleString('en-IN')}` : '₹0';
      const nextDueText = b.next_due_amount ? `₹${b.next_due_amount.toLocaleString('en-IN')}` : 'None';
      const nextDateText = b.next_due_date || '--';

      return `
        <div class="borrower-card">
          <div class="borrower-card-header">
            <h3 class="borrower-name">${escapeHtml(b.full_name)}</h3>
            <span class="badge ${b.loan_status === 'COMPLETED' ? 'badge-success' : 'badge-primary'}">${b.loan_status || 'REGISTERED'}</span>
          </div>
          <div class="borrower-card-body">
            <div class="card-prop"><span>Mobile:</span> <strong>${escapeHtml(b.phone)}</strong></div>
            <div class="card-prop"><span>Loan Amount:</span> <strong>${loanText}</strong></div>
            <div class="card-prop"><span>Interest:</span> <span>${b.interest_rate_annual ? b.interest_rate_annual + '% (' + b.interest_type + ')' : '--'}</span></div>
            <div class="card-prop"><span>Total Paid:</span> <strong style="color: var(--accent-success);">${paidText}</strong></div>
            <div class="card-prop"><span>Outstanding:</span> <strong style="color: var(--accent-warning);">${outText}</strong></div>
            <div class="card-prop"><span>Next Due:</span> <strong>${nextDueText}</strong> <small>(${nextDateText})</small></div>
          </div>
          <div class="borrower-card-footer">
            <button class="btn btn-sm btn-primary btn-block" onclick="openBorrowerModule('${b.id}')">
              Open Borrower Module →
            </button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    grid.innerHTML = '<div style="grid-column: 1/-1; padding: 20px; text-align: center; color: var(--accent-danger);">Failed to load borrowers.</div>';
  }
}

// ----------------- BORROWER DIRECTORY ----------------- //

async function loadBorrowersDirectory() {
  const tbody = document.getElementById('tblBorrowersBody');
  tbody.innerHTML = '<tr><td colspan="8">Loading borrowers...</td></tr>';

  try {
    const res = await fetch('/api/v1/financier/borrowers', { headers: getApiHeaders() });
    const borrowers = await res.json();

    if (!borrowers.length) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 30px;">No borrowers registered yet. Click "+ ADD BORROWER" to get started.</td></tr>';
      return;
    }

    tbody.innerHTML = borrowers.map(b => `
      <tr>
        <td><strong>${escapeHtml(b.full_name)}</strong></td>
        <td>${escapeHtml(b.phone)}</td>
        <td>${escapeHtml(b.address || '--')}</td>
        <td>${b.principal_amount ? '₹' + b.principal_amount.toLocaleString('en-IN') : 'No Loan'}</td>
        <td style="color: var(--accent-success);">₹${b.total_paid ? b.total_paid.toLocaleString('en-IN') : 0}</td>
        <td style="color: var(--accent-warning);">₹${b.outstanding_principal ? b.outstanding_principal.toLocaleString('en-IN') : 0}</td>
        <td>${b.next_due_amount ? '₹' + b.next_due_amount.toLocaleString('en-IN') + ' (' + b.next_due_date + ')' : '--'}</td>
        <td>
          <button class="btn btn-sm btn-secondary" onclick="openBorrowerModule('${b.id}')">View Module</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="8">Failed to load borrower directory.</td></tr>';
  }
}

function openAddBorrowerModal() {
  document.getElementById('addBorName').value = '';
  document.getElementById('addBorPhone').value = '';
  document.getElementById('addBorEmail').value = '';
  document.getElementById('addBorAddress').value = '';
  document.getElementById('addBorKycNum').value = '';
  openModal('modalAddBorrower');
}

async function handleCreateBorrower(e) {
  e.preventDefault();
  const full_name = document.getElementById('addBorName').value.trim();
  const phone = document.getElementById('addBorPhone').value.trim();
  const email = document.getElementById('addBorEmail').value.trim();
  const address = document.getElementById('addBorAddress').value.trim();
  const kyc_id_type = document.getElementById('addBorKycType').value;
  const kyc_id_number = document.getElementById('addBorKycNum').value.trim();

  try {
    const res = await fetch('/api/v1/financier/borrowers', {
      method: 'POST',
      headers: getApiHeaders(),
      body: JSON.stringify({ full_name, phone, email, address, kyc_id_type, kyc_id_number })
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "Failed to create borrower.");
      return;
    }

    closeModal('modalAddBorrower');
    alert(`Borrower "${full_name}" created successfully!`);
    loadDashboardMetrics();
  } catch (err) {
    alert("Network error while creating borrower.");
  }
}

// ----------------- DEDICATED BORROWER MODULE ----------------- //

async function openBorrowerModule(borrowerId) {
  try {
    const res = await fetch(`/api/v1/financier/borrowers/${borrowerId}/detail`, { headers: getApiHeaders() });
    if (!res.ok) {
      alert("Failed to load borrower detail module.");
      return;
    }
    const data = await res.json();
    currentModuleBorrower = data;

    // Header & Info
    document.getElementById('modBorName').textContent = data.borrower.full_name;
    document.getElementById('modBorPhone').textContent = data.borrower.phone;
    document.getElementById('modBorAddress').textContent = data.borrower.address || 'Not Provided';

    // Summary Box
    if (data.loan) {
      const l = data.loan;
      document.getElementById('modSumOriginal').textContent = `₹${l.principal_amount.toLocaleString('en-IN')}`;
      document.getElementById('modSumRate').textContent = `${l.interest_rate_annual}% (${l.interest_type})`;
      document.getElementById('modSumTotInterest').textContent = `₹${l.total_interest.toLocaleString('en-IN')}`;
      document.getElementById('modSumTotPayable').textContent = `₹${l.total_payable.toLocaleString('en-IN')}`;
      document.getElementById('modSumPaid').textContent = `₹${l.total_paid.toLocaleString('en-IN')}`;
      document.getElementById('modSumPrincPaid').textContent = `₹${l.principal_paid.toLocaleString('en-IN')}`;
      document.getElementById('modSumIntPaid').textContent = `₹${l.interest_paid.toLocaleString('en-IN')}`;
      document.getElementById('modSumOutstanding').textContent = `₹${l.outstanding_balance.toLocaleString('en-IN')}`;
      document.getElementById('modSumRemInterest').textContent = `₹${l.remaining_interest.toLocaleString('en-IN')}`;
      document.getElementById('modSumRemInst').textContent = l.remaining_installments;
      document.getElementById('modSumNextAmt').textContent = `₹${l.next_amount_due.toLocaleString('en-IN')}`;
      document.getElementById('modSumNextDate').textContent = l.next_due_date || 'COMPLETED';
    } else {
      ['modSumOriginal','modSumTotInterest','modSumTotPayable','modSumPaid','modSumPrincPaid','modSumIntPaid','modSumOutstanding','modSumRemInterest','modSumNextAmt'].forEach(id => {
        document.getElementById(id).textContent = '₹0.00';
      });
      document.getElementById('modSumRate').textContent = 'No Loan Active';
      document.getElementById('modSumRemInst').textContent = '0';
      document.getElementById('modSumNextDate').textContent = '--';
    }

    // Schedule Table
    const tbodySched = document.getElementById('tblModScheduleBody');
    if (data.schedule && data.schedule.length > 0) {
      tbodySched.innerHTML = data.schedule.map(s => `
        <tr>
          <td>#${s.installment_number}</td>
          <td>${s.due_date}</td>
          <td>₹${s.principal_due.toLocaleString('en-IN')}</td>
          <td>₹${s.interest_due.toLocaleString('en-IN')}</td>
          <td><strong>₹${s.total_due.toLocaleString('en-IN')}</strong></td>
          <td style="color: var(--accent-success);">₹${(s.principal_paid + s.interest_paid).toLocaleString('en-IN')}</td>
          <td style="color: var(--accent-warning);">₹${s.remaining_amount.toLocaleString('en-IN')}</td>
          <td><span class="badge ${s.status === 'PAID' ? 'badge-success' : s.status === 'OVERDUE' ? 'badge-danger' : 'badge-warning'}">${s.status}</span></td>
        </tr>
      `).join('');
    } else {
      tbodySched.innerHTML = '<tr><td colspan="8">No active repayment schedule found. Click "+ Add Loan" above to disburse a loan.</td></tr>';
    }

    // Ledger History Table
    const tbodyLedger = document.getElementById('tblModLedgerBody');
    if (data.payment_history && data.payment_history.length > 0) {
      tbodyLedger.innerHTML = data.payment_history.map(p => `
        <tr>
          <td>${p.created_at}</td>
          <td><strong style="color: var(--accent-success);">₹${p.amount.toLocaleString('en-IN')}</strong></td>
          <td>₹${p.principal_component.toLocaleString('en-IN')}</td>
          <td>₹${p.interest_component.toLocaleString('en-IN')}</td>
          <td>${p.payment_method}</td>
          <td><code>${p.reference_id || '--'}</code></td>
          <td>${p.recorder_name || 'Staff'}</td>
          <td><button class="btn btn-sm btn-secondary" onclick="viewReceipt('${p.id}')">Receipt</button></td>
        </tr>
      `).join('');
    } else {
      tbodyLedger.innerHTML = '<tr><td colspan="8">No payment transactions recorded yet.</td></tr>';
    }

    switchModTab('schedule');
    openModal('modalBorrowerModule');
  } catch (err) {
    alert("Error loading borrower module.");
  }
}

function switchModTab(tab) {
  document.getElementById('btnModTabSched').classList.toggle('active', tab === 'schedule');
  document.getElementById('btnModTabLedger').classList.toggle('active', tab === 'ledger');
  document.getElementById('modViewSchedule').style.display = (tab === 'schedule') ? 'block' : 'none';
  document.getElementById('modViewLedger').style.display = (tab === 'ledger') ? 'block' : 'none';
}

function openDisburseForCurrentBorrower() {
  closeModal('modalBorrowerModule');
  showTab('origination');
  if (currentModuleBorrower && currentModuleBorrower.borrower) {
    const sel = document.getElementById('selLoanBorrower');
    if (sel) sel.value = currentModuleBorrower.borrower.id;
  }
}

function openRecordPaymentForCurrentModule() {
  if (!currentModuleBorrower || !currentModuleBorrower.loan) {
    alert("Borrower has no active loan to record payment for.");
    return;
  }
  closeModal('modalBorrowerModule');
  showTab('cashdesk');
  const sel = document.getElementById('selCashLoan');
  if (sel) sel.value = currentModuleBorrower.loan.loan_id;
  document.getElementById('numCashAmount').value = currentModuleBorrower.loan.next_amount_due || 0;
}

function openReminderModalForCurrent() {
  if (!currentModuleBorrower || !currentModuleBorrower.loan) {
    alert("No active loan found for this borrower.");
    return;
  }
  const l = currentModuleBorrower.loan;
  const b = currentModuleBorrower.borrower;
  const msg = `Dear ${b.full_name}, your loan installment of ₹${l.next_amount_due.toFixed(2)} for Loan #${l.loan_id.substring(0, 10)} is due on ${l.next_due_date || 'today'}. Please pay via link: http://${window.location.host}/?pay=${l.loan_id}`;
  
  document.getElementById('txtReminderPreview').value = msg;
  openModal('modalReminder');
}

async function dispatchReminderNow() {
  if (!currentModuleBorrower || !currentModuleBorrower.loan) return;
  const channel = document.getElementById('selReminderChannel').value;

  try {
    const res = await fetch('/api/v1/financier/send-reminder', {
      method: 'POST',
      headers: getApiHeaders(),
      body: JSON.stringify({
        loan_id: currentModuleBorrower.loan.loan_id,
        channel: channel
      })
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || "Failed to dispatch reminder.");
      return;
    }
    alert(`Payment reminder dispatched via ${channel} successfully!`);
    closeModal('modalReminder');
  } catch (err) {
    alert("Network error sending reminder.");
  }
}

function copyReminderText() {
  const txt = document.getElementById('txtReminderPreview');
  txt.select();
  navigator.clipboard.writeText(txt.value);
  alert("Reminder text copied to clipboard!");
}

async function openEarlySettlementForCurrent() {
  if (!currentModuleBorrower || !currentModuleBorrower.loan) return;
  const loan_id = currentModuleBorrower.loan.loan_id;

  try {
    const res = await fetch(`/api/v1/financier/loans/${loan_id}/early-settlement-quote`, { headers: getApiHeaders() });
    const quote = await res.json();

    if (!res.ok) {
      alert(quote.error || "Failed to get early settlement quote.");
      return;
    }

    const confirmMsg = `
EARLY SETTLEMENT QUOTE FOR LOAN #${loan_id.substring(0, 10)}

Principal Remaining: ₹${quote.outstanding_principal.toLocaleString('en-IN')}
Earned Interest: ₹${quote.earned_interest.toLocaleString('en-IN')}
Unearned Interest Waived: ₹${quote.unearned_interest_waived.toLocaleString('en-IN')}
---------------------------------------------
TOTAL SETTLEMENT PAYOFF AMOUNT: ₹${quote.settlement_amount.toLocaleString('en-IN')}

Execute early settlement payoff now?
    `;

    if (confirm(confirmMsg)) {
      const postRes = await fetch(`/api/v1/financier/loans/${loan_id}/early-settlement`, {
        method: 'POST',
        headers: getApiHeaders(),
        body: JSON.stringify({ payment_method: 'CASH', reference_id: `EARLY-SETTLE-${Date.now()}` })
      });
      const postData = await postRes.json();
      if (!postRes.ok) {
        alert(postData.error || "Settlement failed.");
        return;
      }
      alert("Loan successfully settled early! All remaining unearned interest has been waived.");
      closeModal('modalBorrowerModule');
      loadDashboardMetrics();
    }
  } catch (err) {
    alert("Error executing early settlement.");
  }
}

async function archiveCurrentBorrower() {
  if (!currentModuleBorrower || !currentModuleBorrower.borrower) return;
  const borId = currentModuleBorrower.borrower.id;
  const name = currentModuleBorrower.borrower.full_name;

  if (confirm(`Archive borrower "${name}"? Financial records will remain preserved in audit ledger.`)) {
    try {
      const res = await fetch(`/api/v1/financier/borrowers/${borId}/archive`, {
        method: 'POST',
        headers: getApiHeaders()
      });
      if (!res.ok) {
        const d = await res.json();
        alert(d.error || "Failed to archive borrower.");
        return;
      }
      alert(`Borrower "${name}" archived successfully.`);
      closeModal('modalBorrowerModule');
      loadDashboardMetrics();
    } catch (err) {
      alert("Error archiving borrower.");
    }
  }
}

// ----------------- LOAN ORIGINATION & CALCULATOR ----------------- //

async function initLoanStudio() {
  const sel = document.getElementById('selLoanBorrower');
  sel.innerHTML = '<option value="">Loading borrowers...</option>';

  try {
    const res = await fetch('/api/v1/financier/borrowers', { headers: getApiHeaders() });
    const borrowers = await res.json();

    if (!borrowers.length) {
      sel.innerHTML = '<option value="">No borrowers registered yet. Add borrower first.</option>';
      return;
    }

    sel.innerHTML = borrowers.map(b => `<option value="${b.id}">${escapeHtml(b.full_name)} (${b.phone})</option>`).join('');
    previewSchedule();
  } catch (err) {
    sel.innerHTML = '<option value="">Failed to load borrowers.</option>';
  }
}

async function previewSchedule() {
  const principal = parseFloat(document.getElementById('numPrincipal').value) || 0;
  const rate = parseFloat(document.getElementById('numRate').value) || 0;
  const interest_type = document.getElementById('selInterestType').value;
  const frequency = document.getElementById('selFrequency').value;
  const tenure_periods = parseInt(document.getElementById('numTenure').value) || 12;
  const start_date = document.getElementById('dtStartDate').value || new Date().toISOString().split('T')[0];

  if (!principal || !rate || !tenure_periods) return;

  try {
    const res = await fetch('/api/v1/financier/loans/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ principal_amount: principal, interest_rate_annual: rate, interest_type, frequency, tenure_periods, start_date })
    });
    const sched = await res.json();
    if (!res.ok) return;

    document.getElementById('lblCalcInterest').textContent = `₹${sched.total_interest.toLocaleString('en-IN')}`;
    document.getElementById('lblCalcPayable').textContent = `₹${sched.total_payable.toLocaleString('en-IN')}`;
    document.getElementById('lblCalcEmi').textContent = `₹${sched.installment_amount.toLocaleString('en-IN')}`;

    const tbody = document.getElementById('tblPreviewBody');
    tbody.innerHTML = sched.installments.map(i => `
      <tr>
        <td>#${i.installment_number}</td>
        <td>${i.due_date}</td>
        <td>₹${i.principal_due.toLocaleString('en-IN')}</td>
        <td>₹${i.interest_due.toLocaleString('en-IN')}</td>
        <td><strong>₹${i.total_due.toLocaleString('en-IN')}</strong></td>
      </tr>
    `).join('');
  } catch (err) {
    console.error("Preview failed:", err);
  }
}

async function handleDisburseLoan(e) {
  e.preventDefault();
  const borrower_id = document.getElementById('selLoanBorrower').value;
  const principal_amount = parseFloat(document.getElementById('numPrincipal').value);
  const interest_rate_annual = parseFloat(document.getElementById('numRate').value);
  const interest_type = document.getElementById('selInterestType').value;
  const frequency = document.getElementById('selFrequency').value;
  const tenure_periods = parseInt(document.getElementById('numTenure').value);
  const start_date = document.getElementById('dtStartDate').value;

  if (!borrower_id) {
    alert("Please select a borrower.");
    return;
  }

  try {
    const res = await fetch('/api/v1/financier/loans', {
      method: 'POST',
      headers: getApiHeaders(),
      body: JSON.stringify({ borrower_id, principal_amount, interest_rate_annual, interest_type, frequency, tenure_periods, start_date })
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "Loan disbursal failed.");
      return;
    }

    alert("Loan disbursed and posted to financial ledger successfully!");
    showTab('dashboard');
  } catch (err) {
    alert("Network error during loan disbursal.");
  }
}

// ----------------- CASH DESK & REVERSALS ----------------- //

async function initCashDesk() {
  const sel = document.getElementById('selCashLoan');
  sel.innerHTML = '<option value="">Loading active loans...</option>';

  try {
    const res = await fetch('/api/v1/financier/loans', { headers: getApiHeaders() });
    const loans = await res.json();

    if (!loans.length) {
      sel.innerHTML = '<option value="">No active loans found.</option>';
      return;
    }

    sel.innerHTML = loans.map(l => `<option value="${l.id}">${escapeHtml(l.borrower_name)} — Loan #${l.id.substring(0, 10)} (Outstanding: ₹${l.outstanding_principal.toLocaleString('en-IN')})</option>`).join('');
  } catch (err) {
    sel.innerHTML = '<option value="">Failed to load loans.</option>';
  }
}

async function handleRecordCashPayment(e) {
  e.preventDefault();
  const loan_id = document.getElementById('selCashLoan').value;
  const amount = parseFloat(document.getElementById('numCashAmount').value);
  const payment_method = document.getElementById('selCashMethod').value;
  const reference_id = document.getElementById('txtCashRef').value.trim() || `OFFLINE-${Date.now()}`;
  const notes = document.getElementById('txtCashNotes').value.trim();

  if (!loan_id || !amount) {
    alert("Please select a loan and enter amount.");
    return;
  }

  try {
    const res = await fetch('/api/v1/financier/cash-payment', {
      method: 'POST',
      headers: getApiHeaders(),
      body: JSON.stringify({ loan_id, amount, payment_method, reference_id, notes })
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "Payment recording failed.");
      return;
    }

    alert("Offline payment recorded & posted to ledger!");
    document.getElementById('numCashAmount').value = '';
    document.getElementById('txtCashRef').value = '';
    document.getElementById('txtCashNotes').value = '';
    showTab('dashboard');
  } catch (err) {
    alert("Error recording payment.");
  }
}

async function handleReverseTransaction(e) {
  e.preventDefault();
  const ledger_entry_id = document.getElementById('txtRevLedgerId').value.trim();
  const reason = document.getElementById('txtRevReason').value.trim();

  if (!ledger_entry_id || !reason) {
    alert("Ledger Entry ID and Reason are required.");
    return;
  }

  try {
    const res = await fetch('/api/v1/financier/reverse-payment', {
      method: 'POST',
      headers: getApiHeaders(),
      body: JSON.stringify({ ledger_entry_id, reason })
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "Reversal failed.");
      return;
    }

    alert("Transaction reversed successfully! Counter-entry posted to ledger.");
    document.getElementById('txtRevLedgerId').value = '';
    document.getElementById('txtRevReason').value = '';
    showTab('dashboard');
  } catch (err) {
    alert("Error executing reversal.");
  }
}

// ----------------- PROFILE & AUDIT LOGS ----------------- //

async function openProfileModal() {
  try {
    const res = await fetch('/api/v1/auth/profile', { headers: getApiHeaders() });
    if (!res.ok) return;
    const p = await res.json();

    document.getElementById('profFullName').value = p.full_name || '';
    document.getElementById('profPhone').value = p.phone || '';
    document.getElementById('profEmail').value = p.email || '';
    document.getElementById('profOrgName').value = p.org_name || '';
    document.getElementById('profOrgAddress').value = p.org_address || '';

    openModal('modalProfile');
  } catch (err) {
    alert("Failed to load profile.");
  }
}

async function handleUpdateProfile(e) {
  e.preventDefault();
  const full_name = document.getElementById('profFullName').value.trim();
  const phone = document.getElementById('profPhone').value.trim();
  const email = document.getElementById('profEmail').value.trim();
  const org_name = document.getElementById('profOrgName').value.trim();
  const org_address = document.getElementById('profOrgAddress').value.trim();

  try {
    const res = await fetch('/api/v1/auth/profile', {
      method: 'PUT',
      headers: getApiHeaders(),
      body: JSON.stringify({ full_name, phone, email, org_name, org_address })
    });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "Failed to update profile.");
      return;
    }

    currentUser.full_name = full_name;
    currentUser.org_name = org_name;
    localStorage.setItem('finoffice_user', JSON.stringify(currentUser));
    document.getElementById('lblUserGreeting').textContent = `Welcome, ${full_name}`;
    document.getElementById('lblOrgBadge').textContent = org_name;

    closeModal('modalProfile');
    alert("Profile updated successfully!");
  } catch (err) {
    alert("Error updating profile.");
  }
}

async function loadAuditLogs() {
  const tbody = document.getElementById('tblAuditBody');
  tbody.innerHTML = '<tr><td colspan="6">Loading audit logs...</td></tr>';

  try {
    const res = await fetch('/api/v1/financier/audit-logs', { headers: getApiHeaders() });
    const logs = await res.json();

    if (!logs.length) {
      tbody.innerHTML = '<tr><td colspan="6">No audit records found.</td></tr>';
      return;
    }

    tbody.innerHTML = logs.map(l => `
      <tr>
        <td>${l.created_at}</td>
        <td>${l.user_id || 'System'}</td>
        <td><strong style="color: var(--accent-blue);">${l.action}</strong></td>
        <td>${l.entity_type}</td>
        <td><code>${l.entity_id}</code></td>
        <td>${escapeHtml(l.new_state || l.notes || '--')}</td>
      </tr>
    `).join('');
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="6">Failed to load audit logs.</td></tr>';
  }
}

// ----------------- RECEIPTS & STATEMENTS ----------------- //

async function viewReceipt(receiptId) {
  try {
    const res = await fetch(`/api/v1/borrower/receipt/${receiptId}`);
    if (!res.ok) {
      alert("Receipt not found.");
      return;
    }
    const r = await res.json();

    const area = document.getElementById('receiptPrintArea');
    area.innerHTML = `
      <div style="text-align: center; border-bottom: 2px solid var(--border-color); padding-bottom: 16px; margin-bottom: 16px;">
        <h2 style="margin: 0; color: var(--accent-primary);">${escapeHtml(r.financier_name)}</h2>
        <p style="margin: 4px 0; color: var(--text-muted); font-size: 0.85rem;">${escapeHtml(r.financier_address || 'Registered Finance Office')}</p>
        <h3 style="margin-top: 12px; letter-spacing: 1px;">OFFICIAL PAYMENT RECEIPT</h3>
        <span class="badge badge-success">${r.receipt_number}</span>
      </div>
      <div class="summary-grid" style="margin-bottom: 16px;">
        <div><span>Date & Time:</span> <strong>${r.date}</strong></div>
        <div><span>Borrower Name:</span> <strong>${escapeHtml(r.borrower_name)}</strong></div>
        <div><span>Mobile Number:</span> <strong>${escapeHtml(r.borrower_phone)}</strong></div>
        <div><span>Loan Reference:</span> <strong>#${r.loan_id.substring(0, 10)}</strong></div>
        <div><span>Payment Method:</span> <strong>${r.payment_method}</strong></div>
        <div><span>Txn Reference:</span> <code>${r.reference_id || 'OFFLINE'}</code></div>
      </div>
      <div style="background: var(--bg-tertiary); padding: 16px; border-radius: 8px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; font-size: 1.1rem; font-weight: 700;">
          <span>TOTAL AMOUNT PAID:</span>
          <span style="color: var(--accent-success);">₹${r.amount_paid.toLocaleString('en-IN')}</span>
        </div>
        <hr style="margin: 10px 0; border: none; border-top: 1px dashed var(--border-color);">
        <div style="font-size: 0.85rem; color: var(--text-muted);">
          <div>Principal Component: ₹${r.principal_component.toLocaleString('en-IN')}</div>
          <div>Interest Component: ₹${r.interest_component.toLocaleString('en-IN')}</div>
        </div>
      </div>
      <div style="text-align: center; font-size: 0.75rem; color: var(--text-muted);">
        Cryptographic Hash: <code>${r.verification_hash}</code><br>
        This is a computer-generated authoritative receipt.
      </div>
    `;
    openModal('modalReceipt');
  } catch (err) {
    alert("Error loading digital receipt.");
  }
}

async function downloadStatementForCurrent() {
  if (!currentModuleBorrower || !currentModuleBorrower.loan) return;
  const loanId = currentModuleBorrower.loan.loan_id;

  try {
    const res = await fetch(`/api/v1/borrower/statement?loan_id=${loanId}`, { headers: getApiHeaders() });
    if (!res.ok) {
      alert("Failed to load loan statement.");
      return;
    }
    const stmt = await res.json();
    const area = document.getElementById('statementPrintArea');

    area.innerHTML = `
      <div style="text-align: center; border-bottom: 2px solid var(--border-color); padding-bottom: 16px; margin-bottom: 20px;">
        <h2>LOAN STATEMENT OF ACCOUNT</h2>
        <p style="color: var(--text-muted);">Statement Date: ${new Date().toISOString().split('T')[0]}</p>
      </div>

      <div class="summary-grid" style="margin-bottom: 20px;">
        <div><span>Borrower Name:</span> <strong>${escapeHtml(stmt.borrower.full_name)}</strong></div>
        <div><span>Borrower Phone:</span> <strong>${escapeHtml(stmt.borrower.phone)}</strong></div>
        <div><span>Loan Reference:</span> <strong>#${stmt.loan.id.substring(0, 10)}</strong></div>
        <div><span>Original Loan:</span> <strong>₹${stmt.loan.principal_amount.toLocaleString('en-IN')}</strong></div>
        <div><span>Interest Terms:</span> <strong>${stmt.loan.interest_rate_annual}% (${stmt.loan.interest_type})</strong></div>
        <div><span>Current Status:</span> <strong>${stmt.loan.status}</strong></div>
      </div>

      <h3>Financial Balances</h3>
      <div class="kpi-grid" style="margin-bottom: 20px;">
        <div class="kpi-card accent-blue">
          <div class="kpi-title">Total Payable</div>
          <div class="kpi-value">₹${stmt.loan.total_payable.toLocaleString('en-IN')}</div>
        </div>
        <div class="kpi-card accent-green">
          <div class="kpi-title">Total Paid</div>
          <div class="kpi-value">₹${stmt.summary.total_paid.toLocaleString('en-IN')}</div>
        </div>
        <div class="kpi-card accent-purple">
          <div class="kpi-title">Outstanding</div>
          <div class="kpi-value">₹${stmt.summary.outstanding_balance.toLocaleString('en-IN')}</div>
        </div>
      </div>

      <h3>Ledger Transactions History</h3>
      <table class="data-table" style="margin-bottom: 20px;">
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Amount</th>
            <th>Principal</th>
            <th>Interest</th>
            <th>Ref #</th>
          </tr>
        </thead>
        <tbody>
          ${stmt.transactions.map(t => `
            <tr>
              <td>${t.created_at}</td>
              <td><strong>${t.entry_type}</strong></td>
              <td>₹${t.amount.toLocaleString('en-IN')}</td>
              <td>₹${t.principal_component.toLocaleString('en-IN')}</td>
              <td>₹${t.interest_component.toLocaleString('en-IN')}</td>
              <td><code>${t.reference_id || '--'}</code></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
    openModal('modalStatement');
  } catch (err) {
    alert("Error fetching statement.");
  }
}

// ----------------- BORROWER PORTAL & UPI PAYMENTS ----------------- //

async function loadBorrowerPortal() {
  const box = document.getElementById('borPortalContent');
  box.innerHTML = '<p>Loading borrower loan summary...</p>';

  try {
    const res = await fetch('/api/v1/borrower/my-loan', { headers: getApiHeaders() });
    if (!res.ok) {
      box.innerHTML = '<p style="padding: 20px; text-align: center; color: var(--text-muted);">No active loan record found for your borrower account.</p>';
      return;
    }
    const data = await res.json();

    const upiUri = `upi://pay?pa=finance@upi&pn=${encodeURIComponent(data.financier_name)}&am=${data.next_payment.amount_due}&tn=LoanPayment_${data.loan_id.substring(0,8)}`;
    const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(upiUri)}`;

    box.innerHTML = `
      <div class="summary-grid" style="margin-bottom: 24px;">
        <div><span>Financier Name:</span> <strong>${escapeHtml(data.financier_name)}</strong></div>
        <div><span>Original Loan:</span> <strong>₹${data.original_principal.toLocaleString('en-IN')}</strong></div>
        <div><span>Total Payable:</span> <strong>₹${data.total_payable.toLocaleString('en-IN')}</strong></div>
        <div><span>Total Paid:</span> <strong style="color: var(--accent-success);">₹${data.total_paid.toLocaleString('en-IN')}</strong></div>
        <div><span>Outstanding Balance:</span> <strong style="color: var(--accent-warning);">₹${data.outstanding_balance.toLocaleString('en-IN')}</strong></div>
        <div><span>Next Payment Due:</span> <strong style="color: var(--accent-danger);">₹${data.next_payment.amount_due.toLocaleString('en-IN')}</strong> <small>(${data.next_payment.due_date || 'COMPLETED'})</small></div>
      </div>

      ${data.next_payment.amount_due > 0 ? `
        <div class="card-inner" style="text-align: center; padding: 24px; background: var(--bg-tertiary); margin-bottom: 24px;">
          <h3>Pay Now via Compliant UPI</h3>
          <p style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 16px;">Scan with Google Pay, PhonePe, Paytm, or any compatible UPI app</p>
          
          <img src="${qrUrl}" alt="UPI Payment QR Code" style="border-radius: 8px; border: 4px solid #ffffff; box-shadow: var(--shadow-sm); margin-bottom: 16px;">
          
          <div>
            <button class="btn btn-primary btn-lg" onclick="simulatePortalPayment('${data.loan_id}', '${data.next_payment.schedule_id}', ${data.next_payment.amount_due})">
              💳 PAY NOW (₹${data.next_payment.amount_due.toLocaleString('en-IN')})
            </button>
          </div>
        </div>
      ` : '<div class="card-inner" style="text-align: center; color: var(--accent-success); padding: 20px;">🎉 Your loan is completely paid up!</div>'}
    `;
  } catch (err) {
    box.innerHTML = '<p>Failed to load borrower portal.</p>';
  }
}

async function simulatePortalPayment(loanId, scheduleId, amount) {
  try {
    // Step 1: Initiate attempt
    const initRes = await fetch('/api/v1/payments/initiate', {
      method: 'POST',
      headers: getApiHeaders(),
      body: JSON.stringify({ loan_id: loanId, schedule_id: scheduleId, amount: amount })
    });
    const initData = await initRes.json();
    if (!initRes.ok) {
      alert(initData.error || "Payment initiation failed.");
      return;
    }

    // Step 2: Gateway Simulation with verified server HMAC webhook
    const simRes = await fetch('/api/v1/payments/simulate-gateway-payment', {
      method: 'POST',
      headers: getApiHeaders(),
      body: JSON.stringify({
        gateway_order_id: initData.gateway_order_id,
        amount: amount,
        status: 'SUCCESS'
      })
    });
    const simData = await simRes.json();

    if (!simRes.ok) {
      alert(simData.error || "Payment verification failed.");
      return;
    }

    alert(`Payment of ₹${amount.toLocaleString('en-IN')} verified successfully! Receipt #${simData.receipt ? simData.receipt.receipt_number : ''} generated.`);
    loadBorrowerPortal();
  } catch (err) {
    alert("Error processing payment.");
  }
}

// ----------------- UTILITY FUNCTIONS ----------------- //

function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('active');
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('active');
}

function toggleTheme() {
  document.body.classList.toggle('light-theme');
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}

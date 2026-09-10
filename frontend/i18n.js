/**
 * CreditorPulse Multilingual (i18n) System
 * Supports English, Hindi (हिंदी), Tamil (தமிழ்), Telugu (తెలుగు), Kannada (ಕನ್ನಡ)
 */

const TRANSLATIONS = {
  en: {
    appTitle: "CreditorPulse — Professional Financier–Borrower Platform",
    navDashboard: "Dashboard",
    navBorrowers: "Borrowers",
    navLoanStudio: "Loan Studio",
    navCashDesk: "Cash Desk",
    navReminders: "Reminders",
    navAudit: "Audit Log",
    navReconcile: "Reconciliation",
    navBorrowerPortal: "Borrower Portal",
    navAdminPanel: "Admin Panel",

    kpiTotalOutstanding: "Total Outstanding",
    kpiTotalCollected: "Total Collected",
    kpiDueToday: "Due Today",
    kpiTotalOverdue: "Total Overdue",

    btnDisburseLoan: "🚀 Authorize Loan & Disburse",
    btnPreviewSchedule: "📐 Preview Schedule",
    btnRecordCash: "✅ Record & Post to Ledger",
    btnReverseTxn: "🔴 Authorize Transaction Reversal",
    btnSendReminder: "📨 Dispatch Compliance Reminder",
    btnPayOnline: "💳 PAY NOW ONLINE",
    btnPrintReceipt: "🖨️ Print Receipt",

    lblPrincipal: "Principal Amount (₹)",
    lblInterestRate: "Annual Interest Rate (%)",
    lblCalculationMethod: "Interest Calculation Method",
    lblFrequency: "Repayment Frequency",
    lblTenure: "Tenure (Installments)",
    lblStartDate: "Start Date"
  },
  hi: {
    appTitle: "CreditorPulse — व्यावसायिक वित्तीय प्रबंधन मंच",
    navDashboard: "डैशबोर्ड",
    navBorrowers: "ऋणदाता / उधारकर्ता",
    navLoanStudio: "ऋण निर्माण स्टूडियो",
    navCashDesk: "नकद काउंटर",
    navReminders: "भुगतान अनुस्मारक",
    navAudit: "ऑडिट लॉग",
    navReconcile: "समाधान / सुलह",
    navBorrowerPortal: "उधारकर्ता पोर्टल",
    navAdminPanel: "प्रशासनिक पैनल",

    kpiTotalOutstanding: "कुल बकाया राशि",
    kpiTotalCollected: "कुल वसूल की गई राशि",
    kpiDueToday: "आज देय भुगतान",
    kpiTotalOverdue: "कुल विलंबित राशि",

    btnDisburseLoan: "🚀 ऋण स्वीकृत करें और वितरित करें",
    btnPreviewSchedule: "📐 किश्त अनुसूची देखें",
    btnRecordCash: "✅ नकद भुगतान दर्ज करें",
    btnReverseTxn: "🔴 लेनदेन निरस्त करें",
    btnSendReminder: "📨 अनुस्मारक भेजें",
    btnPayOnline: "💳 अभी ऑनलाइन भुगतान करें",
    btnPrintReceipt: "🖨️ रसीद प्रिंट करें",

    lblPrincipal: "मूलधन राशि (₹)",
    lblInterestRate: "वार्षिक ब्याज दर (%)",
    lblCalculationMethod: "ब्याज गणना विधि",
    lblFrequency: "भुगतान आवृत्ति",
    lblTenure: "किश्तों की संख्या",
    lblStartDate: "शुरुआती तारीख"
  },
  ta: {
    appTitle: "CreditorPulse — தொழில்முறை நிதி பயன்பாடு",
    navDashboard: "முதன்மை பலகை",
    navBorrowers: "கடன் வாங்கியவர்கள்",
    navLoanStudio: "கடன் ஸ்டுடியோ",
    navCashDesk: "ரொக்கப் பிரிவு",
    navReminders: "நினைவூட்டல்கள்",
    navAudit: "தணிக்கை பதிவு",
    navReconcile: "கணக்கு சரிபார்ப்பு",
    navBorrowerPortal: "கடன் வாங்கியவர் தளம்",
    navAdminPanel: "நிர்வாகக் குழு",

    kpiTotalOutstanding: "மொத்த நிலுவை தொகை",
    kpiTotalCollected: "மொத்தம் வசூலிக்கப்பட்டது",
    kpiDueToday: "இன்று செலுத்த வேண்டியவை",
    kpiTotalOverdue: "காலக்கெடு கடந்தவை",

    btnDisburseLoan: "🚀 கடனை அனுமதிக்கவும்",
    btnPreviewSchedule: "📐 தவணை அட்டவணை",
    btnRecordCash: "✅ ரொக்கப் பணம் பதிவு செய்",
    btnReverseTxn: "🔴 பரிவர்த்தனையை ரத்து செய்",
    btnSendReminder: "📨 நினைவூட்டல் அனுப்பு",
    btnPayOnline: "💳 ஆன்லைனில் செலுத்துங்கள்",
    btnPrintReceipt: "🖨️ ரசீது அச்சிடுக",

    lblPrincipal: "அசல் தொகை (₹)",
    lblInterestRate: "ஆண்டு வட்டி விகிதம் (%)",
    lblCalculationMethod: "வட்டி கணக்கீட்டு முறை",
    lblFrequency: "செலுத்தும் முறை",
    lblTenure: "தவணைகளின் எண்ணிக்கை",
    lblStartDate: "தொடங்கும் தேதி"
  },
  te: {
    appTitle: "CreditorPulse — ప్రొఫెషనల్ ఫైనాన్స్ మేనేజ్‌మెంట్",
    navDashboard: "డాష్‌బోర్డ్",
    navBorrowers: "రుణగ్రహీతలు",
    navLoanStudio: "రుణ నిర్మాణం",
    navCashDesk: "క్యాష్ కౌంటర్",
    navReminders: "రిమైండర్లు",
    navAudit: "ఆడిట్ లాగ్",
    navReconcile: "ఖాతా సరిచూడటం",
    navBorrowerPortal: "రుణగ్రహీత పోర్టల్",
    navAdminPanel: "అడ్మిన్ ప్యానెల్",

    kpiTotalOutstanding: "మొత్తం బకీ బకాయి",
    kpiTotalCollected: "మొత్తం వసూలైనది",
    kpiDueToday: "ఈరోజు చెల్లించాల్సినవి",
    kpiTotalOverdue: "మొత్తం గడువు మీరినవి",

    btnDisburseLoan: "🚀 రుణం మంజూరు చేయండి",
    btnPreviewSchedule: "📐 షెడ్యూల్ చూడండి",
    btnRecordCash: "✅ నగదు చెల్లింపు నమొదు",
    btnReverseTxn: "🔴 లావాదేవీ రద్దు చేయండి",
    btnSendReminder: "📨 రిమైండర్ పంపండి",
    btnPayOnline: "💳 ఆన్‌లైన్‌లో చెల్లించండి",
    btnPrintReceipt: "🖨️ రశీదు ప్రింట్ చేయండి",

    lblPrincipal: "అసలు మొత్తం (₹)",
    lblInterestRate: "వార్షిక వడ్డీ రేటు (%)",
    lblCalculationMethod: "వడ్డీ లెక్కింపు పద్ధతి",
    lblFrequency: "చెల్లింపు వ్యవధి",
    lblTenure: "వాయిదాల సంఖ్య",
    lblStartDate: "ప్రారంభ తేదీ"
  },
  kn: {
    appTitle: "CreditorPulse — ವೃತ್ತಿಪರ ಹಣಕಾಸು ನಿರ್ವಹಣೆ",
    navDashboard: "ಡ್ಯಾಶ್‌ಬೋರ್ಡ್",
    navBorrowers: "ಸಾಲಗಾರರು",
    navLoanStudio: "ಸಾಲ ಸ್ಟುಡಿಯೋ",
    navCashDesk: "ನಗದು ಕೌಂಟರ್",
    navReminders: "ಜ್ಞಾಪನೆಗಳು",
    navAudit: "ಆಡಿಟ್ ಲಾಗ್",
    navReconcile: "ಲೆಕ್ಕ ಸಮನ್ವಯ",
    navBorrowerPortal: "ಸಾಲಗಾರರ ಪೋರ್ಟಲ್",
    navAdminPanel: "ಅಡ್ಮಿನ್ ಪ್ಯಾನಲ್",

    kpiTotalOutstanding: "ಒಟ್ಟು ಬಾಕಿ ಮೊತ್ತ",
    kpiTotalCollected: "ಒಟ್ಟು ಸಂಗ್ರಹಿಸಿದ ಮೊತ್ತ",
    kpiDueToday: "ಇಂದು ಪಾವತಿಸಬೇಕಾದದ್ದು",
    kpiTotalOverdue: "ಒಟ್ಟು ಬಾಕಿ ಉಳಿದದ್ದು",

    btnDisburseLoan: "🚀 ಸಾಲ ಮಂಜೂರು ಮಾಡಿ",
    btnPreviewSchedule: "📐 ಕಂತುಗಳ ವೇಳಾಪಟ್ಟಿ",
    btnRecordCash: "✅ ನಗದು ಪಾವತಿ ದಾಖಲಿಸಿ",
    btnReverseTxn: "🔴 ವಹಿವಾಟು ರದ್ದುಗೊಳಿಸಿ",
    btnSendReminder: "📨 ಜ್ಞಾಪನೆ ಕಳುಹಿಸಿ",
    btnPayOnline: "💳 ಆನ್‌ಲೈನ್ ಪಾವತಿಸಿ",
    btnPrintReceipt: "🖨️ ರಶೀದಿ ಮುದ್ರಿಸಿ",

    lblPrincipal: "ಅಸಲು ಮೊತ್ತ (₹)",
    lblInterestRate: "ವಾರ್ಷಿಕ ಬಡ್ಡಿ ದರ (%)",
    lblCalculationMethod: "ಬಡ್ಡಿ ಲೆಕ್ಕಾಚಾರದ ವಿಧಾನ",
    lblFrequency: "ಪಾವತಿ ಆವರ್ತನ",
    lblTenure: "ಕಂತುಗಳ ಸಂಖ್ಯೆ",
    lblStartDate: "ಆರಂಭದ ದಿನಾಂಕ"
  }
};

let currentLanguage = 'en';

function setLanguage(lang) {
  if (!TRANSLATIONS[lang]) return;
  currentLanguage = lang;
  const dict = TRANSLATIONS[lang];

  // Update UI Elements with data-i18n attribute
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) {
      el.textContent = dict[key];
    }
  });

  // Store preference
  try {
    localStorage.setItem('cp_lang', lang);
  } catch (e) {}
}

document.addEventListener('DOMContentLoaded', () => {
  const savedLang = localStorage.getItem('cp_lang') || 'en';
  const langSel = document.getElementById('selLanguage');
  if (langSel) {
    langSel.value = savedLang;
  }
  setLanguage(savedLang);
});

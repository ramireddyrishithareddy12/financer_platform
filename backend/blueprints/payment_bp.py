"""
Payment Gateway Integration & Webhook Blueprint
Provides secure payment initiation, simulated gateway client authorization,
and server-to-server HMAC signature-verified webhook handler.
"""

from flask import Blueprint, request, jsonify
import hmac
import hashlib
import json
import uuid
from backend.services.payment_service import PaymentService, GATEWAY_SHARED_SECRET

payment_bp = Blueprint('payments', __name__, url_prefix='/api/v1/payments')

@payment_bp.route('/initiate', methods=['POST'])
def initiate_digital_payment():
    """Initiates a pending digital payment attempt."""
    user_id = request.headers.get('X-User-Id', 'borrower_user')
    data = request.json or {}
    loan_id = data.get('loan_id')
    schedule_id = data.get('schedule_id')
    amount = data.get('amount')

    if not loan_id or not schedule_id or not amount:
        return jsonify({"error": "Loan ID, Schedule ID, and Amount are required."}), 400

    try:
        attempt = PaymentService.initiate_payment(loan_id, schedule_id, amount, user_id)
        return jsonify(attempt), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@payment_bp.route('/simulate-gateway-payment', methods=['POST'])
def simulate_gateway_payment():
    """
    Simulates payment completion on payment gateway side.
    Generates a valid HMAC SHA-256 webhook signature and triggers server webhook logic.
    """
    data = request.json or {}
    gateway_order_id = data.get('gateway_order_id')
    amount = data.get('amount')
    status = data.get('status', 'SUCCESS')

    if not gateway_order_id:
        return jsonify({"error": "Gateway Order ID required."}), 400

    payment_id = f"pay_rzp_{uuid.uuid4().hex[:10]}"
    payload_dict = {
        "gateway_order_id": gateway_order_id,
        "gateway_payment_id": payment_id,
        "status": status,
        "amount": amount
    }
    raw_payload = json.dumps(payload_dict)

    # Compute HMAC SHA-256 signature
    signature = hmac.new(GATEWAY_SHARED_SECRET.encode('utf-8'), raw_payload.encode('utf-8'), hashlib.sha256).hexdigest()

    # Process via verified server webhook mechanism
    success, msg, receipt_data = PaymentService.process_webhook_callback(raw_payload, signature)

    if success:
        return jsonify({
            "status": "SUCCESS",
            "message": msg,
            "gateway_payment_id": payment_id,
            "receipt": receipt_data
        }), 200
    else:
        return jsonify({"status": "FAILED", "error": msg}), 400

@payment_bp.route('/webhook', methods=['POST'])
def handle_server_webhook():
    """
    Raw Server-to-Server Payment Webhook Endpoint.
    Expects X-Razorpay-Signature header containing HMAC SHA-256 signature.
    """
    signature = request.headers.get('X-Razorpay-Signature') or request.headers.get('X-Gateway-Signature')
    raw_payload = request.get_data(as_text=True)

    if not signature:
        return jsonify({"error": "Missing signature header."}), 401

    success, msg, data = PaymentService.process_webhook_callback(raw_payload, signature)

    if success:
        return jsonify({"status": "ok", "message": msg, "data": data}), 200
    else:
        return jsonify({"status": "error", "message": msg}), 400

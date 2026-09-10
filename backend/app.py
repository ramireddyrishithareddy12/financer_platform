"""
Main Flask Server Entrypoint for CreditorPulse Platform
Integrates Database initialization, Blueprint API routing, and SPA static hosting.
"""

import os
import sys
from flask import Flask, send_from_directory, jsonify, request

# Add parent project path to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.database import init_db
from backend.blueprints.auth_bp import auth_bp
from backend.blueprints.financier_bp import financier_bp
from backend.blueprints.borrower_bp import borrower_bp
from backend.blueprints.payment_bp import payment_bp
from backend.blueprints.admin_bp import admin_bp

def create_app():
    # Initialize SQLite schema and seed records
    init_db()

    frontend_dir = os.path.join(PROJECT_ROOT, "frontend")
    app = Flask(__name__, static_folder=frontend_dir, static_url_path="")

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(financier_bp)
    app.register_blueprint(borrower_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(admin_bp)

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Org-Id, X-User-Id, X-User-Role'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return response

    @app.route('/api/v1/health', methods=['GET'])
    def health_check():
        return jsonify({
            "status": "UP",
            "system": "CreditorPulse Financial Platform",
            "version": "2.4.0",
            "ledger_engine": "Double-Entry Active",
            "math_engine": "Python Decimal 4-Place Precision"
        }), 200

    # Serve SPA Frontend
    @app.route('/')
    def serve_index():
        return send_from_directory(frontend_dir, "index.html")

    @app.route('/<path:path>')
    def serve_static(path):
        if os.path.exists(os.path.join(frontend_dir, path)):
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, "index.html")

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resource not found."}), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "An unexpected server error occurred."}), 500

    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    print(f"CreditorPulse Financial Platform server running on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', '').lower() == 'true')
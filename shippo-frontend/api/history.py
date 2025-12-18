from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import traceback
from datetime import datetime
from decimal import Decimal

# Add lib to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lib'))

# Import database helpers
try:
    from db import get_labels, add_label, init_db, get_label_count
    USE_POSTGRES = True
except Exception as e:
    print(f"Postgres not available: {e}")
    USE_POSTGRES = False

# Fallback to JSON file storage if Postgres not available
STORAGE_FILE = os.path.join(os.path.dirname(__file__), '..', 'storage', 'labels.json')


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder for Decimal types"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self._add_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Get label history"""
        try:
            # Parse query params
            query = self.path.split('?')[1] if '?' in self.path else ''
            params = dict(item.split('=') for item in query.split('&') if '=' in item)

            if USE_POSTGRES:
                # Initialize DB if needed
                try:
                    init_db()
                except Exception as e:
                    print(f"DB init warning: {e}")

                # Get labels from Postgres
                from_date = params.get('from_date')
                to_date = params.get('to_date')
                limit = int(params.get('limit', 100))
                offset = int(params.get('offset', 0))

                history = get_labels(
                    limit=limit,
                    offset=offset,
                    from_date=from_date,
                    to_date=to_date
                )
                count = get_label_count(from_date=from_date, to_date=to_date)
            else:
                # Fallback to JSON file
                history = self._load_history_json()

                # Filter by date range if provided
                if 'from_date' in params:
                    from_date = params['from_date']
                    history = [h for h in history if h.get('created_at', '') >= from_date]

                if 'to_date' in params:
                    to_date = params['to_date']
                    history = [h for h in history if h.get('created_at', '') <= to_date]

                count = len(history)

            # Send response
            self.send_response(200)
            self._add_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'success': True,
                'data': history,
                'count': count,
                'storage_type': 'postgres' if USE_POSTGRES else 'json'
            }

            self.wfile.write(json.dumps(response, cls=DecimalEncoder).encode())

        except Exception as e:
            print(f"History GET error: {traceback.format_exc()}")
            self.send_response(500)
            self._add_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            error_response = {
                'success': False,
                'error': str(e)
            }
            self.wfile.write(json.dumps(error_response).encode())

    def do_POST(self):
        """Add label to history"""
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))

            # Prepare label record
            label_record = {
                'tracking_number': body.get('tracking_number'),
                'carrier': body.get('carrier'),
                'service': body.get('service'),
                'cost': body.get('cost'),
                'currency': body.get('currency', 'USD'),
                'provider': body.get('provider'),
                'created_at': body.get('created_at', datetime.now().isoformat()),
                'from_address': json.dumps(body.get('from_address')) if body.get('from_address') else None,
                'to_address': json.dumps(body.get('to_address')) if body.get('to_address') else None,
                'google_drive_link': body.get('google_drive_link'),
                'google_drive_file_id': body.get('google_drive_file_id'),
                'signature_confirmation': body.get('signature_confirmation'),
                'label_id': body.get('label_id'),
                'label_download_url': body.get('label_url_temp')
            }

            if USE_POSTGRES:
                # Initialize DB if needed
                try:
                    init_db()
                except Exception as e:
                    print(f"DB init warning: {e}")

                # Add to Postgres
                saved_record = add_label(label_record)
            else:
                # Fallback to JSON file
                history = self._load_history_json()
                history.insert(0, label_record)
                history = history[:1000]  # Keep only last 1000
                self._save_history_json(history)
                saved_record = label_record

            # Send response
            self.send_response(200)
            self._add_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'success': True,
                'data': saved_record,
                'storage_type': 'postgres' if USE_POSTGRES else 'json'
            }

            self.wfile.write(json.dumps(response, cls=DecimalEncoder).encode())

        except Exception as e:
            print(f"History POST error: {traceback.format_exc()}")
            self.send_response(500)
            self._add_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            error_response = {
                'success': False,
                'error': str(e)
            }
            self.wfile.write(json.dumps(error_response).encode())

    def _add_cors_headers(self):
        """Add CORS headers"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _load_history_json(self):
        """Load history from JSON file (fallback)"""
        try:
            if os.path.exists(STORAGE_FILE):
                with open(STORAGE_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading history: {e}")
        return []

    def _save_history_json(self, history):
        """Save history to JSON file (fallback)"""
        os.makedirs(os.path.dirname(STORAGE_FILE), exist_ok=True)
        with open(STORAGE_FILE, 'w') as f:
            json.dump(history, f, indent=2)

from http.server import BaseHTTPRequestHandler
import json
import os
import traceback
from datetime import datetime

# Simple JSON file storage for label history
STORAGE_FILE = os.path.join(os.path.dirname(__file__), '..', 'storage', 'labels.json')


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self._add_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Get label history"""
        try:
            history = self._load_history()

            # Optional filtering by query params
            query = self.path.split('?')[1] if '?' in self.path else ''
            params = dict(item.split('=') for item in query.split('&') if '=' in item)

            # Filter by date range if provided
            if 'from_date' in params:
                from_date = params['from_date']
                history = [h for h in history if h.get('created_at', '') >= from_date]

            if 'to_date' in params:
                to_date = params['to_date']
                history = [h for h in history if h.get('created_at', '') <= to_date]

            # Send response
            self.send_response(200)
            self._add_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'success': True,
                'data': history,
                'count': len(history)
            }

            self.wfile.write(json.dumps(response).encode())

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

            # Load existing history
            history = self._load_history()

            # Add new label record
            label_record = {
                'tracking_number': body.get('tracking_number'),
                'carrier': body.get('carrier'),
                'service': body.get('service'),
                'cost': body.get('cost'),
                'currency': body.get('currency', 'USD'),
                'provider': body.get('provider'),
                'created_at': body.get('created_at', datetime.now().isoformat()),
                'from_address': body.get('from_address'),
                'to_address': body.get('to_address'),
                'google_drive_link': body.get('google_drive_link'),
                'google_drive_file_id': body.get('google_drive_file_id')
            }

            # Add to beginning of list (most recent first)
            history.insert(0, label_record)

            # Keep only last 1000 records
            history = history[:1000]

            # Save history
            self._save_history(history)

            # Send response
            self.send_response(200)
            self._add_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'success': True,
                'data': label_record
            }

            self.wfile.write(json.dumps(response).encode())

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

    def _load_history(self):
        """Load history from JSON file"""
        try:
            if os.path.exists(STORAGE_FILE):
                with open(STORAGE_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading history: {e}")

        return []

    def _save_history(self, history):
        """Save history to JSON file"""
        os.makedirs(os.path.dirname(STORAGE_FILE), exist_ok=True)

        with open(STORAGE_FILE, 'w') as f:
            json.dump(history, f, indent=2)

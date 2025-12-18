from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import traceback

# Add lib to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lib'))

from shipengine_client import ShipEngineClient


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self._add_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Void a shipping label"""
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))

            label_id = body.get('label_id')
            provider = body.get('provider')
            tracking_number = body.get('tracking_number')

            if not label_id or not provider:
                raise ValueError("Missing label_id or provider")

            # Currently only ShipEngine supports voiding via our client
            if provider == 'shipengine':
                result = self._void_shipengine_label(label_id)
            else:
                raise ValueError(f"Voiding not supported for provider: {provider}. Only ShipEngine labels can be voided.")

            # Send response
            self.send_response(200)
            self._add_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response_data = {
                'success': True,
                'data': {
                    'approved': result.get('approved'),
                    'message': result.get('message'),
                    'label_id': label_id,
                    'tracking_number': tracking_number
                }
            }

            self.wfile.write(json.dumps(response_data).encode())

        except Exception as e:
            print(f"Void error: {traceback.format_exc()}")
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

    def _void_shipengine_label(self, label_id):
        """Void label from ShipEngine"""
        client = ShipEngineClient(
            api_key=os.environ['SHIPENGINE_API_KEY']
        )
        return client.void_label(label_id)

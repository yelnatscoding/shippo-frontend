from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import traceback
import requests
from datetime import datetime

# Add lib to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lib'))

from shippo_client import ShippoClient
from easypost_client import EasyPostClient
from shipengine_client import ShipEngineClient
from easyship_client import EasyshipClient
from google_drive_uploader import GoogleDriveUploader


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self._add_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Purchase shipping label"""
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))

            rate_id = body.get('rate_id')
            provider = body.get('provider')
            label_format = body.get('format', os.environ.get('DEFAULT_LABEL_FORMAT', 'PDF'))
            from_address = body.get('from_address', {})
            to_address = body.get('to_address', {})

            if not rate_id or not provider:
                raise ValueError("Missing rate_id or provider")

            # Purchase label from provider
            if provider == 'shippo':
                label = self._purchase_shippo_label(rate_id, label_format)
            elif provider == 'easypost':
                label = self._purchase_easypost_label(rate_id, label_format)
            elif provider == 'shipengine':
                label = self._purchase_shipengine_label(rate_id, label_format)
            elif provider == 'easyship':
                label = self._purchase_easyship_label(rate_id, label_format)
            else:
                raise ValueError(f"Unknown provider: {provider}")

            # Download PDF from provider's temporary URL
            pdf_response = requests.get(label.label_url, timeout=10)
            pdf_response.raise_for_status()
            pdf_content = pdf_response.content

            # Upload to Google Drive (if configured)
            drive_link = None
            drive_file_id = None
            drive_warning = None

            if os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON'):
                try:
                    uploader = GoogleDriveUploader()
                    drive_result = uploader.upload_label(
                        pdf_content=pdf_content,
                        tracking_number=label.tracking_number,
                        carrier=label.carrier,
                        to_name=to_address.get('name', 'Unknown'),
                        service_name=label.service
                    )

                    drive_link = drive_result['web_link']
                    drive_file_id = drive_result['file_id']

                except Exception as drive_error:
                    print(f"Google Drive upload failed: {traceback.format_exc()}")
                    drive_warning = f"Label purchased successfully, but Drive upload failed: {str(drive_error)}"

            # Prepare response
            response_data = {
                'success': True,
                'data': {
                    'tracking_number': label.tracking_number,
                    'carrier': label.carrier,
                    'service': label.service,
                    'cost': float(label.cost),
                    'currency': getattr(label, 'currency', 'USD'),
                    'created_at': label.created_at or datetime.now().isoformat(),
                    'google_drive_link': drive_link,
                    'google_drive_file_id': drive_file_id,
                    'label_url_temp': label.label_url,  # Temporary URL (expires soon)
                    'from_address': from_address,
                    'to_address': to_address,
                    'provider': provider
                }
            }

            if drive_warning:
                response_data['warning'] = drive_warning

            # Send response
            self.send_response(200)
            self._add_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            self.wfile.write(json.dumps(response_data).encode())

        except Exception as e:
            print(f"Purchase error: {traceback.format_exc()}")
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

    def _purchase_shippo_label(self, rate_id, label_format):
        """Purchase label from Shippo"""
        client = ShippoClient(
            api_key=os.environ['SHIPPO_API_KEY'],
            test_mode=os.environ.get('SHIPPO_TEST_MODE', 'true').lower() == 'true'
        )
        return client.purchase_label(rate_id, label_format)

    def _purchase_easypost_label(self, rate_id, label_format):
        """Purchase label from EasyPost"""
        client = EasyPostClient(
            api_key=os.environ['EASYPOST_API_KEY'],
            test_mode=os.environ.get('EASYPOST_TEST_MODE', 'true').lower() == 'true'
        )
        return client.purchase_label(rate_id, label_format)

    def _purchase_shipengine_label(self, rate_id, label_format):
        """Purchase label from ShipEngine"""
        client = ShipEngineClient(
            api_key=os.environ['SHIPENGINE_API_KEY']
        )
        return client.purchase_label(rate_id, label_format)

    def _purchase_easyship_label(self, rate_id, label_format):
        """Purchase label from Easyship"""
        client = EasyshipClient(
            api_key=os.environ['EASYSHIP_API_KEY']
        )
        return client.purchase_label(rate_id, label_format)

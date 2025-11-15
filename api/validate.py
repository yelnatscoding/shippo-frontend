from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import traceback

# Add lib to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lib'))

from models import Address
from shippo_client import ShippoClient
from easypost_client import EasyPostClient


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self._add_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Validate shipping address"""
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))

            # Get address and provider preference
            address = Address(**body.get('address'))
            provider = body.get('provider', 'auto')

            # Choose provider (default to Shippo, fallback to EasyPost)
            if provider == 'auto':
                if os.environ.get('SHIPPO_API_KEY'):
                    provider = 'shippo'
                elif os.environ.get('EASYPOST_API_KEY'):
                    provider = 'easypost'
                else:
                    raise ValueError("No validation provider configured")

            # Validate address
            if provider == 'shippo':
                result = self._validate_with_shippo(address)
            elif provider == 'easypost':
                result = self._validate_with_easypost(address)
            else:
                raise ValueError(f"Unknown provider: {provider}")

            # Send response
            self.send_response(200)
            self._add_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'success': True,
                'data': result,
                'provider': provider
            }

            self.wfile.write(json.dumps(response).encode())

        except Exception as e:
            print(f"Validation error: {traceback.format_exc()}")
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

    def _validate_with_shippo(self, address):
        """Validate with Shippo"""
        client = ShippoClient(
            api_key=os.environ['SHIPPO_API_KEY'],
            test_mode=os.environ.get('SHIPPO_TEST_MODE', 'true').lower() == 'true'
        )

        validation_result = client.validate_address(address)

        return {
            'is_valid': validation_result.is_valid,
            'messages': validation_result.messages,
            'original': self._serialize_address(validation_result.original_address),
            'suggested': self._serialize_address(validation_result.validated_address) if validation_result.validated_address else None
        }

    def _validate_with_easypost(self, address):
        """Validate with EasyPost"""
        client = EasyPostClient(
            api_key=os.environ['EASYPOST_API_KEY'],
            test_mode=os.environ.get('EASYPOST_TEST_MODE', 'true').lower() == 'true'
        )

        validation_result = client.validate_address(address)

        return {
            'is_valid': validation_result.is_valid,
            'messages': validation_result.messages,
            'original': self._serialize_address(validation_result.original_address),
            'suggested': self._serialize_address(validation_result.validated_address) if validation_result.validated_address else None
        }

    def _serialize_address(self, address):
        """Convert Address model to dict"""
        if address is None:
            return None

        if hasattr(address, 'model_dump'):
            return address.model_dump()
        elif hasattr(address, 'dict'):
            return address.dict()
        else:
            return {
                'name': address.name,
                'street1': address.street1,
                'street2': getattr(address, 'street2', None),
                'city': address.city,
                'state': address.state,
                'zip': address.zip,
                'country': address.country,
                'phone': getattr(address, 'phone', None),
                'email': getattr(address, 'email', None)
            }

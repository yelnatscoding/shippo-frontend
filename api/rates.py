from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import traceback

# Add lib to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lib'))

from models import Address, Parcel
from shippo_client import ShippoClient
from easypost_client import EasyPostClient
from shipengine_client import ShipEngineClient
from easyship_client import EasyshipClient


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self._add_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Get shipping rates from all providers"""
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))

            # Validate and create models
            from_address = Address(**body.get('from_address'))
            to_address = Address(**body.get('to_address'))
            parcel = Parcel(**body.get('parcel'))

            # Get rates from all providers in parallel
            results = {}
            errors = {}

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {}

                # Submit all provider requests
                if os.environ.get('SHIPPO_API_KEY'):
                    futures[executor.submit(
                        self._get_shippo_rates,
                        from_address,
                        to_address,
                        parcel
                    )] = 'shippo'

                if os.environ.get('EASYPOST_API_KEY'):
                    futures[executor.submit(
                        self._get_easypost_rates,
                        from_address,
                        to_address,
                        parcel
                    )] = 'easypost'

                if os.environ.get('SHIPENGINE_API_KEY'):
                    futures[executor.submit(
                        self._get_shipengine_rates,
                        from_address,
                        to_address,
                        parcel
                    )] = 'shipengine'

                if os.environ.get('EASYSHIP_API_KEY'):
                    futures[executor.submit(
                        self._get_easyship_rates,
                        from_address,
                        to_address,
                        parcel
                    )] = 'easyship'

                # Collect results
                for future in as_completed(futures, timeout=9):
                    provider = futures[future]
                    try:
                        rates = future.result(timeout=8)
                        results[provider] = rates
                    except TimeoutError:
                        errors[provider] = 'Request timed out'
                    except Exception as e:
                        errors[provider] = str(e)
                        print(f"Error from {provider}: {traceback.format_exc()}")

            # Send response
            self.send_response(200)
            self._add_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            response = {
                'success': True,
                'data': results,
                'errors': errors if errors else {}
            }

            self.wfile.write(json.dumps(response).encode())

        except Exception as e:
            print(f"Handler error: {traceback.format_exc()}")
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

    def _get_shippo_rates(self, from_address, to_address, parcel):
        """Get rates from Shippo"""
        client = ShippoClient(
            api_key=os.environ['SHIPPO_API_KEY'],
            test_mode=os.environ.get('SHIPPO_TEST_MODE', 'true').lower() == 'true'
        )
        rates = client.get_rates(from_address, to_address, parcel)
        return [self._serialize_rate(r) for r in rates]

    def _get_easypost_rates(self, from_address, to_address, parcel):
        """Get rates from EasyPost"""
        client = EasyPostClient(
            api_key=os.environ['EASYPOST_API_KEY'],
            test_mode=os.environ.get('EASYPOST_TEST_MODE', 'true').lower() == 'true'
        )
        rates = client.get_rates(from_address, to_address, parcel)
        return [self._serialize_rate(r) for r in rates]

    def _get_shipengine_rates(self, from_address, to_address, parcel):
        """Get rates from ShipEngine"""
        client = ShipEngineClient(
            api_key=os.environ['SHIPENGINE_API_KEY']
        )
        rates = client.get_rates(from_address, to_address, parcel)
        return [self._serialize_rate(r) for r in rates]

    def _get_easyship_rates(self, from_address, to_address, parcel):
        """Get rates from Easyship"""
        client = EasyshipClient(
            api_key=os.environ['EASYSHIP_API_KEY']
        )
        rates = client.get_rates(from_address, to_address, parcel)
        return [self._serialize_rate(r) for r in rates]

    def _serialize_rate(self, rate):
        """Convert Rate model to dict"""
        if hasattr(rate, 'model_dump'):
            return rate.model_dump()
        elif hasattr(rate, 'dict'):
            return rate.dict()
        else:
            return {
                'object_id': rate.object_id,
                'provider': rate.provider,
                'carrier': getattr(rate, 'carrier', rate.provider),
                'servicelevel_name': rate.servicelevel_name,
                'servicelevel_token': getattr(rate, 'servicelevel_token', None),
                'amount': float(rate.amount),
                'currency': rate.currency,
                'estimated_days': rate.estimated_days,
                'duration_terms': getattr(rate, 'duration_terms', None),
                'shipment_id': getattr(rate, 'shipment_id', None)
            }

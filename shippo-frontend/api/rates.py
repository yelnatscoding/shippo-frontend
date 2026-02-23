from http.server import BaseHTTPRequestHandler
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import traceback

# Add lib to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lib'))


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self._add_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Get shipping rates from all providers (base + signature)"""
        try:
            # Add lib directory to path for imports
            lib_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib')
            if lib_path not in sys.path:
                sys.path.insert(0, lib_path)

            # Lazy imports to avoid build-time import errors
            from models import Address, Parcel
            from shippo_client import ShippoClient
            from easypost_client import EasyPostClient
            from shipengine_client import ShipEngineClient
            from easyship_client import EasyshipClient
            from gori_client import GoriClient

            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))

            # Validate and create models
            from_address = Address(**body.get('from_address'))
            to_address = Address(**body.get('to_address'))
            parcel = Parcel(**body.get('parcel'))

            # Get rates from all providers in parallel (both base and signature)
            results = {}
            errors = {}

            # We'll submit 2 tasks per provider: base rates and signature rates
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {}

                # Submit all provider requests (base + signature for each)
                if os.environ.get('SHIPPO_API_KEY'):
                    futures[executor.submit(
                        self._get_shippo_rates,
                        from_address, to_address, parcel, None
                    )] = ('shippo', 'base')
                    futures[executor.submit(
                        self._get_shippo_rates,
                        from_address, to_address, parcel, 'STANDARD'
                    )] = ('shippo', 'signature')

                if os.environ.get('EASYPOST_API_KEY'):
                    futures[executor.submit(
                        self._get_easypost_rates,
                        from_address, to_address, parcel, None
                    )] = ('easypost', 'base')
                    futures[executor.submit(
                        self._get_easypost_rates,
                        from_address, to_address, parcel, 'STANDARD'
                    )] = ('easypost', 'signature')

                if os.environ.get('SHIPENGINE_API_KEY'):
                    futures[executor.submit(
                        self._get_shipengine_rates,
                        from_address, to_address, parcel, None
                    )] = ('shipengine', 'base')
                    futures[executor.submit(
                        self._get_shipengine_rates,
                        from_address, to_address, parcel, 'STANDARD'
                    )] = ('shipengine', 'signature')

                if os.environ.get('EASYSHIP_API_KEY'):
                    futures[executor.submit(
                        self._get_easyship_rates,
                        from_address, to_address, parcel, None
                    )] = ('easyship', 'base')
                    futures[executor.submit(
                        self._get_easyship_rates,
                        from_address, to_address, parcel, 'STANDARD'
                    )] = ('easyship', 'signature')

                if os.environ.get('GORI_CLIENT_ID'):
                    futures[executor.submit(
                        self._get_gori_rates,
                        from_address, to_address, parcel, None
                    )] = ('gori', 'base')
                    futures[executor.submit(
                        self._get_gori_rates,
                        from_address, to_address, parcel, 'STANDARD'
                    )] = ('gori', 'signature')

                # Collect results
                for future in as_completed(futures, timeout=15):
                    provider, rate_type = futures[future]
                    try:
                        rates = future.result(timeout=12)
                        if provider not in results:
                            results[provider] = {'base': [], 'signature': []}
                        results[provider][rate_type] = rates
                    except TimeoutError:
                        if provider not in errors:
                            errors[provider] = {}
                        errors[provider][rate_type] = 'Request timed out'
                    except Exception as e:
                        if provider not in errors:
                            errors[provider] = {}
                        errors[provider][rate_type] = str(e)
                        print(f"Error from {provider} ({rate_type}): {traceback.format_exc()}")

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
            error_traceback = traceback.format_exc()
            print(f"Handler error: {error_traceback}")
            self.send_response(500)
            self._add_cors_headers()
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            error_response = {
                'success': False,
                'error': str(e),
                'traceback': error_traceback,
                'type': type(e).__name__
            }
            self.wfile.write(json.dumps(error_response).encode())

    def _add_cors_headers(self):
        """Add CORS headers"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _get_shippo_rates(self, from_address, to_address, parcel, signature_confirmation):
        """Get rates from Shippo"""
        lib_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from shippo_client import ShippoClient
        client = ShippoClient(
            api_key=os.environ['SHIPPO_API_KEY'],
            test_mode=os.environ.get('SHIPPO_TEST_MODE', 'true').lower() == 'true'
        )
        rates = client.get_rates(from_address, to_address, parcel,
                                  signature_confirmation=signature_confirmation)
        return [self._serialize_rate(r) for r in rates]

    def _get_easypost_rates(self, from_address, to_address, parcel, signature_confirmation):
        """Get rates from EasyPost"""
        lib_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from easypost_client import EasyPostClient
        client = EasyPostClient(
            api_key=os.environ['EASYPOST_API_KEY'],
            test_mode=os.environ.get('EASYPOST_TEST_MODE', 'true').lower() == 'true'
        )
        rates = client.get_rates(from_address, to_address, parcel,
                                  signature_confirmation=signature_confirmation)
        return [self._serialize_rate(r) for r in rates]

    def _get_shipengine_rates(self, from_address, to_address, parcel, signature_confirmation):
        """Get rates from ShipEngine"""
        lib_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from shipengine_client import ShipEngineClient
        client = ShipEngineClient(
            api_key=os.environ['SHIPENGINE_API_KEY']
        )
        rates = client.get_rates(from_address, to_address, parcel,
                                  signature_confirmation=signature_confirmation)
        return [self._serialize_rate(r) for r in rates]

    def _get_easyship_rates(self, from_address, to_address, parcel, signature_confirmation):
        """Get rates from Easyship"""
        lib_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from easyship_client import EasyshipClient
        client = EasyshipClient(
            api_key=os.environ['EASYSHIP_API_KEY']
        )
        rates = client.get_rates(from_address, to_address, parcel,
                                  signature_confirmation=signature_confirmation)
        return [self._serialize_rate(r) for r in rates]

    def _get_gori_rates(self, from_address, to_address, parcel, signature_confirmation):
        """Get rates from Gori (ShipBae)"""
        lib_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from gori_client import GoriClient
        client = GoriClient(
            client_id=os.environ['GORI_CLIENT_ID'],
            client_secret=os.environ['GORI_CLIENT_SECRET'],
            test_mode=os.environ.get('GORI_TEST_MODE', 'false').lower() == 'true'
        )
        rates = client.get_rates(from_address, to_address, parcel,
                                  signature_confirmation=signature_confirmation)
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
                'shipment_id': getattr(rate, 'shipment_id', None),
                'signature_confirmation': getattr(rate, 'signature_confirmation', None)
            }

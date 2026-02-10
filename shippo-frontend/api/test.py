from http.server import BaseHTTPRequestHandler
import json
import os
import sys


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        checks = {}

        # Check POSTGRES_URL
        checks['postgres_url_set'] = bool(os.environ.get('POSTGRES_URL'))

        # Check psycopg2
        try:
            import psycopg2
            checks['psycopg2'] = 'installed'
        except ImportError as e:
            checks['psycopg2'] = f'missing: {e}'

        # Check db import
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'lib'))
        try:
            from db import add_label, get_labels
            checks['db_import'] = 'ok'
        except Exception as e:
            checks['db_import'] = f'failed: {e}'

        # Check DB connection
        try:
            from db import init_db
            init_db()
            checks['db_connection'] = 'ok'
        except Exception as e:
            checks['db_connection'] = f'failed: {e}'

        response = {
            'success': True,
            'checks': checks
        }
        self.wfile.write(json.dumps(response).encode())

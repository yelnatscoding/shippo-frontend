from http.server import BaseHTTPRequestHandler
import json
import os
import re
import requests


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self._add_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Parse natural language shipping request via Gemini AI"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))
            message = body.get('message', '').strip()

            if not message:
                self._send_error(400, 'Message is required')
                return

            api_key = os.environ.get('GEMINI_API_KEY', '').strip()
            if not api_key:
                self._send_error(500, 'GEMINI_API_KEY not configured')
                return

            # Call Gemini API
            parsed = self._call_gemini(api_key, message)

            if not parsed:
                self._send_error(422, 'Could not parse shipping details from your message. Try: "Ship from [address] to [address], [dimensions] [weight]"')
                return

            # Validate required fields
            validation_errors = self._validate_parsed(parsed)
            if validation_errors:
                self._send_error(422, f'Missing fields: {", ".join(validation_errors)}. Please include both addresses and package dimensions.')
                return

            self._send_json(200, {
                'success': True,
                'data': parsed
            })

        except json.JSONDecodeError:
            self._send_error(400, 'Invalid JSON in request body')
        except requests.exceptions.Timeout:
            self._send_error(504, 'Gemini API timed out. Please try again.')
        except Exception as e:
            print(f"Chat handler error: {e}")
            self._send_error(500, str(e))

    def _call_gemini(self, api_key, message):
        """Call Gemini REST API to parse shipping text"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

        prompt = f"""You are a shipping assistant. Parse the following natural language shipping request into structured JSON.

RULES:
- Extract from_address, to_address, and parcel dimensions
- Convert ALL dimensions to inches (1 cm = 0.3937 inches, round to 1 decimal)
- Convert ALL weights to pounds (1 kg = 2.2046 lbs, round to 1 decimal)
- US addresses only - include state abbreviation and ZIP code
- If a name is not provided for an address, use empty string
- If street address is not provided but city/state/zip are, use empty string for street1
- phone should default to empty string if not provided

Return ONLY valid JSON with this exact structure (no markdown, no code blocks):
{{
  "from_address": {{
    "name": "",
    "street1": "",
    "city": "",
    "state": "",
    "zip": "",
    "country": "US",
    "phone": ""
  }},
  "to_address": {{
    "name": "",
    "street1": "",
    "city": "",
    "state": "",
    "zip": "",
    "country": "US",
    "phone": ""
  }},
  "parcel": {{
    "length": 0,
    "width": 0,
    "height": 0,
    "weight": 0
  }}
}}

User request: {message}"""

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024
            }
        }

        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()

        data = response.json()

        # Extract text from Gemini response
        text = data['candidates'][0]['content']['parts'][0]['text']

        # Strip markdown code blocks if present
        text = re.sub(r'^```(?:json)?\s*', '', text.strip())
        text = re.sub(r'\s*```$', '', text.strip())

        return json.loads(text)

    def _validate_parsed(self, parsed):
        """Validate parsed data has required fields"""
        errors = []

        to_addr = parsed.get('to_address', {})
        if not to_addr.get('city') and not to_addr.get('zip'):
            errors.append('to_address (need at least city or zip)')

        from_addr = parsed.get('from_address', {})
        if not from_addr.get('city') and not from_addr.get('zip'):
            errors.append('from_address (need at least city or zip)')

        parcel = parsed.get('parcel', {})
        if not parcel.get('weight'):
            errors.append('weight')
        if not parcel.get('length') or not parcel.get('width') or not parcel.get('height'):
            errors.append('dimensions (length, width, height)')

        return errors

    def _send_json(self, status, data):
        """Send JSON response"""
        self.send_response(status)
        self._add_cors_headers()
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_error(self, status, message):
        """Send error response"""
        self._send_json(status, {
            'success': False,
            'error': message
        })

    def _add_cors_headers(self):
        """Add CORS headers"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

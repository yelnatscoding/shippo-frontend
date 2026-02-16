"""Gemini AI client for natural language processing"""

import os
from google import genai
from google.genai import types
from typing import Optional, Dict, Any, List
import json
import logging

logger = logging.getLogger(__name__)


class GeminiClient:
    """Wrapper for Google Gemini API"""

    MODEL = "gemini-2.0-flash"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not configured")

        self.client = genai.Client(api_key=self.api_key)
        logger.info("Gemini client initialized")

    # --- Shipping tool declarations for function calling ---
    SHIPPING_TOOLS = [
        {
            "name": "set_to_address",
            "description": (
                "Set or update the DESTINATION (recipient) address. "
                "Call this when the user provides recipient/destination info. "
                "All addresses are destination unless user explicitly says 'from' or 'ship from'."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING", "description": "Recipient full name"},
                    "street": {"type": "STRING", "description": "Street address (no apt/suite/unit)"},
                    "street2": {"type": "STRING", "description": "Apt, suite, unit, floor (e.g. 'Apt 4B')"},
                    "city": {"type": "STRING", "description": "City name"},
                    "state": {"type": "STRING", "description": "2-letter state code (e.g. CA, TX)"},
                    "zip": {"type": "STRING", "description": "5-digit ZIP code"},
                    "phone": {"type": "STRING", "description": "10-digit phone (digits only, no formatting)"},
                    "email": {"type": "STRING", "description": "Email address"},
                },
            },
        },
        {
            "name": "set_from_address",
            "description": (
                "Set or update the ORIGIN (sender) address. "
                "ONLY call this when the user EXPLICITLY says 'from', 'ship from', or 'sending from'. "
                "The default origin is already pre-filled — do NOT call this unless user provides a different origin."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING", "description": "Sender full name"},
                    "street": {"type": "STRING", "description": "Origin street address"},
                    "city": {"type": "STRING", "description": "Origin city"},
                    "state": {"type": "STRING", "description": "2-letter state code"},
                    "zip": {"type": "STRING", "description": "5-digit ZIP code"},
                    "phone": {"type": "STRING", "description": "10-digit phone (digits only)"},
                },
            },
        },
        {
            "name": "set_package",
            "description": "Set or update package weight and/or dimensions.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "weight": {"type": "NUMBER", "description": "Weight in pounds (convert oz: 16oz=1lb)"},
                    "length": {"type": "NUMBER", "description": "Length in inches"},
                    "width": {"type": "NUMBER", "description": "Width in inches"},
                    "height": {"type": "NUMBER", "description": "Height in inches"},
                },
            },
        },
        {
            "name": "update_field",
            "description": (
                "Update a single specific field when the user wants to correct something. "
                "Use this for corrections like 'change the zip to 78702' or 'the name is actually Jane'."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "field": {
                        "type": "STRING",
                        "description": "Field to update: to_name, to_street, to_street2, to_city, to_state, to_zip, to_phone, to_email, from_name, from_street, from_city, from_state, from_zip, from_phone, weight, length, width, height",
                    },
                    "value": {"type": "STRING", "description": "New value for the field"},
                },
                "required": ["field", "value"],
            },
        },
        {
            "name": "ask_clarification",
            "description": (
                "Ask the user a clarifying question when their input is genuinely ambiguous. "
                "Only use when you truly cannot determine intent from context."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "question": {"type": "STRING", "description": "The question to ask the user"},
                },
                "required": ["question"],
            },
        },
    ]

    def _build_shipping_system_context(self, default_origin: Dict[str, str]) -> str:
        """Build system context for shipping conversation."""
        origin_parts = [
            default_origin.get("name", "Sender"),
            default_origin.get("street1", ""),
            f"{default_origin.get('city', '')}, {default_origin.get('state', '')} {default_origin.get('zip', '')}",
            default_origin.get("phone", ""),
        ]
        origin_text = ", ".join(p for p in origin_parts if p)

        return (
            "You are a shipping assistant helping create shipping labels.\n\n"
            f"Default origin (from) address:\n  {origin_text}\n\n"
            "Rules:\n"
            "- The user is providing DESTINATION (to) address info unless they explicitly say 'from' or 'ship from'\n"
            "- Use set_to_address for destination info, set_from_address ONLY when user explicitly provides origin\n"
            "- Use set_package for weight and dimensions\n"
            "- Use update_field when user wants to correct a specific previously-set field\n"
            "- Use ask_clarification when input is genuinely ambiguous\n"
            "- You can call multiple tools in one response (e.g. set_to_address AND set_package)\n"
            "- Phone numbers: 10 digits only, strip all formatting\n"
            "- State: always 2-letter abbreviation (e.g. CA, TX, NY)\n"
            "- ZIP: always 5 digits\n"
            "- Weight: convert ounces to pounds if needed (16oz = 1lb)\n"
            "- Separate apt/suite/unit into street2 field\n"
            "- If user says '12x8x4' that means length=12, width=8, height=4"
        )

    async def process_shipping_message(
        self,
        message: str,
        history: List[types.Content],
    ) -> Dict[str, Any]:
        """
        Process a shipping message using function calling.
        Returns dict with 'function_calls' list and 'model_response' Content for history.
        """
        # Build the tools config
        tool = types.Tool(function_declarations=[
            types.FunctionDeclaration(**decl) for decl in self.SHIPPING_TOOLS
        ])
        config = types.GenerateContentConfig(
            tools=[tool],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        # Append user message to history
        contents = list(history) + [
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        ]

        try:
            response = await self.client.aio.models.generate_content(
                model=self.MODEL,
                contents=contents,
                config=config,
            )
        except Exception as e:
            logger.error(f"Gemini function calling error: {e}")
            return {"function_calls": [], "model_response": None, "error": str(e)}

        # Extract function calls and text from response
        function_calls = []
        text_parts = []

        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    fc = part.function_call
                    function_calls.append({
                        "name": fc.name,
                        "args": dict(fc.args) if fc.args else {},
                    })
                elif part.text:
                    text_parts.append(part.text)

        return {
            "function_calls": function_calls,
            "text": " ".join(text_parts) if text_parts else None,
            "model_response": response.candidates[0].content if response.candidates else None,
        }

    def build_function_responses(self, function_calls: List[Dict]) -> types.Content:
        """Build a Content with function responses to append to history."""
        parts = []
        for fc in function_calls:
            parts.append(types.Part.from_function_response(
                name=fc["name"],
                response={"status": "ok"},
            ))
        return types.Content(role="user", parts=parts)

    async def parse_shipping_request(self, message: str) -> Dict[str, Any]:
        """
        Parse natural language shipping request.
        Returns extracted dimensions, weight, and addresses.
        """
        prompt = f"""Extract shipping information from this message. Return JSON only, no markdown.

Message: "{message}"

Return this exact JSON structure (use null for missing values):
{{
    "origin_zip": "string or null",
    "destination_zip": "string or null",
    "destination_city": "string or null",
    "destination_state": "string or null",
    "weight": number or null (in pounds),
    "length": number or null (in inches),
    "width": number or null (in inches),
    "height": number or null (in inches),
    "missing_fields": ["list of required fields that are missing"]
}}

Required fields: destination (zip OR city+state), weight.
If dimensions missing, set length/width/height to null.
Return ONLY the JSON object, no other text."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.MODEL,
                contents=prompt,
            )
            text = response.text.strip()

            # Extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            text = text.strip()
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Gemini: {e}, response: {text}")
            return {"error": "Failed to parse response", "missing_fields": ["all"]}
        except Exception as e:
            logger.error(f"Failed to parse shipping request: {e}")
            # Fallback to regex parsing
            return self._fallback_parse_shipping(message)

    def _fallback_parse_shipping(self, message: str) -> Dict[str, Any]:
        """Fallback regex-based shipping parser when AI is unavailable."""
        import re

        result = {
            "origin_zip": None,
            "destination_zip": None,
            "destination_city": None,
            "destination_state": None,
            "weight": None,
            "length": None,
            "width": None,
            "height": None,
            "missing_fields": []
        }

        message_lower = message.lower()

        # Extract ZIP codes (5 digits)
        zips = re.findall(r'\b(\d{5})\b', message)
        if len(zips) >= 2:
            result["origin_zip"] = zips[0]
            result["destination_zip"] = zips[1]
        elif len(zips) == 1:
            result["destination_zip"] = zips[0]

        # Extract weight (look for patterns like "5lbs", "5 lbs", "5 pounds", "5lb")
        weight_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?|oz|ounces?)', message_lower)
        if weight_match:
            weight = float(weight_match.group(1))
            if 'oz' in message_lower or 'ounce' in message_lower:
                weight = weight / 16  # Convert oz to lbs
            result["weight"] = weight

        # Extract dimensions (patterns like "12x8x2", "12 x 8 x 2", "12x8x2in")
        dim_match = re.search(r'(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)', message)
        if dim_match:
            result["length"] = float(dim_match.group(1))
            result["width"] = float(dim_match.group(2))
            result["height"] = float(dim_match.group(3))

        # Extract state abbreviations
        states = ['AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
                  'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
                  'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
                  'VA','WA','WV','WI','WY']
        state_pattern = r'\b(' + '|'.join(states) + r')\b'
        state_matches = re.findall(state_pattern, message.upper())
        if state_matches:
            result["destination_state"] = state_matches[-1]  # Use last state found (usually destination)

        # Build missing fields list
        if not result["destination_zip"] and not (result["destination_city"] and result["destination_state"]):
            result["missing_fields"].append("destination")
        if not result["weight"]:
            result["missing_fields"].append("weight")

        logger.info(f"Fallback parser result: {result}")
        return result

    async def parse_shipping_info(self, message: str, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Parse shipping info from natural text. Merges with existing data if provided.
        Returns dict with extracted fields and list of missing required fields.
        """
        existing_context = ""
        if existing:
            filled = {k: v for k, v in existing.items() if v is not None}
            if filled:
                existing_context = f"\n\nAlready collected info (keep these unless user is correcting them):\n{json.dumps(filled, indent=2)}"

        prompt = f"""Extract shipping information from this message. Return JSON only, no markdown.

This is for a shipping label. There is a DESTINATION (to) address and an ORIGIN (from) address.
The user's default origin is already pre-filled, so most messages describe the DESTINATION.

Message: "{message}"{existing_context}

Return this exact JSON structure (use null for values not mentioned in the message):
{{
    "to_name": "recipient/destination name or null",
    "to_street": "destination street address (main street line only, no apt/suite/unit) or null",
    "to_street2": "apartment, suite, unit, floor number or null (e.g. 'Apt 4B', 'Suite 200', 'Unit 3')",
    "to_city": "destination city or null",
    "to_state": "2-letter state code or null",
    "to_zip": "5-digit ZIP or null",
    "to_phone": "10-digit phone number (digits only) or null",
    "to_email": "recipient email address or null",
    "from_name": "sender/origin name or null (only if user explicitly provides a FROM address)",
    "from_street": "origin street address or null",
    "from_city": "origin city or null",
    "from_state": "2-letter state code or null",
    "from_zip": "5-digit ZIP or null",
    "from_phone": "origin phone or null",
    "weight": number in pounds or null,
    "length": number in inches or null,
    "width": number in inches or null,
    "height": number in inches or null
}}

CRITICAL rules for from vs to:
- The origin (from) address is ALREADY PRE-FILLED from config. Do NOT guess or invent a from address.
- ASSUME ALL addresses are the DESTINATION (to_*) unless the user EXPLICITLY writes "from" or "ship from"
- If the user gives an address with NO "from" keyword, it is ALWAYS the DESTINATION — put it in to_* fields
- NEVER fill from_* fields unless the user literally writes "from [address]" or "ship from [address]"
- Set ALL from_* fields to null unless the user explicitly provides an origin address
- A pasted address block (name, street, city, state, zip) with no "from" keyword = DESTINATION

Other rules:
- Phone numbers: strip formatting, return 10 digits only
- Email: extract if present (e.g. "email john@example.com")
- State: always return 2-letter abbreviation (e.g. "CA", "TX")
- ZIP: always return 5 digits
- Weight: convert ounces to pounds if needed (16oz = 1lb)
- Dimensions: if user says "12x8x4" that's length=12, width=8, height=4
- If user mentions a city/state but no ZIP, still extract city and state
- Street2: separate apt/suite/unit/floor from main street. e.g. "123 Main St Apt 4B" → to_street="123 Main St", to_street2="Apt 4B"
- Return ONLY the JSON object, no other text."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.MODEL,
                contents=prompt,
            )
            text = response.text.strip()

            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            parsed = json.loads(text.strip())

            # Merge with existing data - new non-null values override
            merged = dict(existing) if existing else {}
            for key, value in parsed.items():
                if value is not None:
                    merged[key] = value

            # Determine missing required fields
            required = ["to_name", "to_street", "to_city", "to_state", "to_zip", "to_phone", "weight"]
            missing = [f for f in required if not merged.get(f)]

            # Dimensions default to 12x12x12 if not provided, so not strictly required
            # but note it for the user
            has_dimensions = all(merged.get(d) for d in ["length", "width", "height"])

            return {
                "collected": merged,
                "missing": missing,
                "has_dimensions": has_dimensions,
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse shipping JSON from Gemini: {e}")
            return {"collected": existing or {}, "missing": ["all"], "has_dimensions": False}
        except Exception as e:
            logger.error(f"Failed to parse shipping info: {e}")
            return {"collected": existing or {}, "missing": ["all"], "has_dimensions": False}

    async def parse_calendar_text(self, email_body: str) -> Optional[Dict[str, Any]]:
        """
        Extract calendar event details from plain text email.
        """
        prompt = f"""Extract calendar event information from this email. Return JSON only, no markdown.

Email:
{email_body}

Return this exact JSON structure (use null for missing values):
{{
    "title": "string",
    "date": "YYYY-MM-DD",
    "start_time": "HH:MM" (24-hour format),
    "end_time": "HH:MM or null",
    "location": "string or null",
    "meeting_link": "URL or null",
    "description": "brief summary or null"
}}

Return ONLY the JSON object, no other text."""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.MODEL,
                contents=prompt,
            )
            text = response.text.strip()

            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            text = text.strip()
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse calendar JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse calendar text: {e}")
            return None

    async def chat_with_context(
        self,
        question: str,
        calendar_events: List[Dict],
        drive_files: List[Dict],
        shipping_labels: List[Dict]
    ) -> str:
        """
        Answer user question using provided context.
        """
        context_parts = []

        if calendar_events:
            events_text = "\n".join([
                f"- {e.get('title', 'Untitled')} on {e.get('start_time', 'unknown time')}" +
                (f" at {e['location']}" if e.get('location') else "") +
                (f" (link: {e['meeting_link']})" if e.get('meeting_link') else "")
                for e in calendar_events[:10]
            ])
            context_parts.append(f"UPCOMING EVENTS:\n{events_text}")

        if drive_files:
            files_text = "\n".join([
                f"- {f.get('name', 'Unknown')} (folder: {f.get('folder_name', 'root')}) - {f.get('web_view_link', 'no link')}"
                for f in drive_files[:20]
            ])
            context_parts.append(f"DRIVE FILES:\n{files_text}")

        if shipping_labels:
            labels_text = "\n".join([
                f"- {l.get('tracking_number', 'N/A')} via {l.get('carrier', 'unknown')} to {l.get('to_address', {}).get('city', 'unknown') if isinstance(l.get('to_address'), dict) else 'unknown'} ({l.get('status', 'unknown')})"
                for l in shipping_labels[:10]
            ])
            context_parts.append(f"RECENT SHIPMENTS:\n{labels_text}")

        context = "\n\n".join(context_parts) if context_parts else "No context available."

        prompt = f"""You are a helpful assistant. Answer the user's question using only the context provided.
If the information isn't in the context, say you don't have that information.
Keep responses concise and friendly.

CONTEXT:
{context}

USER QUESTION: {question}

ANSWER:"""

        try:
            response = await self.client.aio.models.generate_content(
                model=self.MODEL,
                contents=prompt,
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini chat error: {e}")
            return "Sorry, I encountered an error processing your question."

    async def generate_follow_up_question(self, missing_fields: List[str]) -> str:
        """Generate a friendly follow-up question for missing shipping info."""
        field_questions = {
            "destination_zip": "What's the destination ZIP code?",
            "destination_city": "What city are you shipping to?",
            "destination_state": "What state are you shipping to?",
            "weight": "How much does the package weigh (in pounds)?",
            "length": "What are the package dimensions? (length x width x height in inches)",
            "width": "What are the package dimensions?",
            "height": "What are the package dimensions?",
        }

        questions = []
        seen_dimension_question = False

        for f in missing_fields[:3]:
            if f in ["length", "width", "height"]:
                if not seen_dimension_question:
                    questions.append(field_questions.get("length", f"What's the {f}?"))
                    seen_dimension_question = True
            else:
                questions.append(field_questions.get(f, f"What's the {f}?"))

        return " ".join(questions)

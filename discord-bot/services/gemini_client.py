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

    def build_shipping_system_context(self, default_origin: Dict[str, str]) -> str:
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
            "- ALWAYS call set_package when the user mentions weight or dimensions, even if other info is redundant\n"
            "- ALWAYS call at least one tool for every user message that contains shipping info\n"
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

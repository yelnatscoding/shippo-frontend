"""Gemini AI client for natural language processing"""

import os
import google.generativeai as genai
from typing import Optional, Dict, Any, List
import json
import logging

logger = logging.getLogger(__name__)


class GeminiClient:
    """Wrapper for Google Gemini API"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not configured")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")
        logger.info("Gemini client initialized")

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
            response = await self.model.generate_content_async(prompt)
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
            return {"error": str(e), "missing_fields": ["all"]}

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
            response = await self.model.generate_content_async(prompt)
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
            response = await self.model.generate_content_async(prompt)
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

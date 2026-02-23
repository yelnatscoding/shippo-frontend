"""Calendar event parser for iCal and text formats"""

import re
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional, List
from icalendar import Calendar
import logging

logger = logging.getLogger(__name__)


class CalendarParser:
    """Parse calendar events from various formats"""

    def parse_ics(self, ics_content: bytes) -> List[Dict[str, Any]]:
        """Parse iCal (.ics) content into event dicts"""
        events = []

        try:
            cal = Calendar.from_ical(ics_content)

            for component in cal.walk():
                if component.name == "VEVENT":
                    event = self._parse_vevent(component)
                    if event:
                        events.append(event)

        except Exception as e:
            logger.error(f"Failed to parse ICS: {e}")

        return events

    def _parse_vevent(self, component) -> Optional[Dict[str, Any]]:
        """Parse VEVENT component"""
        try:
            # Get start time
            dtstart = component.get("dtstart")
            if not dtstart:
                return None

            start_dt = dtstart.dt

            # Handle date-only (all-day events) vs datetime
            if isinstance(start_dt, date) and not isinstance(start_dt, datetime):
                start_dt = datetime.combine(start_dt, datetime.min.time()).replace(tzinfo=timezone.utc)
            elif hasattr(start_dt, "tzinfo") and start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)

            # Get end time
            dtend = component.get("dtend")
            end_dt = None
            if dtend:
                end_dt = dtend.dt
                if isinstance(end_dt, date) and not isinstance(end_dt, datetime):
                    end_dt = datetime.combine(end_dt, datetime.min.time()).replace(tzinfo=timezone.utc)
                elif hasattr(end_dt, "tzinfo") and end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)

            # Extract meeting link from description or location
            description = str(component.get("description", "") or "")
            location = str(component.get("location", "") or "")
            meeting_link = self._extract_meeting_link(description + " " + location)

            # Get organizer email
            organizer = component.get("organizer")
            organizer_email = None
            if organizer:
                organizer_str = str(organizer)
                if "mailto:" in organizer_str.lower():
                    organizer_email = organizer_str.split(":")[-1].strip()

            return {
                "uid": str(component.get("uid", "")),
                "title": str(component.get("summary", "Untitled Event")),
                "description": description,
                "start_time": start_dt,
                "end_time": end_dt,
                "location": location if location else None,
                "organizer_email": organizer_email,
                "meeting_link": meeting_link,
                "raw_data": {
                    "rrule": str(component.get("rrule", "")) if component.get("rrule") else None,
                    "status": str(component.get("status", "")),
                }
            }

        except Exception as e:
            logger.error(f"Failed to parse VEVENT: {e}")
            return None

    def _extract_meeting_link(self, text: str) -> Optional[str]:
        """Extract video meeting link from text"""
        patterns = [
            r"(https?://[^\s]*zoom\.us/[^\s]+)",
            r"(https?://meet\.google\.com/[^\s]+)",
            r"(https?://teams\.microsoft\.com/[^\s]+)",
            r"(https?://[^\s]*webex\.com/[^\s]+)",
            r"(https?://[^\s]*gotomeeting\.com/[^\s]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                link = match.group(1).rstrip(".,;)>")
                return link

        return None

    def parse_google_calendar_link(self, email_body: str) -> Optional[Dict[str, Any]]:
        """
        Extract event details from Google Calendar email invitation.
        These emails have a specific format.
        """
        event = {}

        # Look for "When:" line
        when_match = re.search(r"When:\s*(.+?)(?:\n|$)", email_body)
        if when_match:
            event["when_text"] = when_match.group(1).strip()

        # Look for "Where:" line
        where_match = re.search(r"Where:\s*(.+?)(?:\n|$)", email_body)
        if where_match:
            event["location"] = where_match.group(1).strip()

        # Look for meeting link
        event["meeting_link"] = self._extract_meeting_link(email_body)

        # Look for event title in subject pattern
        title_match = re.search(r"Invitation:\s*(.+?)(?:\s*@|\n|$)", email_body)
        if title_match:
            event["title"] = title_match.group(1).strip()

        if not event:
            return None

        return event

    def is_calendar_email(self, email_dict: Dict) -> bool:
        """Check if email appears to be a calendar invitation"""
        subject = email_dict.get("subject", "").lower()
        from_addr = email_dict.get("from", "").lower()

        # Check for calendar keywords in subject
        calendar_keywords = ["invitation", "meeting", "calendar", "event", "rsvp", "invite", "accepted:", "declined:", "tentative:"]
        if any(kw in subject for kw in calendar_keywords):
            return True

        # Check for Google Calendar sender
        if "calendar-notification@google.com" in from_addr:
            return True

        # Check for Microsoft/Outlook calendar
        if "calendar@microsoft.com" in from_addr or "outlook" in from_addr:
            return True

        # Check for ICS attachments
        if email_dict.get("attachments"):
            for att in email_dict["attachments"]:
                filename = att.get("filename", "")
                if filename and filename.lower().endswith(".ics"):
                    return True
                content_type = att.get("content_type", "").lower()
                if "calendar" in content_type:
                    return True

        return False

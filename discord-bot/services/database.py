"""Database connection and operations"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)


class Database:
    """Postgres database wrapper"""

    def __init__(self, url: Optional[str] = None):
        self.url = url or os.getenv("POSTGRES_URL")
        if not self.url:
            raise ValueError("Database URL not configured")

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = psycopg2.connect(self.url)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self, schema_path: str = None):
        """Initialize database schema"""
        if schema_path is None:
            schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
        logger.info("Database schema initialized")

    # Calendar operations
    def save_event(self, event: Dict[str, Any]) -> int:
        """Save calendar event, return ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO calendar_events
                    (event_uid, title, description, start_time, end_time,
                     location, organizer_email, meeting_link, source_email, raw_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_uid) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        start_time = EXCLUDED.start_time,
                        end_time = EXCLUDED.end_time,
                        location = EXCLUDED.location,
                        meeting_link = EXCLUDED.meeting_link
                    RETURNING id
                """, (
                    event.get("uid"),
                    event.get("title"),
                    event.get("description"),
                    event.get("start_time"),
                    event.get("end_time"),
                    event.get("location"),
                    event.get("organizer_email"),
                    event.get("meeting_link"),
                    event.get("source_email"),
                    json.dumps(event.get("raw_data", {}))
                ))
                return cur.fetchone()[0]

    def update_event_discord_ids(self, event_id: int, discord_event_id: str, discord_message_id: str):
        """Update event with Discord IDs (only updates non-empty values)"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE calendar_events
                    SET discord_event_id = CASE WHEN %s != '' THEN %s ELSE discord_event_id END,
                        discord_message_id = CASE WHEN %s != '' THEN %s ELSE discord_message_id END
                    WHERE id = %s
                """, (discord_event_id, discord_event_id, discord_message_id, discord_message_id, event_id))

    def get_event_by_uid(self, event_uid: str) -> Optional[Dict]:
        """Get event by its unique calendar UID"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM calendar_events WHERE event_uid = %s
                """, (event_uid,))
                row = cur.fetchone()
                return dict(row) if row else None

    def get_event_by_message_id(self, message_id: str) -> Optional[Dict]:
        """Get event by Discord message ID"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM calendar_events WHERE discord_message_id = %s
                """, (message_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def save_rsvp(self, event_id: int, user_id: str, username: str, response: str) -> bool:
        """Save RSVP, return True if new/changed"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO calendar_rsvps (event_id, discord_user_id, discord_username, response)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (event_id, discord_user_id) DO UPDATE SET
                        response = EXCLUDED.response,
                        email_sent = FALSE
                    RETURNING (xmax = 0) AS is_new
                """, (event_id, user_id, username, response))
                return cur.fetchone()[0]

    def get_pending_rsvps(self, event_id: int) -> List[Dict]:
        """Get RSVPs that haven't been emailed yet"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM calendar_rsvps
                    WHERE event_id = %s AND email_sent = FALSE
                """, (event_id,))
                return [dict(row) for row in cur.fetchall()]

    def mark_rsvp_sent(self, rsvp_id: int):
        """Mark RSVP as emailed"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE calendar_rsvps SET email_sent = TRUE WHERE id = %s
                """, (rsvp_id,))

    def get_upcoming_events(self, limit: int = 10) -> List[Dict]:
        """Get upcoming calendar events"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM calendar_events
                    WHERE start_time > NOW()
                    ORDER BY start_time
                    LIMIT %s
                """, (limit,))
                return [dict(row) for row in cur.fetchall()]

    # Shipping operations
    def save_label(self, label: Dict[str, Any]) -> int:
        """Save shipping label, return ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO shipping_labels
                    (tracking_number, carrier, service, provider, provider_label_id,
                     provider_shipment_id, rate_amount, label_pdf_base64, label_url,
                     from_address, to_address, parcel, discord_user_id, discord_message_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    label["tracking_number"],
                    label["carrier"],
                    label["service"],
                    label["provider"],
                    label.get("provider_label_id"),
                    label.get("provider_shipment_id"),
                    label["rate_amount"],
                    label.get("label_pdf_base64"),
                    label.get("label_url"),
                    json.dumps(label["from_address"]),
                    json.dumps(label["to_address"]),
                    json.dumps(label["parcel"]),
                    label.get("discord_user_id"),
                    label.get("discord_message_id")
                ))
                return cur.fetchone()[0]

    def get_label_by_tracking(self, tracking_number: str) -> Optional[Dict]:
        """Get label by tracking number"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM shipping_labels WHERE tracking_number = %s
                """, (tracking_number,))
                row = cur.fetchone()
                return dict(row) if row else None

    def get_user_labels(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get labels for a user"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM shipping_labels
                    WHERE discord_user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (user_id, limit))
                return [dict(row) for row in cur.fetchall()]

    def get_recent_labels(self, limit: int = 10) -> List[Dict]:
        """Get recent labels for AI context"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM shipping_labels
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                return [dict(row) for row in cur.fetchall()]

    def void_label(self, tracking_number: str) -> bool:
        """Mark label as voided"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE shipping_labels
                    SET status = 'voided', voided_at = NOW()
                    WHERE tracking_number = %s AND status = 'active'
                    RETURNING id
                """, (tracking_number,))
                result = cur.fetchone()
                return result is not None

    # Drive operations
    def save_drive_file(self, file: Dict[str, Any]):
        """Save or update drive file"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO drive_files
                    (file_id, name, mime_type, folder_id, folder_name, web_view_link, modified_time, last_seen)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (file_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        modified_time = EXCLUDED.modified_time,
                        last_seen = NOW()
                """, (
                    file["id"],
                    file["name"],
                    file.get("mimeType"),
                    file.get("folder_id"),
                    file.get("folder_name"),
                    file.get("webViewLink"),
                    file.get("modifiedTime")
                ))

    def search_drive_files(self, query: str, limit: int = 10) -> List[Dict]:
        """Search drive files by name"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM drive_files
                    WHERE name ILIKE %s
                    ORDER BY modified_time DESC
                    LIMIT %s
                """, (f"%{query}%", limit))
                return [dict(row) for row in cur.fetchall()]

    def get_all_drive_files(self, limit: int = 100) -> List[Dict]:
        """Get all drive files for AI context"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM drive_files
                    ORDER BY modified_time DESC
                    LIMIT %s
                """, (limit,))
                return [dict(row) for row in cur.fetchall()]

"""Email client for IMAP/SMTP operations"""

import email
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from imapclient import IMAPClient
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class EmailClient:
    """IMAP/SMTP email client for calendar sync"""

    def __init__(
        self,
        email_address: str,
        password: str,
        imap_host: str = "imap.purelymail.com",
        smtp_host: str = "smtp.purelymail.com",
        imap_port: int = 993,
        smtp_port: int = 587
    ):
        self.email_address = email_address
        self.password = password
        self.imap_host = imap_host
        self.smtp_host = smtp_host
        self.imap_port = imap_port
        self.smtp_port = smtp_port

    def fetch_new_emails(self, folder: str = "INBOX", since_uid: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetch new emails from mailbox.
        Returns list of email dicts with subject, from, body, attachments.
        """
        emails = []

        try:
            with IMAPClient(self.imap_host, port=self.imap_port, ssl=True) as client:
                client.login(self.email_address, self.password)
                client.select_folder(folder)

                # Search for unseen emails or emails after a UID
                if since_uid and since_uid > 0:
                    messages = client.search(["UID", f"{since_uid + 1}:*"])
                else:
                    messages = client.search(["UNSEEN"])

                if not messages:
                    return emails

                # Fetch email data
                fetched = client.fetch(messages, ["RFC822", "UID"])

                for uid, data in fetched.items():
                    raw_email = data[b"RFC822"]
                    msg = email.message_from_bytes(raw_email)

                    email_dict = {
                        "uid": uid,
                        "message_id": msg.get("Message-ID"),
                        "subject": msg.get("Subject", ""),
                        "from": msg.get("From", ""),
                        "to": msg.get("To", ""),
                        "date": msg.get("Date", ""),
                        "body": "",
                        "html_body": "",
                        "attachments": []
                    }

                    # Parse body and attachments
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            disposition = str(part.get("Content-Disposition", ""))

                            if "attachment" in disposition:
                                filename = part.get_filename()
                                content = part.get_payload(decode=True)
                                email_dict["attachments"].append({
                                    "filename": filename,
                                    "content_type": content_type,
                                    "content": content
                                })
                            elif content_type == "text/plain":
                                payload = part.get_payload(decode=True)
                                if payload:
                                    email_dict["body"] = payload.decode("utf-8", errors="ignore")
                            elif content_type == "text/html":
                                payload = part.get_payload(decode=True)
                                if payload:
                                    email_dict["html_body"] = payload.decode("utf-8", errors="ignore")
                    else:
                        payload = msg.get_payload(decode=True)
                        if payload:
                            email_dict["body"] = payload.decode("utf-8", errors="ignore")

                    emails.append(email_dict)

                logger.info(f"Fetched {len(emails)} emails from {self.email_address}")

        except Exception as e:
            logger.error(f"Error fetching emails: {e}")

        return emails

    def send_rsvp_reply(
        self,
        to_address: str,
        original_subject: str,
        response: str,
        responder_name: str
    ) -> bool:
        """
        Send RSVP response email.
        response: 'accepted', 'declined', 'maybe'
        """
        response_text = {
            "accepted": "has accepted",
            "declined": "has declined",
            "maybe": "has tentatively accepted"
        }

        subject = f"Re: {original_subject}"
        body = f"{responder_name} {response_text.get(response, response)} the meeting invitation."

        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_address
            msg["To"] = to_address
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_address, self.password)
                server.send_message(msg)

            logger.info(f"Sent RSVP ({response}) to {to_address}")
            return True

        except Exception as e:
            logger.error(f"Error sending RSVP: {e}")
            return False

    def get_ics_attachments(self, email_dict: Dict) -> List[bytes]:
        """Extract .ics calendar attachments from email"""
        ics_files = []
        for att in email_dict.get("attachments", []):
            filename = att.get("filename", "").lower() if att.get("filename") else ""
            content_type = att.get("content_type", "").lower()

            if filename.endswith(".ics") or "calendar" in content_type:
                if att.get("content"):
                    ics_files.append(att["content"])

        return ics_files

    def mark_as_read(self, folder: str, uid: int) -> bool:
        """Mark an email as read"""
        try:
            with IMAPClient(self.imap_host, port=self.imap_port, ssl=True) as client:
                client.login(self.email_address, self.password)
                client.select_folder(folder)
                client.add_flags([uid], [r"\Seen"])
                return True
        except Exception as e:
            logger.error(f"Error marking email as read: {e}")
            return False

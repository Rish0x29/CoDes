"""Email reader module - connects to iOS Mail via IMAP and fetches job emails."""

import email
import imaplib
import logging
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class EmailMessage:
    """Represents a parsed email message."""

    def __init__(self, uid, subject, sender, date, body_text, body_html, links):
        self.uid = uid
        self.subject = subject
        self.sender = sender
        self.date = date
        self.body_text = body_text
        self.body_html = body_html
        self.links = links

    def __repr__(self):
        return f"EmailMessage(subject={self.subject!r}, sender={self.sender!r}, date={self.date})"


class EmailReader:
    """Reads emails from an IMAP server (iCloud/iOS Mail)."""

    def __init__(self, config):
        self.server = config["email"]["imap_server"]
        self.port = config["email"].get("imap_port", 993)
        self.username = config["email"]["username"]
        self.password = config["email"]["password"]
        self.mailbox = config["email"].get("mailbox", "INBOX")
        self.scan_days = config["email"].get("scan_days", 7)
        self.mark_as_read = config["email"].get("mark_as_read", False)
        self.conn = None

    def connect(self):
        """Establish IMAP connection."""
        logger.info(f"Connecting to {self.server}:{self.port}")
        self.conn = imaplib.IMAP4_SSL(self.server, self.port)
        self.conn.login(self.username, self.password)
        self.conn.select(self.mailbox)
        logger.info(f"Connected and selected mailbox: {self.mailbox}")

    def disconnect(self):
        """Close IMAP connection."""
        if self.conn:
            try:
                self.conn.close()
                self.conn.logout()
            except Exception:
                pass
            self.conn = None

    def fetch_recent_emails(self, max_results=100):
        """Fetch emails from the last N days."""
        if not self.conn:
            self.connect()

        since_date = (datetime.now() - timedelta(days=self.scan_days)).strftime("%d-%b-%Y")
        logger.info(f"Searching for emails since {since_date}")

        status, data = self.conn.search(None, f'(SINCE "{since_date}")')
        if status != "OK":
            logger.error("Failed to search emails")
            return []

        email_ids = data[0].split()
        if not email_ids:
            logger.info("No emails found in the specified date range")
            return []

        # Take the most recent ones
        email_ids = email_ids[-max_results:]
        logger.info(f"Found {len(email_ids)} emails to process")

        messages = []
        for eid in email_ids:
            try:
                msg = self._fetch_single(eid)
                if msg:
                    messages.append(msg)
            except Exception as e:
                logger.warning(f"Failed to fetch email {eid}: {e}")

        return messages

    def _fetch_single(self, email_id):
        """Fetch and parse a single email."""
        status, data = self.conn.fetch(email_id, "(RFC822)")
        if status != "OK":
            return None

        raw = data[0][1]
        msg = email.message_from_bytes(raw)

        subject = self._decode_header(msg["Subject"])
        sender = self._decode_header(msg["From"])
        date = None
        if msg["Date"]:
            try:
                date = parsedate_to_datetime(msg["Date"])
            except Exception:
                date = datetime.now()

        body_text, body_html = self._extract_body(msg)
        links = self._extract_links(body_html or body_text)

        if self.mark_as_read:
            self.conn.store(email_id, "+FLAGS", "\\Seen")

        return EmailMessage(
            uid=email_id.decode() if isinstance(email_id, bytes) else str(email_id),
            subject=subject,
            sender=sender,
            date=date,
            body_text=body_text,
            body_html=body_html,
            links=links,
        )

    def _decode_header(self, header_value):
        """Decode an email header value."""
        if not header_value:
            return ""
        decoded_parts = decode_header(header_value)
        parts = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                parts.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                parts.append(part)
        return " ".join(parts)

    def _extract_body(self, msg):
        """Extract text and HTML body from email."""
        text_body = ""
        html_body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        text_body += payload.decode(charset, errors="replace")
                elif content_type == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        html_body += payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                content = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    html_body = content
                else:
                    text_body = content

        # If we only have HTML, extract text from it
        if html_body and not text_body:
            soup = BeautifulSoup(html_body, "lxml")
            text_body = soup.get_text(separator="\n", strip=True)

        return text_body, html_body

    def _extract_links(self, content):
        """Extract all URLs from email content."""
        if not content:
            return []

        links = []
        soup = BeautifulSoup(content, "lxml") if "<" in content else None

        if soup:
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                text = a_tag.get_text(strip=True)
                links.append({"url": href, "text": text})

        return links

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

"""Notification module - sends summaries of bot activity."""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)


class Notifier:
    """Sends notification summaries."""

    def __init__(self, config):
        self.config = config
        self.notifications = config.get("notifications", {})
        self.email_config = config.get("email", {})

    def send_summary(self, results, stats):
        """Send a summary of the bot run."""
        summary_text = self._build_summary(results, stats)

        # Always log to console
        logger.info("\n" + "=" * 60)
        logger.info("APPLICATION BOT SUMMARY")
        logger.info("=" * 60)
        logger.info(summary_text)

        # Send email if configured
        if self.notifications.get("email_summary"):
            try:
                self._send_email_summary(summary_text)
            except Exception as e:
                logger.error(f"Failed to send email summary: {e}")

        return summary_text

    def _build_summary(self, results, stats):
        """Build a text summary of the run."""
        lines = [
            f"Run completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Emails scanned: {stats.get('emails_processed', 0)}",
            f"Job emails found: {stats.get('job_emails_found', 0)}",
            f"Applications attempted: {len(results)}",
            "",
        ]

        successful = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        if successful:
            lines.append(f"Successful ({len(successful)}):")
            for r in successful:
                lines.append(f"  - {r['title']} at {r['company']}: {r.get('message', '')}")
            lines.append("")

        if failed:
            lines.append(f"Failed ({len(failed)}):")
            for r in failed:
                lines.append(f"  - {r['title']} at {r['company']}: {r.get('message', '')}")
            lines.append("")

        # Overall stats
        lines.append("All-time stats:")
        lines.append(f"  Total applications: {stats.get('total_applications', 0)}")
        for status, count in stats.get("by_status", {}).items():
            lines.append(f"  {status}: {count}")

        return "\n".join(lines)

    def _send_email_summary(self, summary_text):
        """Send summary via email (using the same IMAP account's SMTP)."""
        recipient = self.notifications.get("summary_recipient")
        if not recipient:
            logger.warning("No summary recipient configured")
            return

        msg = MIMEMultipart()
        msg["From"] = self.email_config["username"]
        msg["To"] = recipient
        msg["Subject"] = f"Job Bot Summary - {datetime.now().strftime('%Y-%m-%d')}"
        msg.attach(MIMEText(summary_text, "plain"))

        # Determine SMTP server from IMAP server
        imap_server = self.email_config["imap_server"]
        smtp_server = imap_server.replace("imap", "smtp")
        smtp_port = 587

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(self.email_config["username"], self.email_config["password"])
            server.send_message(msg)

        logger.info(f"Summary email sent to {recipient}")

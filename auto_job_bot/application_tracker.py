"""Application tracker - SQLite database for tracking job applications."""

import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ApplicationTracker:
    """Tracks job applications in a local SQLite database."""

    def __init__(self, db_path="job_applications.db"):
        self.db_path = db_path
        self.conn = None
        self._init_db()

    def _init_db(self):
        """Initialize the database and create tables."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                location TEXT DEFAULT '',
                salary TEXT DEFAULT '',
                application_url TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                email_uid TEXT DEFAULT '',
                cover_letter TEXT DEFAULT '',
                applied_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT DEFAULT ''
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS email_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_uid TEXT UNIQUE NOT NULL,
                subject TEXT,
                sender TEXT,
                is_job_email BOOLEAN DEFAULT 0,
                confidence_score REAL DEFAULT 0,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def is_email_processed(self, email_uid):
        """Check if an email has already been processed."""
        row = self.conn.execute(
            "SELECT 1 FROM email_log WHERE email_uid = ?", (email_uid,)
        ).fetchone()
        return row is not None

    def log_email(self, email_uid, subject, sender, is_job, confidence):
        """Log a processed email."""
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO email_log (email_uid, subject, sender, is_job_email, confidence_score) "
                "VALUES (?, ?, ?, ?, ?)",
                (email_uid, subject, sender, is_job, confidence),
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to log email: {e}")

    def is_already_applied(self, company, title):
        """Check if we've already applied to this job."""
        row = self.conn.execute(
            "SELECT 1 FROM applications WHERE LOWER(company) = LOWER(?) AND LOWER(title) = LOWER(?)",
            (company, title),
        ).fetchone()
        return row is not None

    def record_application(self, job_details, status="applied", cover_letter=""):
        """Record a job application."""
        try:
            self.conn.execute(
                "INSERT INTO applications (company, title, location, salary, application_url, "
                "status, email_uid, cover_letter, applied_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_details.company,
                    job_details.title,
                    job_details.location,
                    job_details.salary,
                    job_details.application_url,
                    status,
                    job_details.source_email_uid,
                    cover_letter,
                    datetime.now().isoformat(),
                ),
            )
            self.conn.commit()
            logger.info(f"Recorded application: {job_details.title} at {job_details.company}")
        except sqlite3.Error as e:
            logger.error(f"Failed to record application: {e}")

    def update_status(self, application_id, status, notes=""):
        """Update application status."""
        self.conn.execute(
            "UPDATE applications SET status = ?, notes = ? WHERE id = ?",
            (status, notes, application_id),
        )
        self.conn.commit()

    def get_all_applications(self, status=None):
        """Get all tracked applications."""
        if status:
            rows = self.conn.execute(
                "SELECT * FROM applications WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM applications ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self):
        """Get application statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        by_status = self.conn.execute(
            "SELECT status, COUNT(*) as count FROM applications GROUP BY status"
        ).fetchall()
        emails_processed = self.conn.execute("SELECT COUNT(*) FROM email_log").fetchone()[0]
        job_emails = self.conn.execute(
            "SELECT COUNT(*) FROM email_log WHERE is_job_email = 1"
        ).fetchone()[0]

        return {
            "total_applications": total,
            "by_status": {row["status"]: row["count"] for row in by_status},
            "emails_processed": emails_processed,
            "job_emails_found": job_emails,
        }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

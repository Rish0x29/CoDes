"""Main entry point for the Auto Job Application Bot."""

import asyncio
import logging
import sys
import argparse

from rich.console import Console
from rich.table import Table
from rich.logging import RichHandler

from .config import load_config
from .email_reader import EmailReader
from .job_parser import JobParser
from .application_tracker import ApplicationTracker
from .cover_letter import CoverLetterGenerator
from .auto_applier import AutoApplier
from .notifier import Notifier

console = Console()


def setup_logging(level="INFO"):
    """Configure logging with rich output."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Auto Job Application Bot")
    parser.add_argument("-c", "--config", help="Path to config.yaml", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Preview mode, don't actually apply")
    parser.add_argument("--stats", action="store_true", help="Show application statistics")
    parser.add_argument("--list", action="store_true", help="List all tracked applications")
    parser.add_argument("--scan-only", action="store_true", help="Scan emails but don't apply")
    return parser.parse_args()


async def run_bot(config):
    """Main bot execution loop."""
    logger = logging.getLogger(__name__)

    bot_config = config.get("bot", {})
    max_apps = bot_config.get("max_applications_per_run", 10)
    generate_cl = bot_config.get("generate_cover_letters", True)

    parser = JobParser(config)
    tracker = ApplicationTracker(bot_config.get("db_path", "job_applications.db"))
    cl_generator = CoverLetterGenerator(config) if generate_cl else None
    notifier = Notifier(config)

    results = []
    job_emails_count = 0

    # Step 1: Read emails
    console.print("\n[bold blue]Step 1:[/] Connecting to email...", highlight=False)
    with EmailReader(config) as reader:
        emails = reader.fetch_recent_emails()
        console.print(f"  Found [bold]{len(emails)}[/] recent emails")

        # Step 2: Classify and parse
        console.print("\n[bold blue]Step 2:[/] Scanning for job emails...", highlight=False)
        job_candidates = []

        for email_msg in emails:
            if tracker.is_email_processed(email_msg.uid):
                continue

            confidence = parser.is_job_email(email_msg)
            is_job = confidence >= 0.3
            tracker.log_email(email_msg.uid, email_msg.subject, email_msg.sender, is_job, confidence)

            if is_job:
                job_emails_count += 1
                job = parser.parse_job_details(email_msg)
                job_candidates.append(job)
                logger.debug(f"Job found: {job}")

        console.print(f"  Found [bold green]{job_emails_count}[/] job emails")

    # Step 3: Filter by preferences
    console.print("\n[bold blue]Step 3:[/] Filtering by preferences...", highlight=False)
    matched_jobs = []
    for job in job_candidates:
        if tracker.is_already_applied(job.company, job.title):
            logger.debug(f"Already applied: {job.title} at {job.company}")
            continue

        matches, reasons = parser.matches_preferences(job)
        if matches:
            matched_jobs.append(job)
        else:
            logger.debug(f"Skipped: {job.title} - {reasons}")

    console.print(f"  [bold green]{len(matched_jobs)}[/] jobs match your preferences")

    # Display matched jobs
    if matched_jobs:
        table = Table(title="Matching Jobs Found")
        table.add_column("#", style="dim")
        table.add_column("Title", style="bold")
        table.add_column("Company", style="cyan")
        table.add_column("Location")
        table.add_column("Confidence", justify="right")

        for i, job in enumerate(matched_jobs[:max_apps], 1):
            table.add_row(
                str(i), job.title, job.company, job.location or "N/A",
                f"{job.confidence_score:.0%}"
            )
        console.print(table)

    # Step 4: Apply
    console.print(f"\n[bold blue]Step 4:[/] Applying to jobs (max {max_apps})...", highlight=False)
    if config.get("bot", {}).get("dry_run", True):
        console.print("  [yellow]DRY RUN MODE[/] - No actual applications will be submitted")

    applier = AutoApplier(config)
    try:
        for job in matched_jobs[:max_apps]:
            # Generate cover letter
            cover_letter = ""
            if cl_generator:
                try:
                    cover_letter = cl_generator.generate(job)
                    logger.debug(f"Generated cover letter for {job.title}")
                except Exception as e:
                    logger.warning(f"Cover letter generation failed: {e}")

            # Apply
            success, message = await applier.apply(job, cover_letter)

            result = {
                "title": job.title,
                "company": job.company,
                "url": job.application_url,
                "success": success,
                "message": message,
            }
            results.append(result)

            status = "applied" if success else "failed"
            tracker.record_application(job, status=status, cover_letter=cover_letter)

            if success:
                console.print(f"  [green]✓[/] {job.title} at {job.company}: {message}")
            else:
                console.print(f"  [red]✗[/] {job.title} at {job.company}: {message}")

    finally:
        await applier.close()

    # Step 5: Summary
    stats = tracker.get_stats()
    summary = notifier.send_summary(results, stats)
    tracker.close()

    return results


def show_stats(config):
    """Show application statistics."""
    db_path = config.get("bot", {}).get("db_path", "job_applications.db")
    with ApplicationTracker(db_path) as tracker:
        stats = tracker.get_stats()

        console.print("\n[bold]Application Statistics[/]")
        console.print(f"  Total applications: {stats['total_applications']}")
        console.print(f"  Emails processed: {stats['emails_processed']}")
        console.print(f"  Job emails found: {stats['job_emails_found']}")
        console.print("\n  By status:")
        for status, count in stats.get("by_status", {}).items():
            console.print(f"    {status}: {count}")


def list_applications(config):
    """List all tracked applications."""
    db_path = config.get("bot", {}).get("db_path", "job_applications.db")
    with ApplicationTracker(db_path) as tracker:
        apps = tracker.get_all_applications()

        if not apps:
            console.print("No applications tracked yet.")
            return

        table = Table(title=f"All Applications ({len(apps)} total)")
        table.add_column("ID", style="dim")
        table.add_column("Title", style="bold")
        table.add_column("Company", style="cyan")
        table.add_column("Status")
        table.add_column("Applied At")

        for app in apps:
            status_style = {"applied": "green", "failed": "red", "pending": "yellow"}.get(
                app["status"], ""
            )
            table.add_row(
                str(app["id"]),
                app["title"],
                app["company"],
                f"[{status_style}]{app['status']}[/{status_style}]",
                app.get("applied_at", "N/A"),
            )
        console.print(table)


def main():
    """Main entry point."""
    args = parse_args()

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Configuration error:[/] {e}")
        sys.exit(1)

    if args.dry_run:
        config.setdefault("bot", {})["dry_run"] = True

    setup_logging(config.get("bot", {}).get("log_level", "INFO"))

    if args.stats:
        show_stats(config)
        return

    if args.list:
        list_applications(config)
        return

    console.print("[bold]🤖 Auto Job Application Bot[/]", highlight=False)
    console.print("=" * 40)

    asyncio.run(run_bot(config))


if __name__ == "__main__":
    main()

"""Auto applier module - automates job application form submission."""

import logging
import time

logger = logging.getLogger(__name__)


class AutoApplier:
    """Automates job application submission via browser automation."""

    def __init__(self, config):
        self.profile = config.get("profile", {})
        self.dry_run = config.get("bot", {}).get("dry_run", True)
        self.delay = config.get("bot", {}).get("delay_between_applications", 30)
        self.browser = None
        self.page = None

    async def initialize(self):
        """Initialize Playwright browser."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=False)
        self.page = await self.browser.new_page()
        logger.info("Browser initialized")

    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def apply(self, job_details, cover_letter=""):
        """Apply to a job. Returns (success: bool, message: str)."""
        if not job_details.application_url:
            return False, "No application URL found"

        if self.dry_run:
            logger.info(f"[DRY RUN] Would apply to: {job_details.title} at {job_details.company}")
            logger.info(f"[DRY RUN] URL: {job_details.application_url}")
            return True, "Dry run - application simulated"

        try:
            if not self.page:
                await self.initialize()

            logger.info(f"Navigating to: {job_details.application_url}")
            await self.page.goto(job_details.application_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(2000)

            # Try to detect and fill common application form fields
            filled = await self._try_fill_form(cover_letter)

            if filled:
                logger.info(f"Form filled for: {job_details.title} at {job_details.company}")
                # Wait for user review before final submission
                logger.info("PAUSING FOR REVIEW - Check the browser window")
                await self.page.wait_for_timeout(self.delay * 1000)
                return True, "Form filled - review required before submission"
            else:
                return False, "Could not detect application form on page"

        except Exception as e:
            logger.error(f"Application failed: {e}")
            return False, f"Error: {str(e)}"

    async def _try_fill_form(self, cover_letter=""):
        """Attempt to detect and fill common form fields."""
        filled_any = False

        # Common field mappings: (field_identifiers, value)
        field_map = [
            (["first_name", "firstname", "first-name", "fname"], self.profile.get("first_name", "")),
            (["last_name", "lastname", "last-name", "lname"], self.profile.get("last_name", "")),
            (["email", "e-mail", "email_address"], self.profile.get("email", "")),
            (["phone", "telephone", "mobile", "phone_number"], self.profile.get("phone", "")),
            (["linkedin", "linkedin_url", "linkedin_profile"], self.profile.get("linkedin", "")),
            (["github", "github_url", "github_profile"], self.profile.get("github", "")),
            (["portfolio", "website", "personal_website"], self.profile.get("portfolio", "")),
            (["location", "city", "address"], self.profile.get("location", "")),
        ]

        for identifiers, value in field_map:
            if not value:
                continue
            for identifier in identifiers:
                try:
                    # Try by name attribute
                    input_el = await self.page.query_selector(f'input[name*="{identifier}" i]')
                    if not input_el:
                        # Try by placeholder
                        input_el = await self.page.query_selector(f'input[placeholder*="{identifier}" i]')
                    if not input_el:
                        # Try by label
                        input_el = await self.page.query_selector(f'label:has-text("{identifier}") + input')

                    if input_el:
                        await input_el.fill(value)
                        filled_any = True
                        logger.debug(f"Filled field: {identifier}")
                        break
                except Exception:
                    continue

        # Try to fill cover letter textarea
        if cover_letter:
            for identifier in ["cover_letter", "cover-letter", "coverletter", "message", "additional"]:
                try:
                    textarea = await self.page.query_selector(f'textarea[name*="{identifier}" i]')
                    if not textarea:
                        textarea = await self.page.query_selector(f'textarea[placeholder*="{identifier}" i]')
                    if textarea:
                        await textarea.fill(cover_letter)
                        filled_any = True
                        logger.debug("Filled cover letter field")
                        break
                except Exception:
                    continue

        # Try to upload resume
        resume_path = self.profile.get("resume_path", "")
        if resume_path:
            try:
                file_input = await self.page.query_selector('input[type="file"]')
                if file_input:
                    await file_input.set_input_files(resume_path)
                    filled_any = True
                    logger.debug("Uploaded resume")
            except Exception as e:
                logger.debug(f"Could not upload resume: {e}")

        return filled_any

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

"""Job parser module - classifies emails and extracts job details."""

import re
import logging

logger = logging.getLogger(__name__)

# Keywords that indicate a job opportunity email
JOB_KEYWORDS = [
    "job opportunity", "job opening", "we're hiring", "we are hiring",
    "apply now", "job alert", "new jobs", "career opportunity",
    "position available", "job match", "recommended job", "job recommendation",
    "hiring for", "open position", "open role", "role at",
    "application invited", "you may be a fit", "jobs for you",
    "based on your profile", "new job", "job posting",
]

# Keywords in sender names/addresses suggesting job platforms
JOB_PLATFORM_SENDERS = [
    "linkedin", "indeed", "glassdoor", "ziprecruiter", "monster",
    "dice", "hired", "angel.co", "wellfound", "lever", "greenhouse",
    "workday", "jobvite", "smartrecruiters", "recruitee", "breezy",
    "naukri", "seek", "reed", "totaljobs", "simplyhired",
]

# Application link patterns
APPLICATION_URL_PATTERNS = [
    r"apply", r"application", r"careers", r"jobs", r"openings",
    r"lever\.co", r"greenhouse\.io", r"workday\.com", r"smartrecruiters",
    r"jobvite\.com", r"ashbyhq\.com", r"myworkdayjobs",
]


class JobDetails:
    """Extracted job details from an email."""

    def __init__(self):
        self.company = ""
        self.title = ""
        self.location = ""
        self.salary = ""
        self.description = ""
        self.requirements = []
        self.application_url = ""
        self.source_email_uid = ""
        self.confidence_score = 0.0

    def to_dict(self):
        return {
            "company": self.company,
            "title": self.title,
            "location": self.location,
            "salary": self.salary,
            "description": self.description,
            "requirements": self.requirements,
            "application_url": self.application_url,
            "source_email_uid": self.source_email_uid,
            "confidence_score": self.confidence_score,
        }

    def __repr__(self):
        return f"JobDetails(title={self.title!r}, company={self.company!r}, confidence={self.confidence_score:.2f})"


class JobParser:
    """Parses and classifies job emails."""

    def __init__(self, config):
        self.preferences = config.get("preferences", {})
        self.desired_roles = [r.lower() for r in self.preferences.get("desired_roles", [])]
        self.preferred_locations = [l.lower() for l in self.preferences.get("preferred_locations", [])]
        self.blacklist = [c.lower() for c in self.preferences.get("blacklist_companies", [])]
        self.exclude_keywords = [k.lower() for k in self.preferences.get("exclude_keywords", [])]
        self.required_keywords = [k.lower() for k in self.preferences.get("required_keywords", [])]

    def is_job_email(self, email_msg):
        """Determine if an email is a job opportunity. Returns confidence 0-1."""
        score = 0.0
        text = f"{email_msg.subject} {email_msg.body_text}".lower()
        sender = email_msg.sender.lower()

        # Check sender against known job platforms
        for platform in JOB_PLATFORM_SENDERS:
            if platform in sender:
                score += 0.4
                break

        # Check subject/body for job keywords
        keyword_matches = sum(1 for kw in JOB_KEYWORDS if kw in text)
        score += min(keyword_matches * 0.15, 0.4)

        # Check for application links
        for link in email_msg.links:
            url = link["url"].lower()
            link_text = link["text"].lower()
            for pattern in APPLICATION_URL_PATTERNS:
                if re.search(pattern, url) or re.search(pattern, link_text):
                    score += 0.2
                    break

        return min(score, 1.0)

    def parse_job_details(self, email_msg):
        """Extract structured job details from an email."""
        job = JobDetails()
        job.source_email_uid = email_msg.uid
        job.confidence_score = self.is_job_email(email_msg)

        text = email_msg.body_text
        subject = email_msg.subject

        job.title = self._extract_title(subject, text)
        job.company = self._extract_company(email_msg.sender, subject, text)
        job.location = self._extract_location(text)
        job.salary = self._extract_salary(text)
        job.description = self._extract_description(text)
        job.requirements = self._extract_requirements(text)
        job.application_url = self._find_application_url(email_msg.links)

        return job

    def matches_preferences(self, job):
        """Check if a job matches user preferences."""
        reasons = []

        # Check blacklist
        if job.company.lower() in self.blacklist:
            reasons.append(f"Company '{job.company}' is blacklisted")
            return False, reasons

        # Check exclude keywords
        full_text = f"{job.title} {job.description}".lower()
        for kw in self.exclude_keywords:
            if kw in full_text:
                reasons.append(f"Contains excluded keyword: '{kw}'")
                return False, reasons

        # Check required keywords
        for kw in self.required_keywords:
            if kw not in full_text:
                reasons.append(f"Missing required keyword: '{kw}'")
                return False, reasons

        # Check role match
        if self.desired_roles:
            title_lower = job.title.lower()
            role_match = any(role in title_lower for role in self.desired_roles)
            if not role_match:
                reasons.append(f"Title '{job.title}' doesn't match desired roles")
                return False, reasons

        # Check location
        if self.preferred_locations and job.location:
            loc_lower = job.location.lower()
            loc_match = any(loc in loc_lower for loc in self.preferred_locations)
            if not loc_match:
                reasons.append(f"Location '{job.location}' doesn't match preferences")
                return False, reasons

        return True, ["Matches all preferences"]

    def _extract_title(self, subject, text):
        """Extract job title from email."""
        # Try common patterns in subject
        patterns = [
            r"(?:role|position|job|opening|opportunity):\s*(.+?)(?:\s*[-|@at]|$)",
            r"(?:hiring|looking for)\s+(?:a\s+)?(.+?)(?:\s+at\s+|\s*[-|]|$)",
            r"^(.+?)\s+(?:at|@|-)\s+",
        ]
        for pattern in patterns:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Try body text
        for pattern in patterns:
            match = re.search(pattern, text[:500], re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback: use subject line cleaned up
        return re.sub(r"\[.*?\]", "", subject).strip()[:100]

    def _extract_company(self, sender, subject, text):
        """Extract company name."""
        # Try "at Company" pattern
        patterns = [
            r"(?:at|@)\s+([A-Z][A-Za-z0-9\s&.]+?)(?:\s*[-|,!]|\s+is\s+|\s+has\s+|$)",
            r"([A-Z][A-Za-z0-9\s&.]+?)\s+is\s+(?:hiring|looking)",
        ]
        for pattern in patterns:
            for source in [subject, text[:300]]:
                match = re.search(pattern, source)
                if match:
                    return match.group(1).strip()

        # Extract from sender email domain
        domain_match = re.search(r"@([a-zA-Z0-9-]+)\.", sender)
        if domain_match:
            domain = domain_match.group(1)
            if domain not in ["gmail", "yahoo", "outlook", "hotmail", "icloud"]:
                return domain.replace("-", " ").title()

        return "Unknown"

    def _extract_location(self, text):
        """Extract job location."""
        patterns = [
            r"(?:location|based in|located in|office in)[\s:]+([^\n,]{3,50})",
            r"(remote|hybrid|on-?site)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_salary(self, text):
        """Extract salary information."""
        patterns = [
            r"\$[\d,]+(?:k)?(?:\s*[-–]\s*\$[\d,]+(?:k)?)?(?:\s*(?:per\s+)?(?:year|yr|annually|/yr))?",
            r"(?:salary|compensation|pay)[\s:]+([^\n]{5,60})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip()
        return ""

    def _extract_description(self, text):
        """Extract a brief job description."""
        # Take the first meaningful paragraph
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 50]
        if paragraphs:
            return paragraphs[0][:500]
        return text[:500]

    def _extract_requirements(self, text):
        """Extract job requirements."""
        requirements = []
        # Look for bullet points or numbered lists after "requirements" or "qualifications"
        req_section = re.search(
            r"(?:requirements?|qualifications?|must have|what we.re looking for)[\s:]*\n((?:[\s]*[-•*\d.]+.+\n?)+)",
            text, re.IGNORECASE
        )
        if req_section:
            lines = req_section.group(1).strip().split("\n")
            for line in lines:
                cleaned = re.sub(r"^[\s\-•*\d.]+", "", line).strip()
                if cleaned:
                    requirements.append(cleaned)
        return requirements[:10]

    def _find_application_url(self, links):
        """Find the most likely application URL from email links."""
        scored_links = []
        for link in links:
            url = link["url"].lower()
            text = link["text"].lower()
            score = 0

            for pattern in APPLICATION_URL_PATTERNS:
                if re.search(pattern, url):
                    score += 2
                if re.search(pattern, text):
                    score += 1

            if "apply" in text:
                score += 3
            if "view" in text and "job" in text:
                score += 2

            if score > 0:
                scored_links.append((score, link["url"]))

        if scored_links:
            scored_links.sort(key=lambda x: x[0], reverse=True)
            return scored_links[0][1]

        return ""

"""Cover letter generator - creates tailored cover letters using AI or templates."""

import logging

from jinja2 import Template

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = """Dear Hiring Manager,

I am writing to express my strong interest in the {{ job_title }} position at {{ company }}. \
With {{ years_of_experience }} years of experience in software development and a proven track record \
in {{ skills_summary }}, I am confident I would be a valuable addition to your team.

{% if job_description %}Based on the role description, I believe my experience aligns well with your needs. {% endif %}\
{% if requirements %}I bring expertise in {{ requirements_match }}, which directly addresses the qualifications you're seeking. {% endif %}

{{ summary }}

I am particularly drawn to {{ company }} and would welcome the opportunity to contribute to your team. \
I am available for an interview at your convenience and look forward to discussing how my background \
and skills would be an asset to your organization.

Best regards,
{{ first_name }} {{ last_name }}
{{ email }}
{{ phone }}
{% if linkedin %}LinkedIn: {{ linkedin }}{% endif %}
{% if github %}GitHub: {{ github }}{% endif %}
"""


class CoverLetterGenerator:
    """Generates tailored cover letters."""

    def __init__(self, config):
        self.profile = config.get("profile", {})
        self.ai_config = config.get("ai", {})
        self.use_ai = bool(self.ai_config.get("api_key"))

    def generate(self, job_details):
        """Generate a cover letter for a job."""
        if self.use_ai:
            try:
                return self._generate_with_ai(job_details)
            except Exception as e:
                logger.warning(f"AI generation failed, falling back to template: {e}")

        return self._generate_from_template(job_details)

    def _generate_from_template(self, job_details):
        """Generate cover letter from Jinja2 template."""
        skills = self.profile.get("skills", [])
        skills_summary = ", ".join(skills[:5]) if skills else "various technologies"

        requirements_match = ""
        if job_details.requirements:
            matching = [r for r in job_details.requirements
                        if any(s.lower() in r.lower() for s in skills)]
            requirements_match = ", ".join(matching[:3]) if matching else skills_summary

        template = Template(DEFAULT_TEMPLATE)
        return template.render(
            job_title=job_details.title,
            company=job_details.company,
            years_of_experience=self.profile.get("years_of_experience", "several"),
            skills_summary=skills_summary,
            job_description=job_details.description,
            requirements=job_details.requirements,
            requirements_match=requirements_match,
            summary=self.profile.get("summary", ""),
            first_name=self.profile.get("first_name", ""),
            last_name=self.profile.get("last_name", ""),
            email=self.profile.get("email", ""),
            phone=self.profile.get("phone", ""),
            linkedin=self.profile.get("linkedin", ""),
            github=self.profile.get("github", ""),
        )

    def _generate_with_ai(self, job_details):
        """Generate cover letter using AI API."""
        provider = self.ai_config.get("provider", "openai")
        api_key = self.ai_config["api_key"]
        model = self.ai_config.get("model", "gpt-4o")

        prompt = self._build_ai_prompt(job_details)

        if provider == "openai":
            return self._call_openai(api_key, model, prompt)
        elif provider == "anthropic":
            return self._call_anthropic(api_key, model, prompt)
        else:
            raise ValueError(f"Unsupported AI provider: {provider}")

    def _build_ai_prompt(self, job_details):
        """Build the prompt for AI cover letter generation."""
        return f"""Write a professional, concise cover letter for the following job application.
Keep it to 3-4 paragraphs. Be specific and avoid generic filler.

Job Title: {job_details.title}
Company: {job_details.company}
Location: {job_details.location}
Description: {job_details.description}
Requirements: {', '.join(job_details.requirements)}

Applicant Profile:
Name: {self.profile.get('first_name')} {self.profile.get('last_name')}
Experience: {self.profile.get('years_of_experience')} years
Skills: {', '.join(self.profile.get('skills', []))}
Summary: {self.profile.get('summary', '')}
Email: {self.profile.get('email')}
Phone: {self.profile.get('phone', '')}

Write the cover letter now:"""

    def _call_openai(self, api_key, model, prompt):
        """Call OpenAI API for cover letter generation."""
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a professional cover letter writer."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1000,
            temperature=0.7,
        )
        return response.choices[0].message.content

    def _call_anthropic(self, api_key, model, prompt):
        """Call Anthropic API for cover letter generation."""
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model or "claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

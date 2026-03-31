"""Post-processing Lambda - normalize and validate extracted fields."""

import os
import re
import json
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def normalize_date(date_str: str) -> str:
    """Normalize various date formats to ISO format."""
    patterns = [
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
        (r"\d{2}/\d{2}/\d{4}", "%m/%d/%Y"),
        (r"\d{2}-\d{2}-\d{4}", "%m-%d-%Y"),
        (r"\w+ \d{1,2}, \d{4}", "%B %d, %Y"),
        (r"\d{1,2} \w+ \d{4}", "%d %B %Y"),
    ]
    for pattern, fmt in patterns:
        match = re.search(pattern, date_str)
        if match:
            try:
                dt = datetime.strptime(match.group(), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
    return date_str


def normalize_currency(value_str: str) -> float:
    """Extract numeric value from currency strings."""
    cleaned = re.sub(r"[^\d.,\-]", "", str(value_str))
    cleaned = cleaned.replace(",", "")
    try:
        return round(float(cleaned), 2)
    except (ValueError, TypeError):
        return 0.0


def normalize_phone(phone_str: str) -> str:
    """Normalize phone numbers."""
    digits = re.sub(r"\D", "", phone_str)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == "1":
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return phone_str


def normalize_email(email_str: str) -> str:
    """Normalize and validate email."""
    email = email_str.strip().lower()
    if re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return email
    return ""


FIELD_NORMALIZERS = {
    "date": normalize_date,
    "invoice_date": normalize_date,
    "due_date": normalize_date,
    "amount": normalize_currency,
    "total": normalize_currency,
    "subtotal": normalize_currency,
    "tax": normalize_currency,
    "price": normalize_currency,
    "phone": normalize_phone,
    "telephone": normalize_phone,
    "email": normalize_email,
    "e-mail": normalize_email,
}


def compute_confidence_score(extraction_result: dict) -> float:
    """Compute overall confidence score for the extraction."""
    confidences = []

    for kv in extraction_result.get("key_value_pairs", []):
        confidences.append(kv.get("confidence", 0))

    for line in extraction_result.get("lines", []):
        confidences.append(line.get("confidence", 0))

    if not confidences:
        return 0.0

    return round(sum(confidences) / len(confidences), 2)


def post_process(extraction_result: dict) -> dict:
    """Normalize extracted fields and compute confidence."""
    normalized_pairs = []
    for kv in extraction_result.get("key_value_pairs", []):
        key_lower = kv["key"].lower().strip().rstrip(":")
        value = kv["value"]

        # Apply normalizer if available
        for field_pattern, normalizer in FIELD_NORMALIZERS.items():
            if field_pattern in key_lower:
                value = normalizer(value) if isinstance(normalizer(value), str) else normalizer(value)
                break

        normalized_pairs.append({
            "key": kv["key"],
            "key_normalized": key_lower,
            "value": value,
            "original_value": kv["value"],
            "confidence": kv.get("confidence", 0),
            "was_normalized": value != kv["value"],
        })

    overall_confidence = compute_confidence_score(extraction_result)

    return {
        **extraction_result,
        "key_value_pairs": normalized_pairs,
        "overall_confidence": overall_confidence,
        "high_confidence": overall_confidence >= 85.0,
        "needs_review": overall_confidence < 70.0,
    }


def handler(event, context):
    """Lambda handler for post-processing."""
    result = post_process(event)
    return result

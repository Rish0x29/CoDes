import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from doc_extraction.post_processor import (
    normalize_date, normalize_currency, normalize_phone, normalize_email,
    post_process, compute_confidence_score,
)


class TestNormalization:
    def test_date_iso(self):
        assert normalize_date("2024-01-15") == "2024-01-15"

    def test_date_us(self):
        assert normalize_date("01/15/2024") == "2024-01-15"

    def test_date_written(self):
        assert normalize_date("January 15, 2024") == "2024-01-15"

    def test_currency_simple(self):
        assert normalize_currency("$1,500.00") == 1500.00

    def test_currency_no_symbol(self):
        assert normalize_currency("2500.50") == 2500.50

    def test_phone_10digit(self):
        assert normalize_phone("5551234567") == "(555) 123-4567"

    def test_email_valid(self):
        assert normalize_email("  User@Example.COM  ") == "user@example.com"

    def test_email_invalid(self):
        assert normalize_email("not-an-email") == ""


class TestPostProcess:
    def test_post_process_adds_confidence(self):
        extraction = {
            "key_value_pairs": [
                {"key": "Invoice Date:", "value": "01/15/2024", "confidence": 95.0},
                {"key": "Total:", "value": "$1,500.00", "confidence": 92.0},
            ],
            "lines": [{"text": "test", "confidence": 90.0}],
            "tables": [],
        }
        result = post_process(extraction)
        assert "overall_confidence" in result
        assert result["overall_confidence"] > 0

    def test_post_process_normalizes_dates(self):
        extraction = {
            "key_value_pairs": [
                {"key": "Date:", "value": "01/15/2024", "confidence": 95.0},
            ],
            "lines": [],
            "tables": [],
        }
        result = post_process(extraction)
        normalized = result["key_value_pairs"][0]
        assert normalized["value"] == "2024-01-15"
        assert normalized["was_normalized"] is True

    def test_high_confidence_flag(self):
        extraction = {
            "key_value_pairs": [{"key": "x", "value": "y", "confidence": 99.0}],
            "lines": [{"text": "test", "confidence": 99.0}],
            "tables": [],
        }
        result = post_process(extraction)
        assert result["high_confidence"] is True
        assert result["needs_review"] is False

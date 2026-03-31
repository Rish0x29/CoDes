import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from doc_extraction.classifier import classify_by_keywords, DOC_TYPES


def test_classify_invoice():
    text = "INVOICE #12345 - Amount Due: $1,500.00 - Tax: $150 - Total: $1,650"
    result = classify_by_keywords(text)
    assert result["document_type"] == "invoice"
    assert result["confidence"] > 0.3


def test_classify_contract():
    text = "This Agreement is entered into by the Parties under these Terms and Conditions clause 1"
    result = classify_by_keywords(text)
    assert result["document_type"] == "contract"


def test_classify_form():
    text = "Application Form - Please fill in your Name: Address: Date: Signature below"
    result = classify_by_keywords(text)
    assert result["document_type"] == "form"


def test_classify_unknown():
    text = "random gibberish that matches nothing specific"
    result = classify_by_keywords(text)
    # Low confidence = unknown
    assert "document_type" in result

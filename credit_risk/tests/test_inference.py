import pytest
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from credit_risk.api_handler import validate_input, REQUIRED_FIELDS


@pytest.fixture
def valid_application():
    return {
        "annual_income": 75000, "employment_length": 5, "home_ownership": "RENT",
        "loan_amount": 15000, "interest_rate": 12.5, "loan_term": 36,
        "credit_score": 720, "dti_ratio": 18.5, "num_credit_lines": 8,
        "revolving_utilization": 0.35, "delinquencies_2yr": 0, "public_records": 0,
        "total_accounts": 12, "months_since_last_delinq": -1, "purpose": "debt_consolidation",
    }


def test_valid_input(valid_application):
    errors = validate_input(valid_application)
    assert errors == []


def test_missing_fields():
    errors = validate_input({"annual_income": 50000})
    assert len(errors) > 0
    assert any("Missing" in e for e in errors)


def test_invalid_credit_score(valid_application):
    valid_application["credit_score"] = 200
    errors = validate_input(valid_application)
    assert any("credit_score" in e for e in errors)


def test_invalid_home_ownership(valid_application):
    valid_application["home_ownership"] = "UNKNOWN"
    errors = validate_input(valid_application)
    assert any("home_ownership" in e for e in errors)

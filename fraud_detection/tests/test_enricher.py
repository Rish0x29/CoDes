import pytest
import sys, os
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


def test_enrich_transaction():
    with patch("fraud_detection.enricher.get_user_profile", return_value={}), \
         patch("fraud_detection.enricher.compute_velocity_features", return_value={
             "txn_count_1h": 2, "txn_count_24h": 5, "avg_amount_30d": 100.0}):
        from fraud_detection.enricher import enrich_transaction
        txn = {
            "transaction_id": "TXN-001", "customer_id": "CUST-001",
            "amount": 150.0, "merchant_category": "retail",
            "card_present": 1, "international": 0,
            "distance_from_home": 5.0, "distance_from_last_txn": 3.0,
        }
        enriched = enrich_transaction(txn)
        assert "amount_vs_avg" in enriched
        assert "velocity_1h" in enriched
        assert "is_night" in enriched
        assert enriched["amount_vs_avg"] == 1.5


def test_simulator_generates_legit():
    from fraud_detection.simulator import generate_legit_transaction
    txn = generate_legit_transaction("CUST-001")
    assert txn["customer_id"] == "CUST-001"
    assert "amount" in txn
    assert "merchant_category" in txn


def test_simulator_generates_fraud():
    from fraud_detection.simulator import generate_fraud_transaction
    txn = generate_fraud_transaction("CUST-001")
    assert txn["customer_id"] == "CUST-001"
    assert txn["merchant_category"] in ["online", "electronics", "jewelry", "travel", "wire_transfer"]

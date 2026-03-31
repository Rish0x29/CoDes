import pytest
import sys, os
import json
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from data_lake.ingestion.validator import detect_file_type, _is_numeric


def test_detect_file_type():
    assert detect_file_type("raw/transactions_2024.csv") == "transactions"
    assert detect_file_type("raw/customers_export.csv") == "customers"
    assert detect_file_type("raw/products_catalog.csv") == "products"
    assert detect_file_type("raw/unknown_data.csv") == "unknown"


def test_is_numeric():
    assert _is_numeric("123.45") is True
    assert _is_numeric("1,000") is True
    assert _is_numeric("abc") is False
    assert _is_numeric("") is False

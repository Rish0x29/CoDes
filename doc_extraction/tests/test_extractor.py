import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from doc_extraction.extractor import _get_text, _extract_key_value_pairs


def test_get_text_from_block():
    block = {"Text": "Hello World"}
    assert _get_text(block, {}) == "Hello World"


def test_get_text_from_children():
    block_map = {
        "child1": {"BlockType": "WORD", "Text": "Hello"},
        "child2": {"BlockType": "WORD", "Text": "World"},
    }
    block = {"Relationships": [{"Type": "CHILD", "Ids": ["child1", "child2"]}]}
    assert _get_text(block, block_map) == "Hello World"


def test_extract_kv_pairs():
    blocks = [
        {
            "Id": "key1", "BlockType": "KEY_VALUE_SET", "EntityTypes": ["KEY"],
            "Text": "Name", "Confidence": 98.0,
            "Relationships": [{"Type": "VALUE", "Ids": ["val1"]}]
        },
        {
            "Id": "val1", "BlockType": "KEY_VALUE_SET", "EntityTypes": ["VALUE"],
            "Text": "John Doe", "Confidence": 95.0,
            "Relationships": []
        },
    ]
    block_map = {b["Id"]: b for b in blocks}
    pairs = _extract_key_value_pairs(blocks, block_map)
    assert len(pairs) == 1
    assert pairs[0]["key"] == "Name"
    assert pairs[0]["value"] == "John Doe"

"""Textract extraction Lambda - extract forms, tables, and text from documents."""

import os
import json
import logging
from typing import Optional

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

textract = boto3.client("textract", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def extract_document(bucket: str, key: str, feature_types: list = None) -> dict:
    """
    Extract structured data from a document using Textract.

    Parameters
    ----------
    bucket : str
        S3 bucket name.
    key : str
        S3 object key.
    feature_types : list
        Textract features: ["TABLES", "FORMS", "QUERIES", "SIGNATURES"]

    Returns
    -------
    dict
        Extracted text, tables, key-value pairs, and metadata.
    """
    if feature_types is None:
        feature_types = ["TABLES", "FORMS"]

    response = textract.analyze_document(
        Document={"S3Object": {"Bucket": bucket, "Name": key}},
        FeatureTypes=feature_types,
    )

    blocks = response.get("Blocks", [])
    block_map = {b["Id"]: b for b in blocks}

    # Extract text lines
    lines = []
    for block in blocks:
        if block["BlockType"] == "LINE":
            lines.append({
                "text": block["Text"],
                "confidence": round(block["Confidence"], 2),
                "page": block.get("Page", 1),
            })

    # Extract key-value pairs (forms)
    key_value_pairs = _extract_key_value_pairs(blocks, block_map)

    # Extract tables
    tables = _extract_tables(blocks, block_map)

    # Page count
    pages = set(b.get("Page", 1) for b in blocks if b["BlockType"] == "PAGE")

    return {
        "page_count": len(pages) if pages else 1,
        "line_count": len(lines),
        "lines": lines,
        "key_value_pairs": key_value_pairs,
        "tables": tables,
        "table_count": len(tables),
        "form_field_count": len(key_value_pairs),
    }


def _extract_key_value_pairs(blocks: list, block_map: dict) -> list:
    """Extract form key-value pairs."""
    pairs = []
    for block in blocks:
        if block["BlockType"] == "KEY_VALUE_SET" and "KEY" in block.get("EntityTypes", []):
            key_text = _get_text(block, block_map)
            value_text = ""
            for rel in block.get("Relationships", []):
                if rel["Type"] == "VALUE":
                    for value_id in rel["Ids"]:
                        value_block = block_map.get(value_id, {})
                        value_text = _get_text(value_block, block_map)

            if key_text:
                pairs.append({
                    "key": key_text.strip(),
                    "value": value_text.strip(),
                    "confidence": round(block.get("Confidence", 0), 2),
                })

    return pairs


def _extract_tables(blocks: list, block_map: dict) -> list:
    """Extract table data."""
    tables = []
    for block in blocks:
        if block["BlockType"] == "TABLE":
            rows = {}
            for rel in block.get("Relationships", []):
                if rel["Type"] == "CHILD":
                    for cell_id in rel["Ids"]:
                        cell = block_map.get(cell_id, {})
                        if cell["BlockType"] == "CELL":
                            row_idx = cell.get("RowIndex", 0)
                            col_idx = cell.get("ColumnIndex", 0)
                            cell_text = _get_text(cell, block_map)
                            if row_idx not in rows:
                                rows[row_idx] = {}
                            rows[row_idx][col_idx] = {
                                "text": cell_text,
                                "confidence": round(cell.get("Confidence", 0), 2),
                            }

            # Convert to list of lists
            if rows:
                max_row = max(rows.keys())
                max_col = max(max(r.keys()) for r in rows.values())
                table_data = []
                for r in range(1, max_row + 1):
                    row_data = []
                    for c in range(1, max_col + 1):
                        cell_data = rows.get(r, {}).get(c, {"text": "", "confidence": 0})
                        row_data.append(cell_data["text"])
                    table_data.append(row_data)

                tables.append({
                    "rows": len(table_data),
                    "columns": max_col,
                    "data": table_data,
                    "page": block.get("Page", 1),
                })

    return tables


def _get_text(block: dict, block_map: dict) -> str:
    """Get text from a block and its children."""
    if "Text" in block:
        return block["Text"]

    text_parts = []
    for rel in block.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for child_id in rel["Ids"]:
                child = block_map.get(child_id, {})
                if child.get("BlockType") == "WORD":
                    text_parts.append(child.get("Text", ""))
    return " ".join(text_parts)


def handler(event, context):
    """Lambda handler for document extraction."""
    bucket = event.get("bucket")
    key = event.get("key")
    features = event.get("features", ["TABLES", "FORMS"])

    if not bucket or not key:
        return {"error": "bucket and key required"}

    result = extract_document(bucket, key, features)
    result["bucket"] = bucket
    result["key"] = key

    return result

"""Schema validation Lambda for incoming data files."""

import os
import json
import logging
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

SCHEMAS = {
    "transactions": {
        "required_columns": ["transaction_id", "customer_id", "amount", "timestamp", "category"],
        "column_types": {"amount": "numeric", "timestamp": "datetime"},
    },
    "customers": {
        "required_columns": ["customer_id", "name", "email", "created_at"],
        "column_types": {"created_at": "datetime"},
    },
    "products": {
        "required_columns": ["product_id", "name", "price", "category"],
        "column_types": {"price": "numeric"},
    },
}


def detect_file_type(key: str) -> str:
    key_lower = key.lower()
    for schema_name in SCHEMAS:
        if schema_name in key_lower:
            return schema_name
    return "unknown"


def validate_csv_schema(bucket: str, key: str, schema_name: str) -> dict:
    import csv
    import io

    obj = s3.get_object(Bucket=bucket, Key=key)
    content = obj["Body"].read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []

    schema = SCHEMAS.get(schema_name, {})
    required = schema.get("required_columns", [])

    errors = []
    warnings = []

    # Check required columns
    missing = [col for col in required if col not in headers]
    if missing:
        errors.append(f"Missing required columns: {missing}")

    # Check for empty file
    rows = list(reader)
    if len(rows) == 0:
        errors.append("File is empty (no data rows)")

    # Check column types on sample
    type_checks = schema.get("column_types", {})
    for col, expected_type in type_checks.items():
        if col in headers:
            sample = [r[col] for r in rows[:100] if r.get(col)]
            if expected_type == "numeric":
                non_numeric = [v for v in sample if not _is_numeric(v)]
                if non_numeric:
                    warnings.append(f"Column '{col}' has {len(non_numeric)} non-numeric values in first 100 rows")

    # Check for duplicate rows
    if rows:
        id_col = required[0] if required else None
        if id_col and id_col in headers:
            ids = [r.get(id_col) for r in rows]
            dupes = len(ids) - len(set(ids))
            if dupes > 0:
                warnings.append(f"{dupes} duplicate {id_col} values found")

    return {
        "valid": len(errors) == 0,
        "file_type": schema_name,
        "row_count": len(rows),
        "column_count": len(headers),
        "columns": headers,
        "errors": errors,
        "warnings": warnings,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }


def _is_numeric(value: str) -> bool:
    try:
        float(value.replace(",", ""))
        return True
    except (ValueError, AttributeError):
        return False


def handler(event, context):
    """Lambda handler for S3 event-triggered schema validation."""
    results = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        logger.info(f"Validating {bucket}/{key}")

        file_type = detect_file_type(key)
        if file_type == "unknown":
            results.append({"key": key, "status": "skipped", "reason": "Unknown file type"})
            continue

        if not key.lower().endswith(".csv"):
            results.append({"key": key, "status": "skipped", "reason": "Not a CSV file"})
            continue

        result = validate_csv_schema(bucket, key, file_type)
        result["key"] = key

        if result["valid"]:
            logger.info(f"VALID: {key} ({result['row_count']} rows)")
        else:
            logger.error(f"INVALID: {key} - Errors: {result['errors']}")

        results.append(result)

    return {"statusCode": 200, "body": json.dumps({"validations": results})}

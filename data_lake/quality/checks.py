"""Data quality checks using Great Expectations patterns."""

import os
import json
import logging
from datetime import datetime, timezone

import boto3
import pandas as pd

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
sns = boto3.client("sns")
SNS_TOPIC = os.environ.get("SNS_TOPIC_ARN", "")


class DataQualityChecker:
    def __init__(self):
        self.results = []

    def expect_column_values_to_not_be_null(self, df: pd.DataFrame, column: str, threshold: float = 0.95):
        if column not in df.columns:
            self.results.append({"check": f"not_null:{column}", "passed": False, "reason": "Column missing"})
            return False
        non_null_pct = df[column].notna().mean()
        passed = non_null_pct >= threshold
        self.results.append({
            "check": f"not_null:{column}", "passed": passed,
            "actual": round(non_null_pct, 4), "threshold": threshold,
        })
        return passed

    def expect_column_values_to_be_unique(self, df: pd.DataFrame, column: str, threshold: float = 0.99):
        if column not in df.columns:
            self.results.append({"check": f"unique:{column}", "passed": False, "reason": "Column missing"})
            return False
        unique_pct = df[column].nunique() / len(df) if len(df) > 0 else 1.0
        passed = unique_pct >= threshold
        self.results.append({
            "check": f"unique:{column}", "passed": passed,
            "actual": round(unique_pct, 4), "threshold": threshold,
        })
        return passed

    def expect_column_values_to_be_between(self, df: pd.DataFrame, column: str, min_val, max_val):
        if column not in df.columns:
            self.results.append({"check": f"between:{column}", "passed": False, "reason": "Column missing"})
            return False
        valid = df[column].between(min_val, max_val)
        pct_valid = valid.mean()
        passed = pct_valid >= 0.99
        self.results.append({
            "check": f"between:{column}", "passed": passed,
            "actual_valid_pct": round(pct_valid, 4), "range": [min_val, max_val],
        })
        return passed

    def expect_row_count_to_be_between(self, df: pd.DataFrame, min_count: int, max_count: int):
        count = len(df)
        passed = min_count <= count <= max_count
        self.results.append({
            "check": "row_count", "passed": passed,
            "actual": count, "range": [min_count, max_count],
        })
        return passed

    def expect_column_values_to_be_in_set(self, df: pd.DataFrame, column: str, value_set: set):
        if column not in df.columns:
            self.results.append({"check": f"in_set:{column}", "passed": False, "reason": "Column missing"})
            return False
        invalid = ~df[column].isin(value_set)
        pct_valid = 1 - invalid.mean()
        passed = pct_valid >= 0.99
        self.results.append({
            "check": f"in_set:{column}", "passed": passed,
            "actual_valid_pct": round(pct_valid, 4),
        })
        return passed

    def summary(self) -> dict:
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        return {
            "total_checks": total, "passed": passed, "failed": total - passed,
            "pass_rate": round(passed / total, 4) if total > 0 else 1.0,
            "all_passed": passed == total, "checks": self.results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


QUALITY_SUITES = {
    "transactions": lambda checker, df: [
        checker.expect_column_values_to_not_be_null(df, "transaction_id"),
        checker.expect_column_values_to_not_be_null(df, "amount"),
        checker.expect_column_values_to_be_unique(df, "transaction_id"),
        checker.expect_column_values_to_be_between(df, "amount", 0.01, 1000000),
        checker.expect_row_count_to_be_between(df, 1, 10000000),
    ],
    "customers": lambda checker, df: [
        checker.expect_column_values_to_not_be_null(df, "customer_id"),
        checker.expect_column_values_to_not_be_null(df, "email"),
        checker.expect_column_values_to_be_unique(df, "customer_id"),
        checker.expect_column_values_to_be_unique(df, "email", threshold=0.95),
    ],
    "products": lambda checker, df: [
        checker.expect_column_values_to_not_be_null(df, "product_id"),
        checker.expect_column_values_to_not_be_null(df, "price"),
        checker.expect_column_values_to_be_between(df, "price", 0.01, 100000),
    ],
}


def run_quality_checks(bucket: str, key: str, data_type: str) -> dict:
    obj = s3.get_object(Bucket=bucket, Key=key)
    if key.endswith(".parquet"):
        df = pd.read_parquet(obj["Body"])
    else:
        df = pd.read_csv(obj["Body"])

    checker = DataQualityChecker()
    suite = QUALITY_SUITES.get(data_type)
    if suite:
        suite(checker, df)
    else:
        checker.expect_row_count_to_be_between(df, 1, 10000000)

    return checker.summary()


def handler(event, context):
    """Lambda handler for quality checks in Step Functions."""
    bucket = event.get("bucket")
    key = event.get("key")
    data_type = event.get("data_type", "unknown")

    result = run_quality_checks(bucket, key, data_type)

    if not result["all_passed"] and SNS_TOPIC:
        sns.publish(
            TopicArn=SNS_TOPIC,
            Subject=f"Data Quality FAILED: {data_type}",
            Message=json.dumps(result, indent=2),
        )

    return result

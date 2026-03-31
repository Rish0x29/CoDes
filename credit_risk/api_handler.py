"""Lambda wrapper for API Gateway - Credit Risk Scoring API."""

import os
import json
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENDPOINT_NAME = os.environ.get("SAGEMAKER_ENDPOINT", "credit-risk-endpoint")
sagemaker_runtime = boto3.client("sagemaker-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))

REQUIRED_FIELDS = [
    "annual_income", "employment_length", "home_ownership", "loan_amount",
    "interest_rate", "loan_term", "credit_score", "dti_ratio",
    "num_credit_lines", "revolving_utilization", "delinquencies_2yr",
    "public_records", "total_accounts", "months_since_last_delinq", "purpose",
]

VALID_HOME_OWNERSHIP = ["RENT", "OWN", "MORTGAGE"]
VALID_PURPOSES = ["debt_consolidation", "credit_card", "home_improvement",
                   "major_purchase", "medical", "car", "small_business", "other"]


def validate_input(data: dict) -> list:
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if "annual_income" in data and (data["annual_income"] < 0 or data["annual_income"] > 10000000):
        errors.append("annual_income must be between 0 and 10,000,000")
    if "credit_score" in data and (data["credit_score"] < 300 or data["credit_score"] > 850):
        errors.append("credit_score must be between 300 and 850")
    if "loan_amount" in data and data["loan_amount"] <= 0:
        errors.append("loan_amount must be positive")
    if "home_ownership" in data and data["home_ownership"] not in VALID_HOME_OWNERSHIP:
        errors.append(f"home_ownership must be one of: {VALID_HOME_OWNERSHIP}")
    if "purpose" in data and data["purpose"] not in VALID_PURPOSES:
        errors.append(f"purpose must be one of: {VALID_PURPOSES}")
    if "dti_ratio" in data and (data["dti_ratio"] < 0 or data["dti_ratio"] > 100):
        errors.append("dti_ratio must be between 0 and 100")

    return errors


def handler(event, context):
    """API Gateway Lambda handler."""
    try:
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", event)

        if isinstance(body, list):
            applications = body
        else:
            applications = [body]

        all_errors = []
        for i, app in enumerate(applications):
            errors = validate_input(app)
            if errors:
                all_errors.extend([f"Application {i}: {e}" for e in errors])

        if all_errors:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"errors": all_errors}),
            }

        response = sagemaker_runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType="application/json",
            Body=json.dumps(applications),
        )

        result = json.loads(response["Body"].read().decode("utf-8"))

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps(result),
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Internal server error"}),
        }

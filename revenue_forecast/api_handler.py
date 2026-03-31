"""Lambda API handler for revenue forecasting."""

import os
import json
import logging
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENDPOINT_NAME = os.environ.get("SAGEMAKER_ENDPOINT", "revenue-forecast-endpoint")
REGION = os.environ.get("AWS_REGION", "us-east-1")
sagemaker = boto3.client("sagemaker-runtime", region_name=REGION)


def invoke_forecast(series_data: dict, prediction_length: int = 30,
                    num_samples: int = 100) -> dict:
    """Call SageMaker DeepAR endpoint for forecast."""
    request = {
        "instances": [
            {
                "start": series_data["start"],
                "target": series_data["target"],
            }
        ],
        "configuration": {
            "num_samples": num_samples,
            "output_types": ["quantiles", "mean"],
            "quantiles": ["0.1", "0.5", "0.9"],
        },
    }

    response = sagemaker.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="application/json",
        Body=json.dumps(request),
    )

    result = json.loads(response["Body"].read().decode("utf-8"))
    prediction = result["predictions"][0]

    return {
        "mean": prediction.get("mean", []),
        "quantile_10": prediction.get("quantiles", {}).get("0.1", []),
        "quantile_50": prediction.get("quantiles", {}).get("0.5", []),
        "quantile_90": prediction.get("quantiles", {}).get("0.9", []),
        "prediction_length": len(prediction.get("mean", [])),
    }


def handler(event, context):
    """API Gateway handler."""
    try:
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", event)

        series_data = body.get("series", {})
        prediction_length = body.get("prediction_length", 30)

        if not series_data.get("target"):
            return _response(400, {"error": "Series data with 'start' and 'target' required"})

        forecast = invoke_forecast(series_data, prediction_length)

        return _response(200, {
            "forecast": forecast,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return _response(500, {"error": "Internal server error"})


def _response(code: int, body: dict) -> dict:
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body),
    }

"""Automated retraining pipeline triggered by EventBridge."""

import os
import json
import logging
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "us-east-1")
ROLE_ARN = os.environ.get("SAGEMAKER_ROLE_ARN", "")
TRAIN_S3 = os.environ.get("TRAIN_S3_URI", "")
TEST_S3 = os.environ.get("TEST_S3_URI", "")
OUTPUT_S3 = os.environ.get("OUTPUT_S3_URI", "")
ENDPOINT_NAME = os.environ.get("SAGEMAKER_ENDPOINT", "revenue-forecast-endpoint")

sm = boto3.client("sagemaker", region_name=REGION)


def handler(event, context):
    """EventBridge-triggered retraining handler."""
    from revenue_forecast.train import get_deepar_image_uri

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    job_name = f"revenue-forecast-retrain-{timestamp}"
    image_uri = get_deepar_image_uri(REGION)

    logger.info(f"Starting retraining job: {job_name}")

    sm.create_training_job(
        TrainingJobName=job_name,
        AlgorithmSpecification={
            "TrainingImage": image_uri,
            "TrainingInputMode": "File",
        },
        RoleArn=ROLE_ARN,
        InputDataConfig=[
            {"ChannelName": "train", "DataSource": {"S3DataSource": {
                "S3DataType": "S3Prefix", "S3Uri": TRAIN_S3, "S3DataDistributionType": "FullyReplicated"}}},
            {"ChannelName": "test", "DataSource": {"S3DataSource": {
                "S3DataType": "S3Prefix", "S3Uri": TEST_S3, "S3DataDistributionType": "FullyReplicated"}}},
        ],
        OutputDataConfig={"S3OutputPath": OUTPUT_S3},
        ResourceConfig={
            "InstanceType": "ml.m5.large", "InstanceCount": 1, "VolumeSizeInGB": 10,
        },
        StoppingCondition={"MaxRuntimeInSeconds": 3600},
        HyperParameters={
            "time_freq": "D", "prediction_length": "30", "context_length": "90",
            "num_cells": "40", "num_layers": "2", "epochs": "100",
            "mini_batch_size": "32", "learning_rate": "0.001", "likelihood": "gaussian",
        },
    )

    return {"statusCode": 200, "body": json.dumps({"job_name": job_name})}

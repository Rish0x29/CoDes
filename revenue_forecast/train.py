"""SageMaker training setup for DeepAR revenue forecasting."""

import os
import json
import logging
import boto3
import sagemaker
from sagemaker.estimator import Estimator

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_deepar_image_uri(region: str = "us-east-1") -> str:
    """Get DeepAR container image URI for the region."""
    account_map = {
        "us-east-1": "522234722520", "us-east-2": "566113047672",
        "us-west-1": "632365934929", "us-west-2": "156387875391",
        "eu-west-1": "224300973850", "eu-central-1": "495149712605",
        "ap-northeast-1": "633353088612", "ap-southeast-1": "475088953585",
    }
    account = account_map.get(region, "522234722520")
    return f"{account}.dkr.ecr.{region}.amazonaws.com/forecasting-deepar:latest"


def create_training_job(
    role_arn: str,
    train_s3_uri: str,
    test_s3_uri: str,
    output_s3_uri: str,
    region: str = "us-east-1",
    prediction_length: int = 30,
    context_length: int = 90,
    num_cells: int = 40,
    num_layers: int = 2,
    epochs: int = 100,
    mini_batch_size: int = 32,
    learning_rate: float = 0.001,
    instance_type: str = "ml.m5.large",
) -> dict:
    """Create and run a SageMaker DeepAR training job."""
    image_uri = get_deepar_image_uri(region)

    hyperparameters = {
        "time_freq": "D",
        "prediction_length": str(prediction_length),
        "context_length": str(context_length),
        "num_cells": str(num_cells),
        "num_layers": str(num_layers),
        "epochs": str(epochs),
        "mini_batch_size": str(mini_batch_size),
        "learning_rate": str(learning_rate),
        "likelihood": "gaussian",
        "num_eval_samples": "100",
    }

    sess = sagemaker.Session(boto_session=boto3.Session(region_name=region))

    estimator = Estimator(
        image_uri=image_uri,
        role=role_arn,
        instance_count=1,
        instance_type=instance_type,
        output_path=output_s3_uri,
        sagemaker_session=sess,
        hyperparameters=hyperparameters,
    )

    data_channels = {
        "train": sagemaker.inputs.TrainingInput(train_s3_uri, content_type="application/jsonlines"),
        "test": sagemaker.inputs.TrainingInput(test_s3_uri, content_type="application/jsonlines"),
    }

    logger.info("Starting DeepAR training job...")
    estimator.fit(data_channels, wait=True)
    logger.info(f"Training complete. Model: {estimator.model_data}")

    return {
        "model_data": estimator.model_data,
        "training_job_name": estimator.latest_training_job.name,
        "hyperparameters": hyperparameters,
    }


def deploy_endpoint(
    model_data: str,
    role_arn: str,
    region: str = "us-east-1",
    endpoint_name: str = "revenue-forecast-endpoint",
    instance_type: str = "ml.m5.large",
):
    """Deploy trained model as SageMaker endpoint."""
    image_uri = get_deepar_image_uri(region)
    sess = sagemaker.Session(boto_session=boto3.Session(region_name=region))

    from sagemaker.model import Model
    model = Model(
        model_data=model_data, image_uri=image_uri,
        role=role_arn, sagemaker_session=sess,
    )

    predictor = model.deploy(
        initial_instance_count=1,
        instance_type=instance_type,
        endpoint_name=endpoint_name,
    )

    logger.info(f"Endpoint deployed: {endpoint_name}")
    return predictor


if __name__ == "__main__":
    from revenue_forecast.data_prep import generate_revenue_data, to_deepar_format, save_deepar_jsonlines, split_train_test

    series = generate_revenue_data(n_series=5, n_days=730)
    train_series, test_series = split_train_test(series, prediction_length=30)

    train_records = to_deepar_format(train_series)
    test_records = to_deepar_format(series)  # Full series for test

    os.makedirs("data", exist_ok=True)
    save_deepar_jsonlines(train_records, "data/train.jsonl")
    save_deepar_jsonlines(test_records, "data/test.jsonl")
    print("Training data prepared. Upload to S3 and run create_training_job().")

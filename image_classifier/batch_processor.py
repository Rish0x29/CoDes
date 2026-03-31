"""Batch image classification processor."""

import os
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3

from image_classifier.handler import classify_image

logger = logging.getLogger(__name__)

s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def list_images(bucket: str, prefix: str, extensions: tuple = (".jpg", ".jpeg", ".png", ".gif", ".bmp")) -> list:
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(extensions):
                keys.append(key)
    return keys


def process_single_image(bucket: str, key: str, table_name: str) -> dict:
    try:
        result = classify_image(s3_bucket=bucket, s3_key=key)
        result["s3_key"] = key
        result["s3_bucket"] = bucket

        table = dynamodb.Table(table_name)
        table.put_item(Item={
            "classification_id": key,
            "s3_key": key,
            "label_count": result["label_count"],
            "face_count": result["face_count"],
            "is_safe": result["is_safe"],
            "top_labels": json.dumps(result["labels"][:5]),
            "full_result": json.dumps(result),
        })
        return {"key": key, "status": "success", "labels": len(result["labels"])}
    except Exception as e:
        logger.error(f"Error processing {key}: {e}")
        return {"key": key, "status": "error", "error": str(e)}


def batch_classify(bucket: str, prefix: str, table_name: str, max_workers: int = 5) -> dict:
    keys = list_images(bucket, prefix)
    logger.info(f"Found {len(keys)} images to process")

    results = {"total": len(keys), "success": 0, "errors": 0, "details": []}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_single_image, bucket, key, table_name): key
            for key in keys
        }
        for future in as_completed(futures):
            result = future.result()
            results["details"].append(result)
            if result["status"] == "success":
                results["success"] += 1
            else:
                results["errors"] += 1

    logger.info(f"Batch complete: {results['success']} success, {results['errors']} errors")
    return results


def handler(event, context):
    """Lambda handler for batch processing."""
    bucket = event.get("bucket", os.environ.get("S3_BUCKET", "image-classifier-uploads"))
    prefix = event.get("prefix", "batch/")
    table = event.get("table", os.environ.get("DYNAMODB_TABLE", "image-classifications"))
    max_workers = event.get("max_workers", 5)

    result = batch_classify(bucket, prefix, table, max_workers)
    return {"statusCode": 200, "body": json.dumps(result)}

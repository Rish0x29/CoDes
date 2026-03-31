"""Core Lambda handler for image classification using AWS Rekognition."""

import os
import json
import base64
import logging
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BUCKET = os.environ.get("S3_BUCKET", "image-classifier-uploads")
TABLE = os.environ.get("DYNAMODB_TABLE", "image-classifications")
REGION = os.environ.get("AWS_REGION", "us-east-1")

s3 = boto3.client("s3", region_name=REGION)
rekognition = boto3.client("rekognition", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)


def classify_image(image_bytes: bytes = None, s3_bucket: str = None, s3_key: str = None,
                   min_confidence: float = 70.0) -> dict:
    if image_bytes:
        image_param = {"Bytes": image_bytes}
    elif s3_bucket and s3_key:
        image_param = {"S3Object": {"Bucket": s3_bucket, "Name": s3_key}}
    else:
        raise ValueError("Provide either image_bytes or s3_bucket+s3_key")

    # Detect labels
    labels_response = rekognition.detect_labels(
        Image=image_param, MaxLabels=20, MinConfidence=min_confidence
    )
    labels = [
        {
            "name": label["Name"],
            "confidence": round(label["Confidence"], 2),
            "parents": [p["Name"] for p in label.get("Parents", [])],
            "categories": [c["Name"] for c in label.get("Categories", [])],
            "instances": [
                {
                    "bounding_box": inst["BoundingBox"],
                    "confidence": round(inst["Confidence"], 2),
                }
                for inst in label.get("Instances", [])
            ],
        }
        for label in labels_response.get("Labels", [])
    ]

    # Detect moderation labels
    moderation_response = rekognition.detect_moderation_labels(
        Image=image_param, MinConfidence=min_confidence
    )
    moderation = [
        {
            "name": mod["Name"],
            "confidence": round(mod["Confidence"], 2),
            "parent": mod.get("ParentName", ""),
        }
        for mod in moderation_response.get("ModerationLabels", [])
    ]

    # Detect faces
    faces_response = rekognition.detect_faces(Image=image_param, Attributes=["ALL"])
    faces = [
        {
            "age_range": face.get("AgeRange", {}),
            "gender": face.get("Gender", {}),
            "emotions": sorted(
                [{"type": e["Type"], "confidence": round(e["Confidence"], 2)}
                 for e in face.get("Emotions", [])],
                key=lambda x: x["confidence"], reverse=True,
            )[:3],
            "smile": face.get("Smile", {}),
            "eyeglasses": face.get("Eyeglasses", {}),
            "sunglasses": face.get("Sunglasses", {}),
            "bounding_box": face.get("BoundingBox", {}),
            "confidence": round(face.get("Confidence", 0), 2),
            "landmarks_count": len(face.get("Landmarks", [])),
            "pose": face.get("Pose", {}),
            "quality": face.get("Quality", {}),
        }
        for face in faces_response.get("FaceDetails", [])
    ]

    return {
        "labels": labels,
        "label_count": len(labels),
        "moderation_labels": moderation,
        "is_safe": len(moderation) == 0,
        "faces": faces,
        "face_count": len(faces),
    }


def save_result(classification_id: str, result: dict, s3_key: str = ""):
    table = dynamodb.Table(TABLE)
    table.put_item(Item={
        "classification_id": classification_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "s3_key": s3_key,
        "label_count": result["label_count"],
        "face_count": result["face_count"],
        "is_safe": result["is_safe"],
        "top_labels": json.dumps(result["labels"][:5]),
        "full_result": json.dumps(result),
    })


def handler(event, context):
    """API Gateway Lambda handler for image classification."""
    try:
        http_method = event.get("httpMethod", event.get("requestContext", {}).get("http", {}).get("method", "POST"))

        if http_method == "GET":
            path_params = event.get("pathParameters", {}) or {}
            classification_id = path_params.get("id")
            if not classification_id:
                return _response(400, {"error": "Missing classification id"})

            table = dynamodb.Table(TABLE)
            result = table.get_item(Key={"classification_id": classification_id})
            item = result.get("Item")
            if not item:
                return _response(404, {"error": "Not found"})

            item["full_result"] = json.loads(item.get("full_result", "{}"))
            item["top_labels"] = json.loads(item.get("top_labels", "[]"))
            return _response(200, item)

        # POST - classify image
        body = event.get("body", "")
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8")

        if isinstance(body, str):
            body = json.loads(body)

        classification_id = str(uuid.uuid4())

        if "image_base64" in body:
            image_bytes = base64.b64decode(body["image_base64"])
            s3_key = f"uploads/{classification_id}.jpg"
            s3.put_object(Bucket=BUCKET, Key=s3_key, Body=image_bytes, ContentType="image/jpeg")
            result = classify_image(image_bytes=image_bytes, min_confidence=body.get("min_confidence", 70.0))

        elif "s3_key" in body:
            s3_key = body["s3_key"]
            s3_bucket = body.get("s3_bucket", BUCKET)
            result = classify_image(s3_bucket=s3_bucket, s3_key=s3_key, min_confidence=body.get("min_confidence", 70.0))

        else:
            return _response(400, {"error": "Provide image_base64 or s3_key"})

        result["classification_id"] = classification_id
        result["s3_key"] = s3_key

        save_result(classification_id, result, s3_key)

        return _response(200, result)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return _response(500, {"error": "Internal server error"})


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body, default=str),
    }

"""Utility functions for image classification service."""

import io
import base64
import logging
from typing import Optional, Tuple

import boto3

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {"image/jpeg", "image/png", "image/gif", "image/bmp", "image/webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB - Rekognition limit for bytes
MAX_S3_IMAGE_SIZE = 15 * 1024 * 1024  # 15MB - Rekognition limit for S3


def validate_image_bytes(image_bytes: bytes) -> Tuple[bool, str]:
    if len(image_bytes) > MAX_IMAGE_SIZE:
        return False, f"Image too large: {len(image_bytes)} bytes (max {MAX_IMAGE_SIZE})"
    if len(image_bytes) < 100:
        return False, "Image too small: likely corrupt"

    # Check magic bytes
    if image_bytes[:2] == b'\xff\xd8':
        return True, "image/jpeg"
    elif image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return True, "image/png"
    elif image_bytes[:6] in (b'GIF87a', b'GIF89a'):
        return True, "image/gif"
    elif image_bytes[:2] == b'BM':
        return True, "image/bmp"
    else:
        return True, "unknown"


def decode_base64_image(base64_string: str) -> bytes:
    if "," in base64_string:
        base64_string = base64_string.split(",", 1)[1]
    return base64.b64decode(base64_string)


def upload_to_s3(image_bytes: bytes, bucket: str, key: str, content_type: str = "image/jpeg",
                 region: str = "us-east-1") -> str:
    s3 = boto3.client("s3", region_name=region)
    s3.put_object(Bucket=bucket, Key=key, Body=image_bytes, ContentType=content_type)
    return f"s3://{bucket}/{key}"


def download_from_s3(bucket: str, key: str, region: str = "us-east-1") -> bytes:
    s3 = boto3.client("s3", region_name=region)
    response = s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def format_labels_response(labels: list, top_n: int = 10) -> list:
    sorted_labels = sorted(labels, key=lambda x: x.get("confidence", 0), reverse=True)
    return sorted_labels[:top_n]


def format_bounding_box(bbox: dict, image_width: int, image_height: int) -> dict:
    return {
        "left": int(bbox.get("Left", 0) * image_width),
        "top": int(bbox.get("Top", 0) * image_height),
        "width": int(bbox.get("Width", 0) * image_width),
        "height": int(bbox.get("Height", 0) * image_height),
    }

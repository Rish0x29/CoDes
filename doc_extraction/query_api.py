"""API Lambda for querying extracted document data."""

import os
import json
import logging
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "extracted-documents")
dynamodb = boto3.resource("dynamodb", region_name=REGION)


def get_document(document_id: str) -> dict:
    table = dynamodb.Table(TABLE_NAME)
    response = table.get_item(Key={"document_id": document_id})
    item = response.get("Item")
    if item and "extraction_result" in item:
        item["extraction_result"] = json.loads(item["extraction_result"])
    return item


def list_documents(status: str = None, limit: int = 50) -> list:
    table = dynamodb.Table(TABLE_NAME)
    if status:
        response = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("status").eq(status),
            Limit=limit,
        )
    else:
        response = table.scan(Limit=limit)

    items = response.get("Items", [])
    for item in items:
        if "extraction_result" in item:
            item.pop("extraction_result")
    return items


def save_document(document_id: str, extraction_result: dict, status: str = "completed"):
    table = dynamodb.Table(TABLE_NAME)
    table.put_item(Item={
        "document_id": document_id,
        "status": status,
        "s3_key": extraction_result.get("key", ""),
        "document_type": extraction_result.get("classification", {}).get("document_type", "unknown"),
        "page_count": extraction_result.get("page_count", 0),
        "field_count": extraction_result.get("form_field_count", 0),
        "overall_confidence": str(extraction_result.get("overall_confidence", 0)),
        "needs_review": extraction_result.get("needs_review", False),
        "extraction_result": json.dumps(extraction_result, default=str),
        "processed_at": datetime.now(timezone.utc).isoformat(),
    })


def handler(event, context):
    """API Gateway handler for document queries."""
    try:
        method = event.get("httpMethod", "GET")
        path_params = event.get("pathParameters", {}) or {}

        if method == "GET" and path_params.get("id"):
            doc = get_document(path_params["id"])
            if not doc:
                return _response(404, {"error": "Document not found"})
            return _response(200, doc)

        elif method == "GET":
            qs = event.get("queryStringParameters", {}) or {}
            status = qs.get("status")
            limit = int(qs.get("limit", 50))
            docs = list_documents(status=status, limit=limit)
            return _response(200, {"documents": docs, "count": len(docs)})

        return _response(405, {"error": "Method not allowed"})

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return _response(500, {"error": "Internal server error"})


def _response(code: int, body: dict) -> dict:
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, default=str),
    }

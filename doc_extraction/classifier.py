"""Document classification Lambda - categorize documents before extraction."""

import os
import json
import logging

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

comprehend = boto3.client("comprehend", region_name=os.environ.get("AWS_REGION", "us-east-1"))
textract = boto3.client("textract", region_name=os.environ.get("AWS_REGION", "us-east-1"))
s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))

DOC_TYPES = {
    "invoice": ["invoice", "bill", "amount due", "total", "subtotal", "tax", "payment"],
    "receipt": ["receipt", "transaction", "purchased", "store", "cashier"],
    "contract": ["agreement", "contract", "parties", "terms", "conditions", "clause", "hereby"],
    "form": ["form", "application", "please fill", "name:", "address:", "date:", "signature"],
    "report": ["report", "summary", "analysis", "findings", "conclusion", "recommendation"],
    "letter": ["dear", "sincerely", "regards", "re:", "attached", "letter"],
}


def extract_text_preview(bucket: str, key: str, max_pages: int = 1) -> str:
    """Extract text from first page for classification."""
    try:
        response = textract.detect_document_text(
            Document={"S3Object": {"Bucket": bucket, "Name": key}}
        )
        text_blocks = [b["Text"] for b in response.get("Blocks", []) if b["BlockType"] == "LINE"]
        return " ".join(text_blocks[:50])
    except Exception as e:
        logger.warning(f"Textract preview failed: {e}")
        return ""


def classify_by_keywords(text: str) -> dict:
    """Classify document by keyword matching."""
    text_lower = text.lower()
    scores = {}
    for doc_type, keywords in DOC_TYPES.items():
        matches = sum(1 for kw in keywords if kw in text_lower)
        scores[doc_type] = matches / len(keywords)

    best_type = max(scores, key=scores.get) if scores else "unknown"
    confidence = scores.get(best_type, 0)

    return {
        "document_type": best_type if confidence > 0.1 else "unknown",
        "confidence": round(confidence, 4),
        "all_scores": {k: round(v, 4) for k, v in sorted(scores.items(), key=lambda x: x[1], reverse=True)},
    }


def classify_by_comprehend(text: str) -> dict:
    """Use Comprehend for additional classification signals."""
    if not text.strip():
        return {"entities": [], "key_phrases": []}

    try:
        entities_resp = comprehend.detect_entities(Text=text[:5000], LanguageCode="en")
        key_phrases_resp = comprehend.detect_key_phrases(Text=text[:5000], LanguageCode="en")

        return {
            "entities": [
                {"text": e["Text"], "type": e["Type"], "score": round(e["Score"], 4)}
                for e in entities_resp.get("Entities", [])[:10]
            ],
            "key_phrases": [
                kp["Text"] for kp in key_phrases_resp.get("KeyPhrases", [])[:10]
            ],
        }
    except Exception as e:
        logger.warning(f"Comprehend classification failed: {e}")
        return {"entities": [], "key_phrases": []}


def handler(event, context):
    """Lambda handler for document classification."""
    bucket = event.get("bucket")
    key = event.get("key")

    if not bucket or not key:
        return {"error": "bucket and key required"}

    text = extract_text_preview(bucket, key)
    keyword_result = classify_by_keywords(text)
    comprehend_result = classify_by_comprehend(text)

    return {
        "bucket": bucket,
        "key": key,
        "classification": keyword_result,
        "nlp_analysis": comprehend_result,
        "text_preview": text[:500],
    }

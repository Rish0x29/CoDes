# Automated Document Data Extraction Pipeline

Extract structured data from PDFs, invoices, and forms using AWS Textract.

## Architecture

1. **S3 Upload** -> EventBridge trigger
2. **Step Functions** orchestrates:
   - Document classification (Comprehend + keyword matching)
   - Textract extraction (tables, forms, text)
   - Post-processing (field normalization, validation)
   - Confidence routing (high -> DynamoDB, low -> SQS review queue)
3. **API Gateway** -> Query extracted data

## Features

- Automatic document type classification (invoice, receipt, contract, form)
- Table and form field extraction via Textract
- Field normalization (dates, currency, phone, email)
- Confidence-based routing (auto-approve or human review)
- REST API for querying extracted data

## Deploy

```bash
sam build && sam deploy --guided
```

## Testing

```bash
pytest doc_extraction/tests/ -v
```

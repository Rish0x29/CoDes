# Sample Documents for Testing

Upload these types of documents to the S3 bucket for testing:

1. **Invoices** - PDF invoices with line items, totals, dates
2. **Receipts** - Scanned receipts from stores
3. **Forms** - Application forms with fillable fields
4. **Contracts** - Legal agreements with signatures

## Test with AWS CLI

```bash
aws s3 cp sample_invoice.pdf s3://doc-extraction-uploads-ACCOUNT_ID/uploads/
```

The Step Functions workflow will automatically trigger.

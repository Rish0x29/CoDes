# ETL Data Lake with Automated Quality Checks

Production-grade data lake with automated ingestion, transformation, quality validation, and alerting.

## Architecture

1. **S3 Raw Zone** -> Schema validation Lambda
2. **Glue ETL** -> Clean, deduplicate, transform
3. **Quality Checks** -> Great Expectations-style validation
4. **S3 Curated Zone** -> Partitioned Parquet
5. **Step Functions** -> Orchestration with pass/fail routing
6. **SNS** -> Alert on quality failures

## Setup

```bash
pip install -r requirements.txt
sam build && sam deploy --guided
```

## Testing

```bash
pytest data_lake/tests/ -v
```

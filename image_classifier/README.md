# Serverless Image Classification Service

Image classification using AWS Rekognition with REST API and web frontend.

## Features

- Label detection with confidence scores and bounding boxes
- Content moderation (safety check)
- Face detection with age, gender, emotions, accessories
- Batch processing for S3 image folders
- Modern drag-and-drop web UI

## Deploy

```bash
sam build && sam deploy --guided
```

## API

```bash
# Classify with base64
curl -X POST https://api-url/prod/classify \
  -d '{"image_base64": "..."}'

# Get result
curl https://api-url/prod/results/{id}
```

## Testing

```bash
pytest image_classifier/tests/ -v
```

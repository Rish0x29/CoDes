# 10 AWS AI/ML/Data/Finance Projects - Master Plan

> **Constraint:** Each project must be fully shippable within **10 hours** (design through deployment).
> **Target repo:** `rish0x29/codes` | **Branch:** `claude/plan-aws-ai-projects-JkaPn`

---

## Project Overview

| # | Project | Domain | Core AWS Services | Est. Hours |
|---|---------|--------|-------------------|------------|
| 1 | Algorithmic Trading Bot | Finance / ML | Lambda, DynamoDB, EventBridge, Secrets Manager | 10 |
| 2 | Real-Time Sentiment Analysis Pipeline | NLP / Data Engineering | Kinesis, Comprehend, S3, QuickSight | 10 |
| 3 | Credit Risk Scoring API | ML / Finance | SageMaker, API Gateway, Lambda, S3 | 10 |
| 4 | Serverless Image Classification Service | Computer Vision | Rekognition, Lambda, API Gateway, S3 | 10 |
| 5 | Customer Churn Prediction Dashboard | Data Science | SageMaker, Glue, Athena, QuickSight | 10 |
| 6 | ETL Data Lake with Automated Quality Checks | Data Engineering | Glue, S3, Athena, CloudWatch, SNS | 10 |
| 7 | Fraud Detection Streaming System | ML / Finance | Kinesis, SageMaker, Lambda, SNS | 10 |
| 8 | Conversational AI Financial Advisor Chatbot | AI / Finance | Bedrock, Lex, Lambda, DynamoDB | 10 |
| 9 | Time-Series Forecasting for Revenue | Data Science / Finance | SageMaker (DeepAR), S3, Lambda, CloudWatch | 10 |
| 10 | Automated PDF/Document Data Extraction Pipeline | AI / Data Engineering | Textract, Lambda, S3, DynamoDB, Step Functions | 10 |

---

## Project 1: Algorithmic Trading Bot

**Domain:** Finance / Machine Learning
**Goal:** A fully automated trading bot that ingests market data, applies a defined strategy (moving-average crossover + RSI filter), executes paper/live trades via a brokerage API, and logs all activity.

### Architecture

```
Market Data API (Alpaca/Alpha Vantage)
        │
  EventBridge (cron: every 1 min during market hours)
        │
   Lambda: strategy_engine
   ├── Fetches OHLCV candles
   ├── Computes SMA-20/SMA-50 crossover + RSI(14)
   ├── Generates BUY / SELL / HOLD signal
   └── Executes order via Alpaca API
        │
   DynamoDB: trade_log
        │
   CloudWatch Metrics + SNS Alerts
```

### Methodology

- **Entry signal:** SMA-20 crosses above SMA-50 AND RSI(14) < 70
- **Exit signal:** SMA-20 crosses below SMA-50 OR RSI(14) > 80 OR stop-loss at -2%
- **Position sizing:** Fixed fractional (2% of portfolio per trade)
- **Universe:** Configurable list of tickers (default: top 10 S&P 500 by volume)

### Timeline (10 hours)

| Hour | Task | Deliverable |
|------|------|-------------|
| 0-1 | Design & setup | Architecture doc, AWS CDK/SAM scaffold, Alpaca API keys in Secrets Manager |
| 1-3 | Data ingestion | Lambda fetching OHLCV data, storing in DynamoDB, backfill script |
| 3-5 | Strategy engine | SMA crossover + RSI logic, signal generation, unit tests |
| 5-7 | Order execution | Alpaca integration, paper trading mode, position sizing |
| 7-8 | Monitoring & alerts | CloudWatch dashboards, SNS alerts on trades, P&L tracking |
| 8-9 | Backtesting module | Historical backtest script with performance metrics (Sharpe, max drawdown) |
| 9-10 | Integration testing & deployment | End-to-end test, deploy via SAM/CDK, push to GitHub |

### Deliverables Checklist

- [ ] `trading_bot/strategy.py` - Core strategy logic (SMA crossover + RSI)
- [ ] `trading_bot/executor.py` - Order execution via Alpaca API
- [ ] `trading_bot/data_fetcher.py` - Market data ingestion
- [ ] `trading_bot/backtest.py` - Backtesting engine with performance metrics
- [ ] `trading_bot/lambda_handler.py` - AWS Lambda entry point
- [ ] `trading_bot/template.yaml` - SAM/CDK deployment template
- [ ] `trading_bot/tests/` - Unit + integration tests
- [ ] `trading_bot/config.yaml` - Configurable tickers, thresholds, position sizing
- [ ] `trading_bot/README.md` - Setup, deployment, and usage guide
- [ ] CloudWatch dashboard JSON export
- [ ] DynamoDB trade log table schema

---

## Project 2: Real-Time Sentiment Analysis Pipeline

**Domain:** NLP / Data Engineering
**Goal:** Ingest streaming text data (tweets, news headlines, RSS feeds), perform real-time sentiment analysis, and visualize trends on a live dashboard.

### Architecture

```
Data Sources (Twitter API / NewsAPI / RSS)
        │
   Kinesis Data Stream
        │
   Lambda: sentiment_processor
   ├── AWS Comprehend (sentiment + entities)
   └── Enriched records → Kinesis Firehose
        │
   S3 (Parquet, partitioned by date/source)
        │
   Athena → QuickSight Dashboard
```

### Timeline (10 hours)

| Hour | Task | Deliverable |
|------|------|-------------|
| 0-1 | Design & setup | Architecture, IAM roles, Kinesis stream creation |
| 1-3 | Data ingestion | Producer scripts for Twitter/NewsAPI/RSS → Kinesis |
| 3-5 | Sentiment processing | Lambda consumer calling Comprehend, entity extraction |
| 5-7 | Storage & catalog | Firehose → S3 Parquet, Glue Crawler, Athena tables |
| 7-9 | Visualization | QuickSight dashboard with sentiment trends, entity word clouds |
| 9-10 | Testing & deployment | End-to-end pipeline test, deploy, push to GitHub |

### Deliverables Checklist

- [ ] `sentiment_pipeline/producer.py` - Multi-source data producer
- [ ] `sentiment_pipeline/processor.py` - Lambda sentiment processor
- [ ] `sentiment_pipeline/template.yaml` - SAM/CDK infra
- [ ] `sentiment_pipeline/glue_crawler_config.json` - Glue catalog setup
- [ ] `sentiment_pipeline/athena_queries/` - Pre-built analytical queries
- [ ] `sentiment_pipeline/dashboard_config.json` - QuickSight dashboard definition
- [ ] `sentiment_pipeline/tests/` - Unit + integration tests
- [ ] `sentiment_pipeline/README.md` - Documentation

---

## Project 3: Credit Risk Scoring API

**Domain:** Machine Learning / Finance
**Goal:** Train a credit risk model on historical loan data and deploy it as a real-time scoring API.

### Architecture

```
S3 (training data: loan history)
        │
   SageMaker Training Job (XGBoost)
        │
   SageMaker Model Registry
        │
   SageMaker Endpoint (real-time inference)
        │
   API Gateway + Lambda (REST API wrapper)
        │
   Client Applications
```

### Timeline (10 hours)

| Hour | Task | Deliverable |
|------|------|-------------|
| 0-1 | Design & data acquisition | Download Lending Club/UCI dataset, define features |
| 1-3 | Data preparation | EDA notebook, feature engineering, train/val/test split |
| 3-5 | Model training | SageMaker XGBoost training, hyperparameter tuning |
| 5-7 | Model evaluation & registry | Confusion matrix, AUC-ROC, SHAP explanations, register model |
| 7-9 | API deployment | SageMaker endpoint, API Gateway + Lambda wrapper |
| 9-10 | Testing & documentation | Load testing, push to GitHub |

### Deliverables Checklist

- [ ] `credit_risk/notebooks/eda.ipynb` - Exploratory data analysis
- [ ] `credit_risk/preprocessing.py` - Feature engineering pipeline
- [ ] `credit_risk/train.py` - SageMaker training script
- [ ] `credit_risk/inference.py` - Inference handler
- [ ] `credit_risk/api_handler.py` - Lambda API wrapper
- [ ] `credit_risk/template.yaml` - SAM/CDK deployment
- [ ] `credit_risk/tests/` - Unit + integration tests
- [ ] `credit_risk/model_card.md` - Model documentation (metrics, bias analysis)
- [ ] `credit_risk/README.md` - Full documentation

---

## Project 4: Serverless Image Classification Service

**Domain:** Computer Vision / AI
**Goal:** Upload an image, classify it using AWS Rekognition (labels, moderation, faces), and return structured results via REST API.

### Architecture

```
Client (web/mobile)
    │
API Gateway (POST /classify)
    │
Lambda: image_classifier
├── S3 (store uploaded image)
├── Rekognition: detect_labels
├── Rekognition: detect_moderation_labels
├── Rekognition: detect_faces
└── Return consolidated JSON response
    │
DynamoDB (classification log)
```

### Timeline (10 hours)

| Hour | Task | Deliverable |
|------|------|-------------|
| 0-1 | Design & setup | API contract, IAM roles, S3 bucket |
| 1-3 | Core Lambda | Image upload to S3, Rekognition calls, response formatting |
| 3-5 | Extended features | Custom labels (Rekognition Custom Labels), batch processing |
| 5-7 | API layer | API Gateway with request validation, CORS, API keys |
| 7-8 | Frontend | Simple HTML/JS upload page hosted on S3 + CloudFront |
| 8-9 | Monitoring | CloudWatch logs, latency tracking, cost alerts |
| 9-10 | Testing & deployment | Integration tests, deploy, push to GitHub |

### Deliverables Checklist

- [ ] `image_classifier/handler.py` - Core classification Lambda
- [ ] `image_classifier/batch_processor.py` - Batch classification
- [ ] `image_classifier/template.yaml` - SAM/CDK deployment
- [ ] `image_classifier/frontend/` - Static upload page (S3-hosted)
- [ ] `image_classifier/tests/` - Tests with sample images
- [ ] `image_classifier/README.md` - Documentation

---

## Project 5: Customer Churn Prediction Dashboard

**Domain:** Data Science / Business Analytics
**Goal:** Predict customer churn using historical data, deploy the model, and build an interactive dashboard for business stakeholders.

### Architecture

```
S3 (raw customer data: transactions, support tickets, usage logs)
        │
   Glue ETL Job (clean, join, feature engineer)
        │
   S3 (feature store - Parquet)
        │
   SageMaker Training (Random Forest / XGBoost)
        │
   SageMaker Batch Transform (score all customers)
        │
   Athena (query scored data)
        │
   QuickSight Dashboard
   ├── Churn risk distribution
   ├── Top risk factors (SHAP values)
   ├── Cohort analysis
   └── Retention recommendations
```

### Timeline (10 hours)

| Hour | Task | Deliverable |
|------|------|-------------|
| 0-1 | Design & data prep | Download Telco Churn dataset, schema design |
| 1-3 | Feature engineering | Glue ETL job, behavioral features, aggregations |
| 3-5 | Model development | Train/tune XGBoost, evaluate with AUC-ROC, precision-recall |
| 5-7 | Scoring pipeline | Batch transform, score entire customer base |
| 7-9 | Dashboard | QuickSight dashboard with drill-down, filters, SHAP charts |
| 9-10 | Testing & deployment | Validate predictions, deploy, push to GitHub |

### Deliverables Checklist

- [ ] `churn_prediction/glue_etl.py` - Glue ETL job script
- [ ] `churn_prediction/notebooks/eda.ipynb` - Exploratory analysis
- [ ] `churn_prediction/train.py` - SageMaker training script
- [ ] `churn_prediction/score.py` - Batch scoring script
- [ ] `churn_prediction/template.yaml` - Infrastructure template
- [ ] `churn_prediction/dashboard/` - QuickSight dashboard config
- [ ] `churn_prediction/tests/` - Validation tests
- [ ] `churn_prediction/README.md` - Documentation

---

## Project 6: ETL Data Lake with Automated Quality Checks

**Domain:** Data Engineering
**Goal:** Build a production-grade data lake with automated ingestion, transformation, quality validation, and alerting.

### Architecture

```
Data Sources (CSV/JSON/API)
        │
   S3: raw/ (landing zone)
        │
   EventBridge (S3 event trigger)
        │
   Step Functions Workflow:
   ├── Lambda: validate_schema
   ├── Glue ETL: transform + deduplicate
   ├── Lambda: data_quality_checks (Great Expectations)
   ├── Pass → S3: curated/ (Parquet, partitioned)
   └── Fail → SNS alert + S3: quarantine/
        │
   Glue Crawler → Athena (query layer)
```

### Timeline (10 hours)

| Hour | Task | Deliverable |
|------|------|-------------|
| 0-1 | Design & setup | S3 bucket structure (raw/curated/quarantine), IAM roles |
| 1-3 | Ingestion layer | S3 event triggers, schema validation Lambda |
| 3-5 | Transformation | Glue ETL jobs (cleaning, deduplication, type casting) |
| 5-7 | Quality checks | Great Expectations suite, quality Lambda, pass/fail routing |
| 7-8 | Cataloging & query | Glue Crawlers, Athena tables, sample queries |
| 8-9 | Alerting & monitoring | SNS alerts, CloudWatch dashboards, dead-letter queues |
| 9-10 | Testing & deployment | End-to-end test with sample data, deploy, push to GitHub |

### Deliverables Checklist

- [ ] `data_lake/ingestion/validator.py` - Schema validation Lambda
- [ ] `data_lake/etl/transform.py` - Glue ETL job
- [ ] `data_lake/quality/checks.py` - Great Expectations quality checks
- [ ] `data_lake/orchestration/state_machine.json` - Step Functions definition
- [ ] `data_lake/template.yaml` - Full infrastructure template
- [ ] `data_lake/sample_data/` - Test datasets
- [ ] `data_lake/tests/` - Integration tests
- [ ] `data_lake/README.md` - Documentation

---

## Project 7: Fraud Detection Streaming System

**Domain:** Machine Learning / Finance
**Goal:** Detect fraudulent transactions in real-time using a streaming ML pipeline.

### Architecture

```
Transaction Stream (simulated / Kinesis producer)
        │
   Kinesis Data Stream
        │
   Lambda: feature_enricher
   ├── Lookup user history (DynamoDB)
   ├── Compute velocity features (transactions in last 1h/24h)
   └── Enriched record → SageMaker Endpoint
        │
   SageMaker Endpoint (Isolation Forest / XGBoost anomaly model)
        │
   ├── Score > threshold → SNS Alert + DynamoDB: flagged_transactions
   └── Score < threshold → DynamoDB: approved_transactions
```

### Timeline (10 hours)

| Hour | Task | Deliverable |
|------|------|-------------|
| 0-1 | Design & data prep | Download IEEE/Kaggle fraud dataset, feature analysis |
| 1-3 | Model training | Feature engineering, train Isolation Forest + XGBoost ensemble |
| 3-5 | Streaming infra | Kinesis stream, Lambda enricher, DynamoDB user profiles |
| 5-7 | Real-time inference | SageMaker endpoint, scoring pipeline, threshold tuning |
| 7-8 | Alerting | SNS alerts, fraud dashboard, investigation queue |
| 8-9 | Transaction simulator | Realistic transaction generator with injected fraud |
| 9-10 | Testing & deployment | End-to-end stream test, deploy, push to GitHub |

### Deliverables Checklist

- [ ] `fraud_detection/train.py` - Model training script
- [ ] `fraud_detection/enricher.py` - Feature enrichment Lambda
- [ ] `fraud_detection/inference.py` - SageMaker inference handler
- [ ] `fraud_detection/simulator.py` - Transaction simulator
- [ ] `fraud_detection/template.yaml` - Infrastructure template
- [ ] `fraud_detection/tests/` - Tests
- [ ] `fraud_detection/README.md` - Documentation

---

## Project 8: Conversational AI Financial Advisor Chatbot

**Domain:** AI / Finance
**Goal:** An AI chatbot that provides financial advice, portfolio analysis, and market insights using LLMs on AWS Bedrock.

### Architecture

```
User (Web / Slack / API)
        │
   API Gateway (WebSocket)
        │
   Lambda: chat_handler
   ├── Bedrock (Claude) - conversational AI
   ├── Tool: portfolio_analyzer (Lambda)
   ├── Tool: market_data_fetcher (Lambda)
   ├── Tool: risk_calculator (Lambda)
   └── DynamoDB: conversation_history
        │
   Response → User
```

### Timeline (10 hours)

| Hour | Task | Deliverable |
|------|------|-------------|
| 0-1 | Design & setup | Bedrock access, conversation design, tool definitions |
| 1-3 | Core chatbot | Bedrock Claude integration, conversation management, DynamoDB |
| 3-5 | Financial tools | Portfolio analyzer, market data fetcher, risk calculator |
| 5-7 | Tool orchestration | Function calling with Bedrock, multi-turn context |
| 7-8 | Frontend | Simple web chat UI (React/HTML) on S3 + CloudFront |
| 8-9 | Guardrails | Content filtering, financial disclaimer injection, rate limiting |
| 9-10 | Testing & deployment | Conversation flow tests, deploy, push to GitHub |

### Deliverables Checklist

- [ ] `financial_chatbot/chat_handler.py` - Core chat Lambda
- [ ] `financial_chatbot/tools/portfolio.py` - Portfolio analysis tool
- [ ] `financial_chatbot/tools/market_data.py` - Market data tool
- [ ] `financial_chatbot/tools/risk.py` - Risk calculation tool
- [ ] `financial_chatbot/frontend/` - Web chat interface
- [ ] `financial_chatbot/template.yaml` - Infrastructure template
- [ ] `financial_chatbot/tests/` - Conversation flow tests
- [ ] `financial_chatbot/README.md` - Documentation

---

## Project 9: Time-Series Forecasting for Revenue

**Domain:** Data Science / Finance
**Goal:** Forecast future revenue using AWS SageMaker DeepAR algorithm on historical financial data, with automated retraining.

### Architecture

```
S3 (historical revenue data - JSON Lines)
        │
   SageMaker Training Job (DeepAR)
        │
   SageMaker Endpoint (real-time forecast)
        │
   Lambda: forecast_handler
   ├── API Gateway (GET /forecast?horizon=30)
   └── CloudWatch scheduled retraining trigger
        │
   S3: forecasts/ (stored predictions)
        │
   QuickSight Dashboard (actual vs predicted)
```

### Timeline (10 hours)

| Hour | Task | Deliverable |
|------|------|-------------|
| 0-1 | Design & data prep | Acquire/generate revenue dataset, DeepAR format conversion |
| 1-3 | Model training | SageMaker DeepAR training, hyperparameter tuning |
| 3-5 | Evaluation | Backtest forecasts, MAPE/RMSE metrics, confidence intervals |
| 5-7 | API deployment | SageMaker endpoint, Lambda wrapper, API Gateway |
| 7-8 | Automated retraining | EventBridge cron → SageMaker Pipeline for weekly retrain |
| 8-9 | Dashboard | QuickSight: actual vs predicted, forecast confidence bands |
| 9-10 | Testing & deployment | Accuracy validation, deploy, push to GitHub |

### Deliverables Checklist

- [ ] `revenue_forecast/data_prep.py` - Data formatting for DeepAR
- [ ] `revenue_forecast/train.py` - SageMaker training script
- [ ] `revenue_forecast/evaluate.py` - Backtesting and metrics
- [ ] `revenue_forecast/api_handler.py` - Lambda forecast API
- [ ] `revenue_forecast/retrain_pipeline.py` - Automated retraining
- [ ] `revenue_forecast/template.yaml` - Infrastructure template
- [ ] `revenue_forecast/tests/` - Tests
- [ ] `revenue_forecast/README.md` - Documentation

---

## Project 10: Automated PDF/Document Data Extraction Pipeline

**Domain:** AI / Data Engineering
**Goal:** Extract structured data from PDFs, invoices, and forms using AWS Textract, with automated processing and validation.

### Architecture

```
S3: uploads/ (PDF/image drop zone)
        │
   S3 Event → Step Functions Workflow:
   ├── Lambda: classify_document (Comprehend)
   ├── Textract: analyze_document (forms, tables, queries)
   ├── Lambda: post_processor (normalize, validate extracted fields)
   ├── Lambda: confidence_router
   │   ├── High confidence → DynamoDB: extracted_data
   │   └── Low confidence → SQS: human_review_queue
   └── SNS: completion_notification
        │
   API Gateway: GET /documents/{id} (query extracted data)
```

### Timeline (10 hours)

| Hour | Task | Deliverable |
|------|------|-------------|
| 0-1 | Design & setup | Document types, extraction schema, S3 bucket setup |
| 1-3 | Textract integration | Document analysis Lambda, form/table extraction |
| 3-5 | Post-processing | Field normalization, validation rules, confidence scoring |
| 5-7 | Orchestration | Step Functions workflow, human review queue, routing logic |
| 7-8 | Query API | API Gateway + Lambda to query extracted data from DynamoDB |
| 8-9 | Monitoring | CloudWatch metrics (documents/hour, accuracy), SNS alerts |
| 9-10 | Testing & deployment | Test with sample documents, deploy, push to GitHub |

### Deliverables Checklist

- [ ] `doc_extraction/classifier.py` - Document classification Lambda
- [ ] `doc_extraction/extractor.py` - Textract extraction Lambda
- [ ] `doc_extraction/post_processor.py` - Field normalization & validation
- [ ] `doc_extraction/query_api.py` - Document query Lambda
- [ ] `doc_extraction/state_machine.json` - Step Functions definition
- [ ] `doc_extraction/template.yaml` - Infrastructure template
- [ ] `doc_extraction/sample_docs/` - Test PDFs and images
- [ ] `doc_extraction/tests/` - Tests
- [ ] `doc_extraction/README.md` - Documentation

---

## Global Execution Timeline

```
Week 1:  [P1: Trading Bot]──────[P2: Sentiment Pipeline]──
Week 1:  ──[P3: Credit Risk]────[P4: Image Classification]
Week 2:  [P5: Churn Prediction]─[P6: Data Lake ETL]───────
Week 2:  ──[P7: Fraud Detection][P8: Financial Chatbot]───
Week 3:  [P9: Revenue Forecast]─[P10: Doc Extraction]─────
```

> Each project is 10 hours. Running 2 projects in parallel per week allows completion in ~3 weeks with buffer.

## Shared Infrastructure & Standards

### Common Tooling (setup once, reuse across all projects)

- **IaC:** AWS SAM or CDK (Python) for all deployments
- **CI/CD:** GitHub Actions workflow per project (lint → test → deploy)
- **Monitoring:** CloudWatch Logs + Metrics for every Lambda
- **Secrets:** AWS Secrets Manager for all API keys and credentials
- **Python version:** 3.11+ with `pyproject.toml` for dependency management
- **Testing:** `pytest` with minimum 80% code coverage on core logic

### Repository Structure

```
CoDes/
├── trading_bot/            # Project 1
├── sentiment_pipeline/     # Project 2
├── credit_risk/            # Project 3
├── image_classifier/       # Project 4
├── churn_prediction/       # Project 5
├── data_lake/              # Project 6
├── fraud_detection/        # Project 7
├── financial_chatbot/      # Project 8
├── revenue_forecast/       # Project 9
├── doc_extraction/         # Project 10
├── shared/                 # Shared utilities
│   ├── aws_utils.py        # Common AWS helpers
│   ├── logging_config.py   # Structured logging
│   └── test_utils.py       # Test fixtures
├── .github/
│   └── workflows/          # CI/CD per project
└── AWS_AI_PROJECTS_PLAN.md # This file
```

### Post-Project Push Workflow

After completing each project:
1. Run all tests: `pytest project_dir/tests/ -v --cov`
2. Lint check: `ruff check project_dir/`
3. Stage files: `git add project_dir/`
4. Commit: `git commit -m "feat(project_name): complete [Project Name] - [brief description]"`
5. Push: `git push -u origin claude/plan-aws-ai-projects-JkaPn`

---

## AWS Cost Considerations

| Service | Free Tier | Estimated Cost Beyond Free Tier |
|---------|-----------|--------------------------------|
| Lambda | 1M requests/month | ~$0.20/1M requests |
| SageMaker | 250 hrs t2.medium/month (first 2 months) | ~$0.05/hr (ml.t3.medium) |
| Kinesis | - | ~$0.015/shard-hour |
| DynamoDB | 25 GB + 25 WCU/RCU | ~$1.25/WCU-month |
| S3 | 5 GB | ~$0.023/GB-month |
| Bedrock | - | Pay per token (model dependent) |
| Comprehend | 50K units/month | ~$0.0001/unit |
| Textract | 1K pages/month | ~$0.0015/page |
| Rekognition | 5K images/month | ~$0.001/image |

**Estimated total for development + testing: $50-150 (using free tier aggressively)**

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| API rate limits (Alpaca, NewsAPI) | Implement exponential backoff; use caching |
| SageMaker training time exceeds budget | Use smaller datasets for dev; spot instances |
| Cold start latency on Lambda | Provisioned concurrency for critical paths |
| Data quality issues | Great Expectations checks in every pipeline |
| AWS service quotas | Request increases upfront for SageMaker endpoints |
| Cost overruns | CloudWatch billing alarms at $25, $50, $100 |

---

*Plan created: 2026-03-29*
*Ready for execution. Begin with Project 1: Algorithmic Trading Bot.*

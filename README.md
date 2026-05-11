# Bedrock Metrics POC

Playground POC that generates realistic Bedrock traffic across two use cases,
surfaces all available metrics (native CloudWatch + custom), and tears itself
down in one command.

**Goal:** understand what metrics Bedrock generates per use case and how to
advise customers on monitoring and cost control.

## Use Cases

| Use Case | Script | What it measures |
|----------|--------|-----------------|
| Multi-turn Chatbot | `use_cases/chatbot_sim.py` | Per-turn cost, session cost, context growth |
| RAG Chatbot | `use_cases/rag_chatbot.py` | Embed vs generation cost split, retrieval quality |

## Cost Estimate

| Resource | When it runs | Est. cost |
|----------|-------------|-----------|
| Claude 3 Haiku (chatbot + RAG generation) | During POC only | ~$0.01–0.05 |
| Titan Embeddings (RAG only) | During POC only | <$0.01 |
| OpenSearch Serverless | While collection is ACTIVE | ~$0.48/hr minimum |
| CloudWatch custom metrics | Per metric push | ~$0.01 |
| S3 | Duration of POC | <$0.01 |
| **Total for a 2-hr session** | | **~$5–10** |

**OpenSearch is the only meaningful cost.** The collection is created by
`setup_rag.py` and deleted by `cleanup.py`. The one-shot `run_poc.sh`
deletes it automatically.

## Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set AWS credentials
source ../Bedrock/.env   # or export AWS_* vars directly

# 3. ONE-SHOT: run everything and clean up
./run_poc.sh
```

## Manual step-by-step

```bash
# Chatbot only (no infra, ~$0.01)
python use_cases/chatbot_sim.py

# RAG setup (~5-7 min, OpenSearch billing starts)
python infrastructure/setup_rag.py
export BEDROCK_KB_ID=<id printed by setup_rag.py>

# RAG chatbot
python use_cases/rag_chatbot.py

# View metrics (wait 1-2 min for CloudWatch to ingest)
python metrics/cloudwatch_reader.py
python metrics/cost_report.py

# DESTROY EVERYTHING (do this immediately after testing)
python infrastructure/cleanup.py
```

## Metrics Architecture

```
                    ┌─────────────────────┐
                    │   AWS/Bedrock (CW)  │  ← emitted automatically
                    │  InvocationLatency  │
                    │  InputTokenCount    │
                    │  OutputTokenCount   │
                    │  ClientErrors       │
                    │  Throttled          │
                    └─────────────────────┘

                    ┌─────────────────────┐
                    │  BedrockPOC (CW)    │  ← pushed by our code
                    │  CostUSD            │
                    │  SessionCostUSD     │
                    │  RAGQueryCostUSD    │
                    │  RetrievalLatencyMs │
                    │  ChunksRetrieved    │
                    │  TopChunkScore      │
                    └─────────────────────┘
```

See `docs/metrics_guide.md` for the full customer advisory.

## File Structure

```
bedrock-metrics-poc/
├── config.py                  # Region, model IDs, pricing, tag helpers
├── requirements.txt
├── run_poc.sh                 # One-shot deploy + run + cleanup
├── use_cases/
│   ├── chatbot_sim.py         # Multi-turn chatbot simulation
│   └── rag_chatbot.py         # RAG chatbot (needs setup_rag.py first)
├── metrics/
│   ├── custom_metrics.py      # CloudWatch PutMetricData helper
│   ├── cloudwatch_reader.py   # Reads native + custom CW metrics
│   └── cost_report.py         # Per use-case cost summary
├── infrastructure/
│   ├── setup_rag.py           # Creates S3, OpenSearch, IAM, Knowledge Base
│   └── cleanup.py             # Destroys all resources
└── docs/
    └── metrics_guide.md       # Customer advisory on Bedrock metrics
```

## IAM Permissions Required

Your AWS credentials need:

```json
{
  "bedrock:InvokeModel",
  "bedrock-agent:CreateKnowledgeBase",
  "bedrock-agent:DeleteKnowledgeBase",
  "bedrock-agent:CreateDataSource",
  "bedrock-agent:DeleteDataSource",
  "bedrock-agent:StartIngestionJob",
  "bedrock-agent:GetIngestionJob",
  "bedrock-agent-runtime:Retrieve",
  "aoss:CreateCollection",
  "aoss:DeleteCollection",
  "aoss:BatchGetCollection",
  "aoss:CreateSecurityPolicy",
  "aoss:DeleteSecurityPolicy",
  "aoss:CreateAccessPolicy",
  "aoss:DeleteAccessPolicy",
  "s3:CreateBucket", "s3:DeleteBucket", "s3:PutObject",
  "s3:GetObject", "s3:ListBucket", "s3:DeleteObject",
  "iam:CreateRole", "iam:DeleteRole", "iam:PutRolePolicy",
  "iam:DeleteRolePolicy", "iam:PassRole",
  "cloudwatch:PutMetricData", "cloudwatch:GetMetricStatistics",
  "cloudwatch:ListMetrics"
}
```

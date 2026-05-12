#!/usr/bin/env bash
# ============================================================
# ONE-SHOT: deploys, runs all use cases, prints metrics, cleans up
# Cost guardrail: aborts if setup takes > 15 min (OpenSearch timeout)
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo ""
echo "============================================================"
echo "  BEDROCK METRICS POC — FULL RUN"
echo "  Est. cost: \$5-15 total | OpenSearch: \$0.48/hr"
echo "  ⚠️  cleanup.py runs automatically at the end"
echo "============================================================"
echo ""

# Install deps
pip install -r requirements.txt -q

# ── Step 1: Chatbot POC (no infra needed) ─────────────────
echo ">>> STEP 1: Chatbot simulation"
python use_cases/chatbot_sim.py

# ── Step 2: DynamoDB audit trail POC (no infra needed) ────
echo ""
echo ">>> STEP 2: DynamoDB audit trail"
python use_cases/dynamodb_logger.py

# ── Step 3: RAG infra + POC ───────────────────────────────
echo ""
echo ">>> STEP 3: RAG setup (this takes ~5-7 min, OpenSearch billing starts)"
python infrastructure/setup_rag.py

# Grab KB ID from state file
KB_ID=$(python -c "import json; print(json.load(open('infrastructure/.rag_state.json'))['kb_id'])")
export BEDROCK_KB_ID="$KB_ID"
echo "  KB ID: $KB_ID"

echo ""
echo ">>> STEP 4: RAG chatbot simulation"
python use_cases/rag_chatbot.py

# ── Step 5: Metrics report ───────────────────────────────
echo ""
echo ">>> STEP 5: Metrics report (reads from CloudWatch)"
sleep 30   # give CW a moment to process the custom metrics
python metrics/cloudwatch_reader.py
python metrics/cost_report.py

# ── Step 6: Cleanup ──────────────────────────────────────
echo ""
echo ">>> STEP 6: Cleanup (destroying all resources)"
python infrastructure/cleanup.py

echo ""
echo "============================================================"
echo "  ✅ POC complete. All resources destroyed."
echo "  Check CloudWatch > Metrics > BedrockPOC for your data."
echo "  Metrics are retained for 15 months by default."
echo "============================================================"

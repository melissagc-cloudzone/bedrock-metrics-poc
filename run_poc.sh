#!/usr/bin/env bash
# ============================================================
# ONE-SHOT: deploys, runs all use cases, prints metrics, cleans up
# Chatbot + DynamoDB run 3x to build richer CloudWatch time-series
# RAG runs once (OpenSearch billing only active during setup/query)
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

echo ""
echo "============================================================"
echo "  BEDROCK METRICS POC — FULL RUN"
echo "  Est. cost: \$5-12 total | ~20 min end-to-end"
echo "  cleanup.py runs automatically — nothing left behind"
echo "============================================================"
echo ""

# Install deps
pip install -r requirements.txt -q

# ── Steps 1-3: Chatbot + DynamoDB x3 (no infra, cents each) ─
# Running 3 rounds gives CloudWatch 3 separate data points per
# metric, which is enough to see a time-series trend in the dashboard.

for ROUND in 1 2 3; do
    echo ">>> ROUND $ROUND/3 — Chatbot simulation"
    python use_cases/chatbot_sim.py

    echo ""
    echo ">>> ROUND $ROUND/3 — DynamoDB audit trail"
    python use_cases/dynamodb_logger.py

    if [ "$ROUND" -lt 3 ]; then
        echo ""
        echo "  (waiting 60s so CloudWatch plots separate data points...)"
        sleep 60
        echo ""
    fi
done

# ── Step 4: RAG infra + POC ──────────────────────────────────
echo ""
echo ">>> STEP 4: RAG setup (takes ~7 min — OpenSearch billing starts now)"
python infrastructure/setup_rag.py

KB_ID=$(python -c "import json; print(json.load(open('infrastructure/.rag_state.json'))['kb_id'])")
export BEDROCK_KB_ID="$KB_ID"
echo "  KB ID: $KB_ID"

echo ""
echo ">>> STEP 5: RAG chatbot simulation"
python use_cases/rag_chatbot.py

# ── Step 6: Metrics report ───────────────────────────────────
echo ""
echo ">>> STEP 6: Metrics report (reads from CloudWatch)"
sleep 30
python metrics/cloudwatch_reader.py
python metrics/cost_report.py

# ── Step 7: Cleanup ──────────────────────────────────────────
echo ""
echo ">>> STEP 7: Cleanup — destroying all resources"
python infrastructure/cleanup.py

echo ""
echo "============================================================"
echo "  POC complete. All resources destroyed."
echo ""
echo "  Your data lives in CloudWatch for 15 months:"
echo "  → AWS Console > CloudWatch > Metrics > BedrockPOC"
echo "  → AWS Console > CloudWatch > Metrics > AWS/Bedrock"
echo ""
echo "  Your audit trail (already deleted from DynamoDB, but"
echo "  metrics are in CloudWatch — use them for cost reports)."
echo "============================================================"

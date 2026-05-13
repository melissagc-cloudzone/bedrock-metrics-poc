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

# ── Step 4: Metrics report ───────────────────────────────────
# RAG skipped: PowerUserAccess blocks iam:CreateRole (needed for KB service role)
echo ""
echo ">>> STEP 4: Metrics report (reads from CloudWatch)"
echo "  (RAG skipped — iam:CreateRole not available in this account)"
sleep 30
python metrics/cloudwatch_reader.py
python metrics/cost_report.py

echo ""
echo "============================================================"
echo "  POC complete. Resources LEFT RUNNING for manager demo."
echo ""
echo "  Live resources (accruing NO ongoing cost):"
echo "  → DynamoDB table: bedrock-poc-usage-log  (us-east-1)"
echo "     Inspect in console: Tables > bedrock-poc-usage-log > Explore items"
echo "     Tags on the table:  Project=bedrock-metrics-poc, Owner=melissa,"
echo "                         Environment=playground, AutoDelete=yes"
echo ""
echo "  CloudWatch data (kept 15 months — free to query):"
echo "  → Console > CloudWatch > Metrics > BedrockPOC"
echo "     AuditTrailCostUSD, ChatbotSessionCostUSD, ChatbotLatencyMs..."
echo "  → Console > CloudWatch > Metrics > AWS/Bedrock"
echo "     InputTokenCount, OutputTokenCount, InvocationLatency..."
echo ""
echo "  When you're ready to clean up, run:"
echo "  → ./teardown.sh"
echo ""
echo "  RAG was skipped (iam:CreateRole blocked by PowerUserAccess)."
echo "  The RAG metrics story is documented in docs/metrics_guide.md"
echo "============================================================"

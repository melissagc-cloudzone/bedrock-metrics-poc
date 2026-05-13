#!/usr/bin/env bash
# Deletes all persistent resources created by run_poc.sh (no-RAG run).
# CloudWatch metric data is NOT deleted — it expires automatically after 15 months.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

echo ""
echo "============================================================"
echo "  BEDROCK METRICS POC — TEARDOWN"
echo "============================================================"
echo ""
echo "  Resources to delete:"
echo "    • DynamoDB table: bedrock-poc-usage-log  (us-east-1)"
echo "    • CloudWatch metrics: NOT deleted (auto-expire in 15 months)"
echo ""

python -c "
import boto3
ddb = boto3.client('dynamodb', region_name='us-east-1')
try:
    ddb.delete_table(TableName='bedrock-poc-usage-log')
    print('  ✓ DynamoDB table deleted: bedrock-poc-usage-log')
except ddb.exceptions.ResourceNotFoundException:
    print('  ✓ DynamoDB table already deleted (nothing to do)')
except Exception as e:
    print(f'  ✗ Error: {e}')
"

echo ""
echo "  Done. Nothing left running."
echo "============================================================"

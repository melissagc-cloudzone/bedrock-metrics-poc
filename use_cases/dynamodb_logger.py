"""
DynamoDB Audit Trail POC — every Bedrock call gets logged as a record:
  model_id, input_tokens, output_tokens, cost_usd, latency_ms, use_case, tags

Why this matters for customers: CloudWatch metrics aggregate and expire.
DynamoDB gives you a queryable, permanent per-call audit trail you can
feed into Cost Explorer, Athena, or BI tools for chargeback / showback.

Metrics captured:
  [DynamoDB]   full per-call record (tokens, cost, latency, tags)
  [Instrumented] running session total, cost per use_case dimension
"""

import boto3, json, time, sys
from datetime import datetime
from decimal import Decimal
sys.path.insert(0, "..")
from config import REGION, CHATBOT_MODEL, calc_cost, boto_tags
from metrics.custom_metrics import push_metric

bedrock  = boto3.client("bedrock-runtime", region_name=REGION)
dynamodb = boto3.resource("dynamodb",      region_name=REGION)
ddb      = boto3.client("dynamodb",        region_name=REGION)

TABLE_NAME = "bedrock-poc-usage-log"

PROMPTS = [
    ("chatbot",      "What is FinOps and why does it matter for cloud teams?"),
    ("chatbot",      "Name 3 ways to reduce AWS Bedrock costs."),
    ("summarize",    "Summarize in 2 sentences: FinOps is the practice of bringing financial accountability to cloud spending."),
    ("summarize",    "Summarize in 2 sentences: Amazon Bedrock provides access to foundation models via a managed API."),
    ("classification","Classify this as URGENT or NORMAL: The production database is returning 500 errors."),
    ("classification","Classify this as URGENT or NORMAL: The weekly cost report is ready for review."),
]


def create_table_if_not_exists():
    existing = ddb.list_tables()["TableNames"]
    if TABLE_NAME in existing:
        print(f"  ✓ Table exists: {TABLE_NAME}")
        return

    print(f"  Creating DynamoDB table: {TABLE_NAME}...")
    ddb.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "call_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "call_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
        Tags=boto_tags({"Phase": "audit-trail"}),
    )
    waiter = ddb.get_waiter("table_exists")
    waiter.wait(TableName=TABLE_NAME)
    print(f"  ✓ Table created: {TABLE_NAME}")


def invoke_and_log(use_case: str, prompt: str) -> dict:
    t0 = time.time()
    response = bedrock.invoke_model(
        modelId=CHATBOT_MODEL,
        body=json.dumps({
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"max_new_tokens": 200, "temperature": 0.5},
        }),
    )
    latency_ms = (time.time() - t0) * 1000
    result     = json.loads(response["body"].read())

    in_tok  = result["usage"]["inputTokens"]
    out_tok = result["usage"]["outputTokens"]
    cost    = calc_cost(CHATBOT_MODEL, in_tok, out_tok)

    call_id = f"{use_case}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"

    dynamodb.Table(TABLE_NAME).put_item(Item={
        "call_id":       call_id,
        "timestamp":     datetime.utcnow().isoformat(),
        "use_case":      use_case,
        "model_id":      CHATBOT_MODEL,
        "prompt":        prompt[:200],
        "input_tokens":  in_tok,
        "output_tokens": out_tok,
        "cost_usd":      Decimal(str(round(cost, 8))),
        "latency_ms":    Decimal(str(round(latency_ms, 2))),
        "tags": {
            "Project":     "bedrock-metrics-poc",
            "Owner":       "melissa",
            "Environment": "playground",
        },
    })

    push_metric("AuditTrailCostUSD",      cost,       "None",         use_case)
    push_metric("AuditTrailInputTokens",  in_tok,     "Count",        use_case)
    push_metric("AuditTrailLatencyMs",    latency_ms, "Milliseconds", use_case)

    return {"call_id": call_id, "use_case": use_case,
            "in_tok": in_tok, "out_tok": out_tok,
            "latency_ms": latency_ms, "cost_usd": cost}


def run():
    print("=" * 60)
    print("  DYNAMODB AUDIT TRAIL POC")
    print(f"  Table: {TABLE_NAME}  |  Region: {REGION}")
    print("=" * 60)

    create_table_if_not_exists()
    print(f"\n  Running {len(PROMPTS)} calls across 3 use cases...\n")

    total_cost   = 0.0
    by_use_case  = {}

    for use_case, prompt in PROMPTS:
        m = invoke_and_log(use_case, prompt)
        total_cost += m["cost_usd"]
        by_use_case[use_case] = by_use_case.get(use_case, 0.0) + m["cost_usd"]

        print(f"  [{use_case:<14}]  {m['in_tok']:>3} in / {m['out_tok']:>3} out tokens"
              f"  | {m['latency_ms']:>6.0f} ms  | ${m['cost_usd']:.6f}  → logged")

    print(f"\n{'=' * 60}")
    print(f"  AUDIT TRAIL SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total calls logged: {len(PROMPTS)}")
    print(f"  Total cost:         ${total_cost:.5f}")
    for uc, uc_cost in by_use_case.items():
        print(f"  Cost [{uc:<14}]: ${uc_cost:.5f}")

    print(f"\n  Query your audit trail in DynamoDB console:")
    print(f"  → Table: {TABLE_NAME}  |  Region: {REGION}")
    print(f"\n  Customer value: this table feeds chargeback by use_case,")
    print(f"  cost trending over time, and per-team showback reports.")


if __name__ == "__main__":
    run()

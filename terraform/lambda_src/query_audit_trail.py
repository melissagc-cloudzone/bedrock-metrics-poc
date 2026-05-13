import json
import os
import boto3
from datetime import datetime, timedelta
from decimal import Decimal

dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("REGION", "us-east-1"))
TABLE_NAME = os.environ.get("TABLE_NAME", "bedrock-poc-usage-log")


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def handler(event, context):
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}
    use_case_filter = params.get("use_case", "all")
    hours = int(params.get("hours", 24))

    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    table = dynamodb.Table(TABLE_NAME)

    response = table.scan(
        FilterExpression="#ts >= :cutoff",
        ExpressionAttributeNames={"#ts": "timestamp"},
        ExpressionAttributeValues={":cutoff": cutoff},
    )
    records = response.get("Items", [])

    if use_case_filter and use_case_filter != "all":
        records = [r for r in records if r.get("use_case") == use_case_filter]

    by_use_case = {}
    total_cost = 0.0

    for r in records:
        uc = r.get("use_case", "unknown")
        cost = float(r.get("cost_usd", 0))
        total_cost += cost

        if uc not in by_use_case:
            by_use_case[uc] = {"calls": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}

        by_use_case[uc]["calls"] += 1
        by_use_case[uc]["cost_usd"] = round(by_use_case[uc]["cost_usd"] + cost, 8)
        by_use_case[uc]["input_tokens"] += int(r.get("input_tokens", 0))
        by_use_case[uc]["output_tokens"] += int(r.get("output_tokens", 0))

    result = {
        "total_cost_usd": round(total_cost, 6),
        "record_count": len(records),
        "hours_queried": hours,
        "by_use_case": by_use_case,
    }

    return {
        "response": {
            "actionGroup": event.get("actionGroup"),
            "apiPath": event.get("apiPath"),
            "httpMethod": event.get("httpMethod"),
            "httpStatusCode": 200,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(result, cls=DecimalEncoder)
                }
            },
        }
    }

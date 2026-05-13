import json
import os
import boto3
from datetime import datetime, timedelta
from decimal import Decimal

dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("REGION", "us-east-1"))
TABLE_NAME = os.environ.get("TABLE_NAME", "bedrock-poc-usage-log")

NOVA_LITE_INPUT_PER_1K = 0.00006
NOVA_LITE_OUTPUT_PER_1K = 0.00024
NOVA_PRO_INPUT_PER_1K = 0.0008
NOVA_PRO_OUTPUT_PER_1K = 0.0032
BATCH_DISCOUNT = 0.50
ASYNC_ELIGIBLE_USE_CASES = {"summarize", "classification"}


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _scan_records(hours):
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    table = dynamodb.Table(TABLE_NAME)
    response = table.scan(
        FilterExpression="#ts >= :cutoff",
        ExpressionAttributeNames={"#ts": "timestamp"},
        ExpressionAttributeValues={":cutoff": cutoff},
    )
    return response.get("Items", [])


def _monthly_multiplier(hours):
    return (24 * 30) / max(hours, 1)


def _batch_inference(records, hours):
    async_records = [r for r in records if r.get("use_case") in ASYNC_ELIGIBLE_USE_CASES]
    async_cost = sum(float(r.get("cost_usd", 0)) for r in async_records)
    total_cost = sum(float(r.get("cost_usd", 0)) for r in records)

    mult = _monthly_multiplier(hours)
    monthly_total = round(total_cost * mult, 4)
    monthly_async = round(async_cost * mult, 4)
    saving = round(monthly_async * BATCH_DISCOUNT, 4)
    pct = round((saving / monthly_total * 100) if monthly_total > 0 else 0, 1)

    eligible_calls = len(async_records)
    total_calls = len(records)

    return {
        "strategy": "batch_inference",
        "current_monthly_cost_usd": monthly_total,
        "eligible_monthly_cost_usd": monthly_async,
        "estimated_saving_usd": saving,
        "saving_percentage": pct,
        "eligible_calls_pct": round((eligible_calls / total_calls * 100) if total_calls else 0, 1),
        "recommendation": (
            f"{eligible_calls} of {total_calls} calls ({pct}% of cost) are async-eligible "
            f"(summarize, classification). Moving these to Batch Inference saves ~${saving:.4f}/month "
            f"at scale with no code change beyond SDK — just submit a BatchInference job."
        ),
    }


def _model_switch(records, hours):
    total_input = sum(int(r.get("input_tokens", 0)) for r in records)
    total_output = sum(int(r.get("output_tokens", 0)) for r in records)
    total_cost = sum(float(r.get("cost_usd", 0)) for r in records)

    mult = _monthly_multiplier(hours)
    monthly_input = total_input * mult
    monthly_output = total_output * mult

    current_monthly = round(total_cost * mult, 4)
    pro_monthly = round(
        (monthly_input / 1000 * NOVA_PRO_INPUT_PER_1K)
        + (monthly_output / 1000 * NOVA_PRO_OUTPUT_PER_1K),
        4,
    )
    saving = round(pro_monthly - current_monthly, 4)
    pct = round((saving / pro_monthly * 100) if pro_monthly > 0 else 0, 1)

    return {
        "strategy": "model_switch",
        "current_model": "Nova Lite",
        "current_monthly_cost_usd": current_monthly,
        "nova_pro_monthly_cost_usd": pro_monthly,
        "estimated_saving_usd": saving,
        "saving_percentage": pct,
        "recommendation": (
            f"Staying on Nova Lite saves ~${saving:.4f}/month vs Nova Pro "
            f"({pct}% cheaper). Only upgrade to Nova Pro if quality evaluations "
            f"show measurable task improvement — the cost delta doesn't justify it for "
            f"chatbot or classification workloads at this token volume."
        ),
    }


def handler(event, context):
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}
    strategy = params.get("strategy", "batch_inference")
    hours = int(params.get("hours", 24))

    records = _scan_records(hours)

    if strategy == "batch_inference":
        result = _batch_inference(records, hours)
    elif strategy == "model_switch":
        result = _model_switch(records, hours)
    else:
        result = {"error": f"Unknown strategy: {strategy}. Use batch_inference or model_switch."}

    result["hours_analyzed"] = hours
    result["record_count"] = len(records)

    return {
        "response": {
            "actionGroup": event.get("actionGroup"),
            "apiPath": event.get("apiPath"),
            "httpMethod": event.get("httpMethod"),
            "httpStatusCode": 200,
            "responseBody": {
                "application/json": {"body": json.dumps(result, cls=DecimalEncoder)}
            },
        }
    }

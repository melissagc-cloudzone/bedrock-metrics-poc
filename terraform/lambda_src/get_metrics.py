import json
import os
import boto3
import datetime

cw = boto3.client("cloudwatch", region_name=os.environ.get("REGION", "us-east-1"))


def _stat(namespace, metric, stat="Sum", hours=3):
    end = datetime.datetime.utcnow()
    start = end - datetime.timedelta(hours=hours)
    resp = cw.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric,
        Dimensions=[],
        StartTime=start,
        EndTime=end,
        Period=int(hours * 3600),
        Statistics=[stat],
    )
    pts = resp.get("Datapoints", [])
    return round(pts[0][stat], 4) if pts else 0.0


def handler(event, context):
    params = {p["name"]: p["value"] for p in event.get("parameters", [])}
    hours = int(params.get("hours", 3))

    result = {
        "window_hours": hours,
        "native_bedrock": {
            "input_tokens": _stat("AWS/Bedrock", "InputTokenCount", "Sum", hours),
            "output_tokens": _stat("AWS/Bedrock", "OutputTokenCount", "Sum", hours),
            "avg_latency_ms": _stat("AWS/Bedrock", "InvocationLatency", "Average", hours),
            "p99_latency_ms": _stat("AWS/Bedrock", "InvocationLatency", "p99", hours),
            "client_errors": _stat("AWS/Bedrock", "InvocationClientErrors", "Sum", hours),
            "throttles": _stat("AWS/Bedrock", "InvocationsThrottled", "Sum", hours),
        },
        "custom_poc": {
            "chatbot_session_cost_usd": _stat("BedrockPOC", "ChatbotSessionCostUSD", "Sum", hours),
            "audit_trail_cost_usd": _stat("BedrockPOC", "AuditTrailCostUSD", "Sum", hours),
            "chatbot_latency_ms": _stat("BedrockPOC", "ChatbotLatencyMs", "Average", hours),
            "audit_trail_latency_ms": _stat("BedrockPOC", "AuditTrailLatencyMs", "Average", hours),
        },
    }

    return {
        "response": {
            "actionGroup": event.get("actionGroup"),
            "apiPath": event.get("apiPath"),
            "httpMethod": event.get("httpMethod"),
            "httpStatusCode": 200,
            "responseBody": {
                "application/json": {"body": json.dumps(result)}
            },
        }
    }

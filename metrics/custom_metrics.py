"""
Pushes custom metrics to CloudWatch under namespace 'BedrockPOC'.

Why we need this: Bedrock natively emits InvocationLatency, InputTokenCount,
OutputTokenCount, and error counts. It does NOT emit cost, session-level
aggregates, or RAG-specific metrics. We push those ourselves.
"""

import boto3, datetime
from config import REGION

_cw = boto3.client("cloudwatch", region_name=REGION)

NAMESPACE = "BedrockPOC"


def push_metric(name: str, value: float, unit: str = "None", dimension_value: str = "default"):
    """
    unit options: Seconds, Milliseconds, Bytes, Count, None, etc.
    dimension_value: a label for the data point (session-id, turn-id, etc.)
    """
    _cw.put_metric_data(
        Namespace=NAMESPACE,
        MetricData=[{
            "MetricName": name,
            "Dimensions": [{"Name": "UseCase", "Value": dimension_value}],
            "Timestamp":  datetime.datetime.utcnow(),
            "Value":      value,
            "Unit":       unit,
        }],
    )

import boto3

REGION        = "us-east-1"
PROJECT_TAG   = "bedrock-metrics-poc"
OWNER_TAG     = "melissa"
ENV_TAG       = "playground"

TAGS = {
    "Project":     PROJECT_TAG,
    "Owner":       OWNER_TAG,
    "Environment": ENV_TAG,
    "AutoDelete":  "yes",
}

# Models used in the POC
CHATBOT_MODEL = "amazon.nova-2-lite-v1:0"
EMBED_MODEL   = "amazon.titan-embed-text-v2:0"

# On-demand pricing (us-east-1, May 2026)
PRICING = {
    "amazon.nova-2-lite-v1:0": {
        "input_per_1k":  0.00007,
        "output_per_1k": 0.00028,
    },
    "amazon.titan-embed-text-v1": {
        "input_per_1k":  0.0001,
        "output_per_1k": 0.0,
    },
}

def boto_tags(extra: dict = None) -> list:
    t = {**TAGS, **(extra or {})}
    return [{"Key": k, "Value": v} for k, v in t.items()]

def bedrock_tags(extra: dict = None) -> list:
    t = {**TAGS, **(extra or {})}
    return [{"key": k, "value": v} for k, v in t.items()]

def calc_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICING.get(model_id, {"input_per_1k": 0, "output_per_1k": 0})
    return (input_tokens / 1000 * p["input_per_1k"]) + (output_tokens / 1000 * p["output_per_1k"])

ACCOUNT_ID = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]

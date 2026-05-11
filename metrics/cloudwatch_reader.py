"""
Reads and prints metrics from both:
  1. AWS/Bedrock  — native metrics Bedrock emits automatically
  2. BedrockPOC   — custom metrics pushed by our POC scripts

Run this AFTER executing the use_case scripts to see the numbers.
"""

import boto3, datetime
from config import REGION
from tabulate import tabulate

cw = boto3.client("cloudwatch", region_name=REGION)

END   = datetime.datetime.utcnow()
START = END - datetime.timedelta(hours=3)   # look back 3 hours


def get_stat(namespace: str, metric: str, dimensions: list, stat: str = "Sum") -> float:
    resp = cw.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric,
        Dimensions=dimensions,
        StartTime=START,
        EndTime=END,
        Period=10800,   # one bucket for the whole window
        Statistics=[stat],
    )
    pts = resp.get("Datapoints", [])
    return pts[0][stat] if pts else 0.0


def list_bedrock_models() -> list[str]:
    """Returns model IDs that have emitted metrics in the look-back window."""
    paginator = cw.get_paginator("list_metrics")
    model_ids = set()
    for page in paginator.paginate(Namespace="AWS/Bedrock", MetricName="InputTokenCount"):
        for m in page["Metrics"]:
            for d in m["Dimensions"]:
                if d["Name"] == "ModelId":
                    model_ids.add(d["Value"])
    return sorted(model_ids)


def show_native_bedrock_metrics():
    print("\n" + "=" * 60)
    print("  NATIVE BEDROCK METRICS  (namespace: AWS/Bedrock)")
    print("=" * 60)
    print("  NOTE: Bedrock emits these automatically — no code required.")
    print(f"  Window: last 3 hours\n")

    models = list_bedrock_models()
    if not models:
        print("  No data yet — run use_cases/chatbot_sim.py first.\n")
        return

    rows = []
    for model_id in models:
        short = model_id.split("/")[-1]
        dims  = [{"Name": "ModelId", "Value": model_id}]

        in_tok   = get_stat("AWS/Bedrock", "InputTokenCount",        dims, "Sum")
        out_tok  = get_stat("AWS/Bedrock", "OutputTokenCount",       dims, "Sum")
        latency  = get_stat("AWS/Bedrock", "InvocationLatency",      dims, "Average")
        errors   = get_stat("AWS/Bedrock", "InvocationClientErrors", dims, "Sum")
        throttle = get_stat("AWS/Bedrock", "InvocationsThrottled",   dims, "Sum")

        rows.append([short, f"{in_tok:,.0f}", f"{out_tok:,.0f}",
                     f"{latency:.0f} ms", f"{errors:.0f}", f"{throttle:.0f}"])

    print(tabulate(rows,
                   headers=["Model", "Input Tokens", "Output Tokens",
                             "Avg Latency", "Client Errors", "Throttled"],
                   tablefmt="simple"))


def show_custom_metrics():
    print("\n" + "=" * 60)
    print("  CUSTOM POC METRICS  (namespace: BedrockPOC)")
    print("=" * 60)
    print("  NOTE: These are NOT emitted by Bedrock — we push them ourselves.")
    print("  They represent the business-level view customers actually want.\n")

    chatbot_metrics = [
        ("ChatbotSessionCostUSD",     "Sum",     "Total chatbot cost (USD)"),
        ("ChatbotSessionTurns",       "Sum",     "Total conversation turns"),
        ("ChatbotLatencyMs",          "Average", "Avg turn latency (ms)"),
        ("ChatbotSessionInputTokens", "Sum",     "Cumulative input tokens"),
    ]

    rag_metrics = [
        ("RAGTotalQueryCostUSD",      "Sum",     "Total RAG cost (USD)"),
        ("RAGEmbedCostUSD",           "Sum",     "Embedding cost (USD)"),
        ("RAGGenerationCostUSD",      "Sum",     "Generation cost (USD)"),
        ("RAGRetrievalLatencyMs",     "Average", "Avg retrieval latency (ms)"),
        ("RAGGenerationLatencyMs",    "Average", "Avg generation latency (ms)"),
        ("RAGChunksRetrieved",        "Average", "Avg chunks retrieved"),
        ("RAGTopChunkScore",          "Average", "Avg top chunk relevance score"),
    ]

    print("  -- Chatbot Use Case --")
    rows = []
    for metric, stat, label in chatbot_metrics:
        val = get_stat("BedrockPOC", metric, [], stat)
        rows.append([label, f"{val:.5f}" if "USD" in metric else f"{val:,.1f}"])
    print(tabulate(rows, headers=["Metric", "Value"], tablefmt="simple"))

    print("\n  -- RAG Chatbot Use Case --")
    rows = []
    for metric, stat, label in rag_metrics:
        val = get_stat("BedrockPOC", metric, [], stat)
        rows.append([label, f"{val:.5f}" if "USD" in metric else f"{val:,.2f}"])
    print(tabulate(rows, headers=["Metric", "Value"], tablefmt="simple"))


def show_metric_gap():
    print("\n" + "=" * 60)
    print("  WHAT BEDROCK GIVES YOU vs. WHAT YOU NEED TO BUILD")
    print("=" * 60)
    rows = [
        ["InvocationLatency",        "AWS/Bedrock", "Yes", "Latency per API call"],
        ["InputTokenCount",          "AWS/Bedrock", "Yes", "Tokens consumed (input)"],
        ["OutputTokenCount",         "AWS/Bedrock", "Yes", "Tokens generated"],
        ["InvocationClientErrors",   "AWS/Bedrock", "Yes", "4xx errors"],
        ["InvocationsThrottled",     "AWS/Bedrock", "Yes", "Throttle events"],
        ["Cost per call",            "BedrockPOC",  "No",  "Calculate from token counts"],
        ["Cost per session",         "BedrockPOC",  "No",  "Aggregate across turns"],
        ["Cost per RAG query",       "BedrockPOC",  "No",  "Embed + retrieval + generation"],
        ["Retrieval relevance score","BedrockPOC",  "No",  "From retrieve() response body"],
        ["Chunks retrieved",         "BedrockPOC",  "No",  "Count from retrieve() results"],
        ["Session turn count",       "BedrockPOC",  "No",  "Track in your app layer"],
    ]
    print(tabulate(rows,
                   headers=["Metric", "Namespace", "Auto?", "Notes"],
                   tablefmt="simple"))
    print()


if __name__ == "__main__":
    show_native_bedrock_metrics()
    show_custom_metrics()
    show_metric_gap()

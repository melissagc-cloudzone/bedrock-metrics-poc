"""
Pulls cost data from CloudWatch custom metrics and prints a per-use-case
cost report. Run after executing the use_case scripts.
"""

import boto3, datetime
from config import REGION
from tabulate import tabulate

cw    = boto3.client("cloudwatch", region_name=REGION)
END   = datetime.datetime.utcnow()
START = END - datetime.timedelta(hours=3)


def _sum(metric: str) -> float:
    resp = cw.get_metric_statistics(
        Namespace="BedrockPOC",
        MetricName=metric,
        Dimensions=[],
        StartTime=START,
        EndTime=END,
        Period=10800,
        Statistics=["Sum"],
    )
    pts = resp.get("Datapoints", [])
    return pts[0]["Sum"] if pts else 0.0


def _avg(metric: str) -> float:
    resp = cw.get_metric_statistics(
        Namespace="BedrockPOC",
        MetricName=metric,
        Dimensions=[],
        StartTime=START,
        EndTime=END,
        Period=10800,
        Statistics=["Average"],
    )
    pts = resp.get("Datapoints", [])
    return pts[0]["Average"] if pts else 0.0


def run():
    print("\n" + "=" * 60)
    print("  BEDROCK POC — COST REPORT")
    print(f"  Window: last 3 hours")
    print("=" * 60)

    chatbot_cost = _sum("ChatbotSessionCostUSD")
    rag_cost     = _sum("RAGTotalQueryCostUSD")
    total_cost   = chatbot_cost + rag_cost

    sessions      = _sum("ChatbotSessionTurns")
    rag_queries   = _sum("RAGTotalQueryCostUSD")   # count workaround: use count of non-zero

    rows = [
        ["Chatbot (multi-turn)",  f"${chatbot_cost:.5f}",
         f"${_avg('ChatbotSessionCostUSD'):.5f} / session",
         f"{_avg('ChatbotLatencyMs'):.0f} ms avg"],
        ["RAG Chatbot",           f"${rag_cost:.5f}",
         f"${_avg('RAGTotalQueryCostUSD'):.5f} / query",
         f"{_avg('RAGGenerationLatencyMs'):.0f} ms gen avg"],
        ["TOTAL",                 f"${total_cost:.5f}", "", ""],
    ]

    print(tabulate(rows,
                   headers=["Use Case", "Total Cost", "Unit Cost", "Latency"],
                   tablefmt="simple"))

    print(f"\n  RAG cost split:")
    embed_cost = _sum("RAGEmbedCostUSD")
    gen_cost   = _sum("RAGGenerationCostUSD")
    if rag_cost > 0:
        print(f"    Embedding:   ${embed_cost:.5f}  ({embed_cost/rag_cost*100:.1f}%)")
        print(f"    Generation:  ${gen_cost:.5f}  ({gen_cost/rag_cost*100:.1f}%)")

    print(f"\n  Monthly projection (if this session = 1 hour of usage):")
    hourly    = total_cost
    projected = hourly * 24 * 30
    print(f"    ${hourly:.4f} / hr  →  ~${projected:.2f} / month")
    print(f"    (adjust multiplier based on actual daily hours of traffic)")

    print(f"\n  Customer advisory:")
    if projected > 50:
        print("    ⚠️  Consider Provisioned Throughput for high-traffic chatbot")
        print("    ⚠️  Consider reducing KB chunk count for RAG cost savings")
    else:
        print("    ✓  On-Demand is cost-effective at this traffic level")
        print("    ✓  Monitor with CW alarms on InputTokenCount for budget guardrails")


if __name__ == "__main__":
    run()

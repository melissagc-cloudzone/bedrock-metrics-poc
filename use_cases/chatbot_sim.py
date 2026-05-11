"""
Chatbot POC — simulates a multi-turn support chatbot and surfaces every
metric you would want to track for this use case.

Metrics captured:
  [Native CW]  InvocationLatency, InputTokenCount, OutputTokenCount
  [Instrumented] cost_usd, tokens_per_turn, latency_ms, session_total_cost
"""

import json, time, sys
sys.path.insert(0, "..")
import boto3
from config import REGION, CHATBOT_MODEL, calc_cost
from metrics.custom_metrics import push_metric

client = boto3.client("bedrock-runtime", region_name=REGION)

SESSIONS = [
    [
        "What AWS services should I use for a serverless API?",
        "Can you show me an example Lambda function in Python?",
        "How much would that cost if I get 1 million requests a month?",
    ],
    [
        "Explain the difference between S3 Standard and S3 Intelligent-Tiering.",
        "When does Intelligent-Tiering actually save money?",
        "What's the minimum object size worth tiering?",
    ],
    [
        "What is Amazon Bedrock?",
        "Which models does it support?",
        "How is it priced compared to calling the model APIs directly?",
    ],
]


def run_turn(messages: list, turn_label: str) -> dict:
    t0 = time.time()
    response = client.invoke_model(
        modelId=CHATBOT_MODEL,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "temperature": 0.7,
            "messages": messages,
        }),
    )
    latency_ms = (time.time() - t0) * 1000
    result     = json.loads(response["body"].read())

    in_tok  = result["usage"]["input_tokens"]
    out_tok = result["usage"]["output_tokens"]
    cost    = calc_cost(CHATBOT_MODEL, in_tok, out_tok)
    text    = result["content"][0]["text"]

    push_metric("ChatbotLatencyMs",    latency_ms, "Milliseconds", turn_label)
    push_metric("ChatbotInputTokens",  in_tok,     "Count",        turn_label)
    push_metric("ChatbotOutputTokens", out_tok,    "Count",        turn_label)
    push_metric("ChatbotCostUSD",      cost,       "None",         turn_label)

    return {"text": text, "in_tok": in_tok, "out_tok": out_tok,
            "latency_ms": latency_ms, "cost_usd": cost}


def run():
    print("=" * 60)
    print("  CHATBOT POC — METRICS SIMULATION")
    print("=" * 60)

    total_cost    = 0.0
    total_in_tok  = 0
    total_out_tok = 0

    for s_idx, prompts in enumerate(SESSIONS):
        session_id = f"session-{s_idx + 1}"
        print(f"\n--- {session_id} ({len(prompts)} turns) ---")

        messages          = []
        session_cost      = 0.0
        session_in_tokens = 0

        for t_idx, prompt in enumerate(prompts):
            messages.append({"role": "user", "content": prompt})
            turn_label = f"{session_id}-turn{t_idx + 1}"

            m = run_turn(messages, turn_label)
            messages.append({"role": "assistant", "content": m["text"]})

            session_cost      += m["cost_usd"]
            session_in_tokens += m["in_tok"]

            print(f"  Turn {t_idx+1}: {m['in_tok']:>4} in / {m['out_tok']:>4} out tokens  "
                  f"| {m['latency_ms']:>6.0f} ms  | ${m['cost_usd']:.6f}")

        push_metric("ChatbotSessionCostUSD",        session_cost,      "None", session_id)
        push_metric("ChatbotSessionInputTokens",    session_in_tokens, "Count", session_id)
        push_metric("ChatbotSessionTurns",          len(prompts),      "Count", session_id)

        print(f"  Session total: ${session_cost:.5f}  "
              f"({session_in_tokens} cumulative input tokens)")

        total_cost    += session_cost
        total_in_tok  += session_in_tokens
        total_out_tok += sum(0 for _ in prompts)   # already counted above

    print(f"\n{'=' * 60}")
    print(f"  CHATBOT SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Sessions:          {len(SESSIONS)}")
    print(f"  Total cost:        ${total_cost:.5f}")
    print(f"  Cost per session:  ${total_cost / len(SESSIONS):.5f}")
    print(f"\n  Metrics pushed to CloudWatch namespace: BedrockPOC")
    print(f"  Native Bedrock metrics in CW namespace: AWS/Bedrock")
    print(f"  (check InvocationLatency, InputTokenCount, OutputTokenCount)")


if __name__ == "__main__":
    run()

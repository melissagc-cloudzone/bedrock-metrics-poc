"""
RAG Chatbot POC — shows the cost and metrics split between:
  1. Embedding the query (Titan Embeddings)
  2. Retrieving chunks from the Knowledge Base
  3. Generating the answer (Claude 3 Haiku)

Metrics captured:
  [Native CW]  InvocationLatency, InputTokenCount, OutputTokenCount (both models)
  [Instrumented] embed_cost_usd, generation_cost_usd, retrieval_latency_ms,
                 generation_latency_ms, chunks_retrieved, total_cost_usd

Run infrastructure/setup_rag.py first — it will print the KB_ID to use here.
"""

import json, time, sys, os
sys.path.insert(0, "..")
import boto3
from config import REGION, CHATBOT_MODEL, EMBED_MODEL, calc_cost
from metrics.custom_metrics import push_metric

bedrock_runtime = boto3.client("bedrock-runtime",  region_name=REGION)
bedrock_agent   = boto3.client("bedrock-agent-runtime", region_name=REGION)

# Set via env var after running setup_rag.py
KB_ID = os.environ.get("BEDROCK_KB_ID", "")

RAG_QUESTIONS = [
    "What is the estimated monthly cost breakdown for this POC?",
    "Which optimization methods can reduce Bedrock costs?",
    "What resources must be deleted at the end of the project?",
    "When should I use batch inference instead of on-demand?",
]


def embed_and_retrieve(question: str) -> tuple[list, float, float]:
    """Retrieve chunks from Knowledge Base; return (chunks, latency_ms, embed_cost)."""
    t0 = time.time()

    # Embed the query
    embed_resp = bedrock_runtime.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps({"inputText": question}),
    )
    embed_result  = json.loads(embed_resp["body"].read())
    embed_in_tok  = embed_result.get("inputTextTokenCount", 0)
    embed_cost    = calc_cost(EMBED_MODEL, embed_in_tok, 0)

    # Retrieve from Knowledge Base
    retrieve_resp = bedrock_agent.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": question},
        retrievalConfiguration={
            "vectorSearchConfiguration": {"numberOfResults": 3}
        },
    )
    latency_ms = (time.time() - t0) * 1000
    chunks     = [r["content"]["text"] for r in retrieve_resp["retrievalResults"]]
    scores     = [r["score"] for r in retrieve_resp["retrievalResults"]]

    push_metric("RAGRetrievalLatencyMs", latency_ms,   "Milliseconds", "retrieve")
    push_metric("RAGChunksRetrieved",    len(chunks),  "Count",        "retrieve")
    push_metric("RAGEmbedCostUSD",       embed_cost,   "None",         "retrieve")
    if scores:
        push_metric("RAGTopChunkScore",  scores[0],    "None",         "retrieve")

    return chunks, latency_ms, embed_cost


def generate_answer(question: str, chunks: list) -> dict:
    context  = "\n\n".join(chunks)
    system_p = (
        "You are a helpful assistant. Answer the user's question using ONLY "
        "the provided context. If the context doesn't contain the answer, say so."
    )
    messages = [{"role": "user", "content": [{"text": f"Context:\n{context}\n\nQuestion: {question}"}]}]

    t0 = time.time()
    response = bedrock_runtime.invoke_model(
        modelId=CHATBOT_MODEL,
        body=json.dumps({
            "system": [{"text": system_p}],
            "messages": messages,
            "inferenceConfig": {"max_new_tokens": 512, "temperature": 0.3},
        }),
    )
    latency_ms = (time.time() - t0) * 1000
    result     = json.loads(response["body"].read())

    in_tok  = result["usage"]["inputTokens"]
    out_tok = result["usage"]["outputTokens"]
    cost    = calc_cost(CHATBOT_MODEL, in_tok, out_tok)

    push_metric("RAGGenerationLatencyMs",    latency_ms, "Milliseconds", "generate")
    push_metric("RAGGenerationInputTokens",  in_tok,     "Count",        "generate")
    push_metric("RAGGenerationOutputTokens", out_tok,    "Count",        "generate")
    push_metric("RAGGenerationCostUSD",      cost,       "None",         "generate")

    return {"text": result["output"]["message"]["content"][0]["text"],
            "in_tok": in_tok, "out_tok": out_tok,
            "latency_ms": latency_ms, "cost_usd": cost}


def run():
    if not KB_ID:
        print("ERROR: set BEDROCK_KB_ID env var first.")
        print("  Run: infrastructure/setup_rag.py — it prints the KB ID.")
        sys.exit(1)

    print("=" * 60)
    print("  RAG CHATBOT POC — METRICS SIMULATION")
    print(f"  Knowledge Base: {KB_ID}")
    print("=" * 60)

    total_cost = 0.0

    for q in RAG_QUESTIONS:
        print(f"\nQ: {q[:70]}...")

        chunks, retr_ms, embed_cost = embed_and_retrieve(q)
        gen                         = generate_answer(q, chunks)

        query_cost = embed_cost + gen["cost_usd"]
        total_cost += query_cost

        push_metric("RAGTotalQueryCostUSD", query_cost, "None", "query")

        print(f"  Chunks retrieved:   {len(chunks)}")
        print(f"  Retrieval latency:  {retr_ms:.0f} ms  | embed cost: ${embed_cost:.6f}")
        print(f"  Generation:         {gen['in_tok']} in / {gen['out_tok']} out tokens"
              f"  | {gen['latency_ms']:.0f} ms  | ${gen['cost_usd']:.6f}")
        print(f"  Total query cost:   ${query_cost:.6f}")

    print(f"\n{'=' * 60}")
    print(f"  RAG CHATBOT SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Queries run:        {len(RAG_QUESTIONS)}")
    print(f"  Total cost:         ${total_cost:.5f}")
    print(f"  Cost per query:     ${total_cost / len(RAG_QUESTIONS):.5f}")
    print(f"\n  Cost split insight:")
    print(f"  → Embedding is cheap; generation (input tokens with context) dominates")
    print(f"  → Reduce generation cost by limiting chunk size and number of chunks")


if __name__ == "__main__":
    run()

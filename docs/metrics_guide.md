# Bedrock Metrics Guide — Customer Advisory

## What Bedrock gives you automatically (AWS/Bedrock namespace)

These metrics are emitted by Bedrock without any code changes. Access them in
CloudWatch > Metrics > AWS/Bedrock. Dimension: `ModelId`.

| Metric | Unit | What it tells you |
|--------|------|-------------------|
| `InvocationLatency` | ms | How long each API call takes (P50/P90/P99) |
| `InputTokenCount` | Count | Tokens consumed per call — drives cost |
| `OutputTokenCount` | Count | Tokens generated per call — drives cost |
| `InvocationClientErrors` | Count | 4xx errors (bad requests, auth issues) |
| `InvocationServerErrors` | Count | 5xx errors (Bedrock-side failures) |
| `InvocationsThrottled` | Count | Requests rejected due to quota limits |

**Native metrics are per-invocation only.** They do not aggregate by session,
user, or conversation thread. You must build that layer yourself.

---

## What you need to instrument yourself (BedrockPOC namespace)

Bedrock does NOT emit cost metrics. You calculate cost from token counts.

### Cost formula

```python
cost_usd = (input_tokens / 1000 * price_per_1k_input) + \
           (output_tokens / 1000 * price_per_1k_output)
```

Current pricing (us-east-1, on-demand):

| Model | Input (per 1K) | Output (per 1K) |
|-------|----------------|-----------------|
| Claude 3 Haiku | $0.00025 | $0.00125 |
| Claude 3 Sonnet | $0.003 | $0.015 |
| Titan Embed v1 | $0.0001 | — |

---

## Metrics per use case

### Chatbot (multi-turn conversation)

| Metric to track | Source | Notes |
|-----------------|--------|-------|
| Cost per turn | Calculated | input+output tokens × price |
| Cost per session | Aggregated | Sum across all turns |
| Cumulative input tokens | Aggregated | Grows with each turn (context window) |
| Session turn count | App layer | Not in Bedrock |
| Turn latency P99 | CloudWatch | `InvocationLatency` P99 |

**Key insight:** In multi-turn chatbots, input tokens grow with each turn
because the full conversation history is re-sent. A 10-turn session can cost
5–8× more than 10 independent single-turn calls.

**Budget guardrail:** Set a CW Alarm on `InputTokenCount` (Sum, 1-hour period)
to alert before a runaway conversation thread drives up costs.

---

### RAG Chatbot (Knowledge Base + Generation)

| Metric to track | Source | Notes |
|-----------------|--------|-------|
| Embedding cost | Calculated | From Titan InputTokenCount |
| Generation cost | Calculated | Dominant cost driver |
| Retrieval latency | Instrumented | Time to retrieve chunks |
| Generation latency | Instrumented | Time to generate answer |
| Chunks retrieved | Instrumented | From retrieve() results |
| Top chunk relevance score | Instrumented | From retrieve() results |
| Total query cost | Aggregated | embed + generation |

**Key insight:** In RAG, the generation cost dominates because the context
window includes the retrieved chunks. Reducing `numberOfResults` from 5 to 3
typically cuts generation input tokens by ~30–40%.

**Cost split (typical):**
- Embedding: ~2–5% of total RAG query cost
- Generation (with context): ~95–98% of total RAG query cost

**Budget guardrail:** Set a CW Alarm on `RAGTotalQueryCostUSD` (custom metric)
to alert when daily RAG spend exceeds threshold.

---

## CloudWatch setup recommendations

### Alarms to create

```
1. Alarm: TokenBudgetWarning
   Metric:    AWS/Bedrock > InputTokenCount (Sum, 1hr)
   Threshold: > 1,000,000 tokens/hr
   Action:    SNS → notify team

2. Alarm: ThrottleSpike
   Metric:    AWS/Bedrock > InvocationsThrottled (Sum, 5min)
   Threshold: > 10
   Action:    SNS → notify oncall

3. Alarm: HighLatency
   Metric:    AWS/Bedrock > InvocationLatency (P99, 5min)
   Threshold: > 10,000 ms
   Action:    SNS → notify oncall
```

### Dashboard widgets

Recommended CloudWatch dashboard for a Bedrock workload:

1. **Token consumption** — InputTokenCount + OutputTokenCount (line chart, 1hr resolution)
2. **Estimated cost** — custom `ChatbotCostUSD` or `RAGTotalQueryCostUSD` (line chart)
3. **Latency** — InvocationLatency P50/P90/P99 (line chart)
4. **Error rate** — ClientErrors + ServerErrors + Throttled (bar chart)

---

## Cost optimization decision tree

```
Is token volume predictable and high (> break-even)?
  → Yes: Evaluate Provisioned Throughput
  → No:
      Are jobs async / batch-able (summarization, processing)?
        → Yes: Use Batch Inference (50% discount)
        → No: Stay on On-Demand

Is RAG retrieval quality sufficient with fewer chunks?
  → Reduce numberOfResults from 5 → 3 (saves ~30% generation cost)

Is Claude Sonnet necessary, or will Haiku suffice?
  → Haiku is 12× cheaper on input tokens
  → Test quality with Haiku first; only upgrade if needed
```

---

## OpenSearch Serverless cost warning

OpenSearch Serverless (used for RAG vector store) has a **minimum charge of
2 OCUs** regardless of query volume. At $0.24/OCU/hr:

- 1 hour = $0.48
- 8 hours = $3.84
- 1 month = $350

**For POC / testing:** create and delete the collection per session.
**For production:** keep it running only if you have consistent query volume.

Use the `cleanup.py` script to delete the collection immediately after testing.

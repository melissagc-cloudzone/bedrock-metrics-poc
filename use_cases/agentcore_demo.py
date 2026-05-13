"""
AgentCore FinOps Cost Advisor — interactive demo
Requires the agent to be deployed first:
  terraform apply -var="enable_agentcore=true"
  export AGENT_ID=$(terraform output -raw agent_id)
  export AGENT_ALIAS_ID=$(terraform output -raw agent_alias_id)
"""

import os
import uuid
import boto3

AGENT_ID = os.environ["AGENT_ID"]
AGENT_ALIAS_ID = os.environ["AGENT_ALIAS_ID"]
REGION = os.environ.get("REGION", "us-east-1")

client = boto3.client("bedrock-agent-runtime", region_name=REGION)

DEMO_QUESTIONS = [
    "What is our total Bedrock spend in the last 24 hours? Break it down by use case.",
    "Which use cases are generating the most tokens? Show me the CloudWatch metrics for the last 3 hours.",
    "Estimate how much we could save by moving eligible workloads to batch inference.",
    "Should we switch models to save money? Run a model switch analysis.",
    "Give me a FinOps summary: spend, top cost driver, and your #1 recommendation.",
]


def ask(session_id: str, question: str) -> str:
    print(f"\n{'─'*70}")
    print(f"Q: {question}")
    print("─" * 70)

    response = client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=session_id,
        inputText=question,
    )

    answer_parts = []
    for event in response["completion"]:
        if "chunk" in event:
            answer_parts.append(event["chunk"]["bytes"].decode("utf-8"))

    answer = "".join(answer_parts)
    print(f"A: {answer}")
    return answer


def main():
    session_id = str(uuid.uuid4())
    print(f"\nAgentCore FinOps Cost Advisor Demo")
    print(f"Agent ID:   {AGENT_ID}")
    print(f"Alias ID:   {AGENT_ALIAS_ID}")
    print(f"Session:    {session_id}")
    print(f"Region:     {REGION}")

    interactive = os.environ.get("INTERACTIVE", "").lower() in ("1", "true", "yes")

    if interactive:
        print("\nType your question (or 'quit' to exit):\n")
        while True:
            question = input("> ").strip()
            if question.lower() in ("quit", "exit", "q"):
                break
            if question:
                ask(session_id, question)
    else:
        print(f"\nRunning {len(DEMO_QUESTIONS)} demo questions...\n")
        for q in DEMO_QUESTIONS:
            ask(session_id, q)

    print(f"\n{'─'*70}")
    print("Demo complete. Set INTERACTIVE=1 to run in interactive mode.")


if __name__ == "__main__":
    main()

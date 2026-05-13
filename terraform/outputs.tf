output "dynamodb_table_name" {
  value       = aws_dynamodb_table.usage_log.name
  description = "DynamoDB audit trail table — query this for per-call chargeback data"
}

output "dynamodb_table_arn" {
  value = aws_dynamodb_table.usage_log.arn
}

output "cloudwatch_dashboard_url" {
  value       = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${local.project}"
  description = "Direct link to the CloudWatch dashboard"
}

output "sns_topic_arn" {
  value       = aws_sns_topic.alerts.arn
  description = "SNS topic receiving all CloudWatch alarm notifications"
}

output "knowledge_base_id" {
  value       = var.enable_rag ? aws_bedrockagent_knowledge_base.main[0].id : "RAG not enabled — set enable_rag=true"
  description = "Bedrock Knowledge Base ID — export as BEDROCK_KB_ID before running rag_chatbot.py"
}

output "kb_s3_bucket" {
  value       = var.enable_rag ? aws_s3_bucket.kb_docs[0].bucket : "RAG not enabled"
  description = "S3 bucket for Knowledge Base source documents"
}

output "agent_id" {
  value       = var.enable_agentcore ? aws_bedrockagent_agent.cost_advisor[0].agent_id : "AgentCore not enabled — set enable_agentcore=true"
  description = "Bedrock Agent ID — export as AGENT_ID before running agentcore_demo.py"
}

output "agent_alias_id" {
  value       = var.enable_agentcore ? aws_bedrockagent_agent_alias.cost_advisor[0].agent_alias_id : "AgentCore not enabled"
  description = "Bedrock Agent Alias ID — export as AGENT_ALIAS_ID before running agentcore_demo.py"
}

output "next_steps" {
  value = <<-EOT

    ── Infrastructure ready. Run the workload scripts: ──────────────────────

      cd ..
      python use_cases/chatbot_sim.py
      python use_cases/dynamodb_logger.py

      # Wait ~2 min for CloudWatch to ingest, then:
      python metrics/cloudwatch_reader.py
      python metrics/cost_report.py

    %{if var.enable_rag}
      # RAG — export KB ID first:
      export BEDROCK_KB_ID=${aws_bedrockagent_knowledge_base.main[0].id}
      python use_cases/rag_chatbot.py
    %{endif}

    %{if var.enable_agentcore}
      # AgentCore Cost Advisor — export agent IDs first:
      export AGENT_ID=${aws_bedrockagent_agent.cost_advisor[0].agent_id}
      export AGENT_ALIAS_ID=${aws_bedrockagent_agent_alias.cost_advisor[0].agent_alias_id}
      python use_cases/agentcore_demo.py
    %{endif}

    ── Tear down everything when done: ──────────────────────────────────────

      terraform destroy${var.enable_rag ? " -var=\"enable_rag=true\"" : ""}${var.enable_agentcore ? " -var=\"enable_agentcore=true\"" : ""}

    ─────────────────────────────────────────────────────────────────────────
  EOT
}

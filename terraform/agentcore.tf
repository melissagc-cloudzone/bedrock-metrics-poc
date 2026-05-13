# AgentCore POC — FinOps Cost Advisor Agent
#
# Usage:
#   terraform apply -var="enable_agentcore=true"
#   terraform output agent_id          → export AGENT_ID=...
#   terraform output agent_alias_id    → export AGENT_ALIAS_ID=...
#   python use_cases/agentcore_demo.py
#   terraform destroy -var="enable_agentcore=true"
#
# The agent queries the DynamoDB audit trail and CloudWatch metrics
# from the main POC run, so run ./run_poc.sh first to populate data.

# ── IAM role for the Bedrock Agent ───────────────────────────────────────────

resource "aws_iam_role" "agent" {
  count = var.enable_agentcore ? 1 : 0
  name  = "${local.project}-agent-role"
  tags  = local.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
      }
    }]
  })
}

resource "aws_iam_role_policy" "agent" {
  count = var.enable_agentcore ? 1 : 0
  name  = "${local.project}-agent-policy"
  role  = aws_iam_role.agent[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = "arn:aws:bedrock:${var.region}::foundation-model/us.amazon.nova-lite-v1:0"
      },
      {
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.query_audit_trail[0].arn,
          aws_lambda_function.get_metrics[0].arn,
          aws_lambda_function.estimate_savings[0].arn,
        ]
      }
    ]
  })
}

# ── Bedrock Agent ─────────────────────────────────────────────────────────────

resource "aws_bedrockagent_agent" "cost_advisor" {
  count                       = var.enable_agentcore ? 1 : 0
  agent_name                  = "${local.project}-cost-advisor"
  agent_resource_role_arn     = aws_iam_role.agent[0].arn
  foundation_model            = "us.amazon.nova-lite-v1:0"
  idle_session_ttl_in_seconds = 600
  tags                        = local.tags

  instruction = <<-EOT
    You are a FinOps cost advisor specialized in Amazon Bedrock AI workloads.
    You help engineering and finance teams understand their AI spending and find savings.

    You have three tools:
    - query_audit_trail: reads the DynamoDB audit trail for cost breakdown by use_case, model, and time
    - get_metrics: reads CloudWatch for token counts, latency, and error rates
    - estimate_savings: calculates potential savings from batch inference or model switching

    Guidelines:
    - Always query audit_trail first when asked about costs
    - Present numbers in USD with use-case breakdowns
    - Flag anything above $0.001 per call as worth investigating at scale
    - End every response with one concrete, prioritized optimization action
    - Keep answers concise — bullet points over paragraphs
  EOT

  depends_on = [aws_iam_role_policy.agent]
}

resource "aws_bedrockagent_agent_alias" "cost_advisor" {
  count            = var.enable_agentcore ? 1 : 0
  agent_id         = aws_bedrockagent_agent.cost_advisor[0].agent_id
  agent_alias_name = "live"
  tags             = local.tags

  depends_on = [
    aws_bedrockagent_agent_action_group.query_audit_trail,
    aws_bedrockagent_agent_action_group.get_metrics,
    aws_bedrockagent_agent_action_group.estimate_savings,
  ]
}

# ── Action Group: QueryAuditTrail ─────────────────────────────────────────────

resource "aws_bedrockagent_agent_action_group" "query_audit_trail" {
  count                      = var.enable_agentcore ? 1 : 0
  agent_id                   = aws_bedrockagent_agent.cost_advisor[0].agent_id
  agent_version              = "DRAFT"
  action_group_name          = "QueryAuditTrail"
  description                = "Query the DynamoDB audit trail for per-call Bedrock cost data, filtered by use_case or time window"
  skip_resource_in_use_check = true

  action_group_executor {
    lambda = aws_lambda_function.query_audit_trail[0].arn
  }

  api_schema {
    payload = jsonencode({
      openapi = "3.0.0"
      info    = { title = "QueryAuditTrail", version = "1.0.0" }
      paths = {
        "/query_costs" = {
          get = {
            operationId = "queryCosts"
            description = "Query Bedrock usage costs from DynamoDB audit trail. Returns total cost, record count, and breakdown by use_case."
            parameters = [
              {
                name        = "use_case"
                in          = "query"
                required    = false
                description = "Filter by use case: chatbot, summarize, classification, or all"
                schema      = { type = "string" }
              },
              {
                name        = "hours"
                in          = "query"
                required    = false
                description = "Number of hours to look back. Default: 24"
                schema      = { type = "integer" }
              }
            ]
            responses = {
              "200" = {
                description = "Cost breakdown by use case"
                content = {
                  "application/json" = {
                    schema = {
                      type = "object"
                      properties = {
                        total_cost   = { type = "number" }
                        record_count = { type = "integer" }
                        hours_queried = { type = "integer" }
                        by_use_case  = { type = "object" }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    })
  }
}

# ── Action Group: GetCloudWatchMetrics ────────────────────────────────────────

resource "aws_bedrockagent_agent_action_group" "get_metrics" {
  count                      = var.enable_agentcore ? 1 : 0
  agent_id                   = aws_bedrockagent_agent.cost_advisor[0].agent_id
  agent_version              = "DRAFT"
  action_group_name          = "GetCloudWatchMetrics"
  description                = "Retrieve native Bedrock CloudWatch metrics: input/output token counts, invocation latency, errors, throttles"
  skip_resource_in_use_check = true

  action_group_executor {
    lambda = aws_lambda_function.get_metrics[0].arn
  }

  api_schema {
    payload = jsonencode({
      openapi = "3.0.0"
      info    = { title = "GetMetrics", version = "1.0.0" }
      paths = {
        "/get_metrics" = {
          get = {
            operationId = "getMetrics"
            description = "Get CloudWatch metrics for Bedrock. Returns token counts, latency, errors from both AWS/Bedrock and BedrockPOC namespaces."
            parameters = [
              {
                name        = "hours"
                in          = "query"
                required    = false
                description = "Number of hours to look back. Default: 3"
                schema      = { type = "integer" }
              }
            ]
            responses = {
              "200" = {
                description = "CloudWatch metric values"
                content = {
                  "application/json" = {
                    schema = {
                      type = "object"
                      properties = {
                        native_bedrock = { type = "object" }
                        custom_poc     = { type = "object" }
                        window_hours   = { type = "integer" }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    })
  }
}

# ── Action Group: EstimateSavings ─────────────────────────────────────────────

resource "aws_bedrockagent_agent_action_group" "estimate_savings" {
  count                      = var.enable_agentcore ? 1 : 0
  agent_id                   = aws_bedrockagent_agent.cost_advisor[0].agent_id
  agent_version              = "DRAFT"
  action_group_name          = "EstimateSavings"
  description                = "Estimate potential savings from batch_inference (50% discount on async workloads) or model_switch analysis"
  skip_resource_in_use_check = true

  action_group_executor {
    lambda = aws_lambda_function.estimate_savings[0].arn
  }

  api_schema {
    payload = jsonencode({
      openapi = "3.0.0"
      info    = { title = "EstimateSavings", version = "1.0.0" }
      paths = {
        "/estimate_savings" = {
          get = {
            operationId = "estimateSavings"
            description = "Calculate projected monthly savings from a given optimization strategy based on recent DynamoDB usage data."
            parameters = [
              {
                name        = "strategy"
                in          = "query"
                required    = true
                description = "Optimization strategy to evaluate: batch_inference or model_switch"
                schema      = { type = "string", enum = ["batch_inference", "model_switch"] }
              },
              {
                name        = "hours"
                in          = "query"
                required    = false
                description = "Hours of historical data to base the projection on. Default: 24"
                schema      = { type = "integer" }
              }
            ]
            responses = {
              "200" = {
                description = "Savings estimate with recommendation"
                content = {
                  "application/json" = {
                    schema = {
                      type = "object"
                      properties = {
                        strategy             = { type = "string" }
                        current_monthly_cost = { type = "number" }
                        estimated_saving_usd = { type = "number" }
                        saving_percentage    = { type = "number" }
                        recommendation       = { type = "string" }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    })
  }
}

# ── Lambda invoke permissions for Bedrock Agent ───────────────────────────────

resource "aws_lambda_permission" "query_audit_trail" {
  count         = var.enable_agentcore ? 1 : 0
  statement_id  = "AllowBedrockAgent"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.query_audit_trail[0].function_name
  principal     = "bedrock.amazonaws.com"
  source_arn    = "${aws_bedrockagent_agent.cost_advisor[0].agent_arn}/*"
}

resource "aws_lambda_permission" "get_metrics" {
  count         = var.enable_agentcore ? 1 : 0
  statement_id  = "AllowBedrockAgent"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_metrics[0].function_name
  principal     = "bedrock.amazonaws.com"
  source_arn    = "${aws_bedrockagent_agent.cost_advisor[0].agent_arn}/*"
}

resource "aws_lambda_permission" "estimate_savings" {
  count         = var.enable_agentcore ? 1 : 0
  statement_id  = "AllowBedrockAgent"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.estimate_savings[0].function_name
  principal     = "bedrock.amazonaws.com"
  source_arn    = "${aws_bedrockagent_agent.cost_advisor[0].agent_arn}/*"
}

# ── SNS topic for alarm notifications ───────────────────────────────────────

resource "aws_sns_topic" "alerts" {
  name = "${local.project}-alerts"
  tags = local.tags
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
  # AWS sends a confirmation email — subscription is pending until confirmed.
}

# ── CloudWatch alarms ────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "token_budget" {
  alarm_name          = "${local.project}-token-budget-warning"
  alarm_description   = "Input token volume exceeds 1M/hr — review for cost runaway"
  namespace           = "AWS/Bedrock"
  metric_name         = "InputTokenCount"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 1000000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  tags                = local.tags
}

resource "aws_cloudwatch_metric_alarm" "throttle_spike" {
  alarm_name          = "${local.project}-throttle-spike"
  alarm_description   = "More than 10 throttled requests in 5 minutes — quota may need review"
  namespace           = "AWS/Bedrock"
  metric_name         = "InvocationsThrottled"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  tags                = local.tags
}

resource "aws_cloudwatch_metric_alarm" "high_latency" {
  alarm_name          = "${local.project}-high-latency"
  alarm_description   = "P99 invocation latency over 10 seconds"
  namespace           = "AWS/Bedrock"
  metric_name         = "InvocationLatency"
  extended_statistic  = "p99"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  tags                = local.tags
}

# ── CloudWatch dashboard ─────────────────────────────────────────────────────

resource "aws_cloudwatch_dashboard" "bedrock" {
  dashboard_name = local.project

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Token Consumption (Input + Output)"
          region = var.region
          period = 3600
          stat   = "Sum"
          view   = "timeSeries"
          metrics = [
            ["AWS/Bedrock", "InputTokenCount"],
            ["AWS/Bedrock", "OutputTokenCount"]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Estimated Cost (USD) — Custom Metrics"
          region = var.region
          period = 3600
          stat   = "Sum"
          view   = "timeSeries"
          metrics = [
            ["BedrockPOC", "ChatbotSessionCostUSD"],
            ["BedrockPOC", "AuditTrailCostUSD"],
            ["BedrockPOC", "RAGTotalQueryCostUSD"]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Invocation Latency (P50 / P90 / P99)"
          region = var.region
          period = 300
          view   = "timeSeries"
          metrics = [
            ["AWS/Bedrock", "InvocationLatency", { "stat" : "p50", "label" : "P50" }],
            ["AWS/Bedrock", "InvocationLatency", { "stat" : "p90", "label" : "P90" }],
            ["AWS/Bedrock", "InvocationLatency", { "stat" : "p99", "label" : "P99" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Errors & Throttles"
          region = var.region
          period = 300
          stat   = "Sum"
          view   = "bar"
          metrics = [
            ["AWS/Bedrock", "InvocationClientErrors"],
            ["AWS/Bedrock", "InvocationServerErrors"],
            ["AWS/Bedrock", "InvocationsThrottled"]
          ]
        }
      }
    ]
  })
}

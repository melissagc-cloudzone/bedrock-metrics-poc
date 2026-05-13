# Lambda functions backing the AgentCore action groups.
# Each function is a single Python file zipped at plan time.

# ── Shared IAM role for all three Lambda functions ────────────────────────────

resource "aws_iam_role" "agent_lambda" {
  count = var.enable_agentcore ? 1 : 0
  name  = "${local.project}-agent-lambda-role"
  tags  = local.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "agent_lambda_basic" {
  count      = var.enable_agentcore ? 1 : 0
  role       = aws_iam_role.agent_lambda[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "agent_lambda" {
  count = var.enable_agentcore ? 1 : 0
  name  = "${local.project}-agent-lambda-policy"
  role  = aws_iam_role.agent_lambda[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Scan", "dynamodb:Query", "dynamodb:GetItem"]
        Resource = aws_dynamodb_table.usage_log.arn
      },
      {
        Effect   = "Allow"
        Action   = ["cloudwatch:GetMetricStatistics", "cloudwatch:ListMetrics"]
        Resource = "*"
      }
    ]
  })
}

# ── Zip archives from source files ───────────────────────────────────────────

data "archive_file" "query_audit_trail" {
  count       = var.enable_agentcore ? 1 : 0
  type        = "zip"
  source_file = "${path.module}/lambda_src/query_audit_trail.py"
  output_path = "${path.module}/lambda_zip/query_audit_trail.zip"
}

data "archive_file" "get_metrics" {
  count       = var.enable_agentcore ? 1 : 0
  type        = "zip"
  source_file = "${path.module}/lambda_src/get_metrics.py"
  output_path = "${path.module}/lambda_zip/get_metrics.zip"
}

data "archive_file" "estimate_savings" {
  count       = var.enable_agentcore ? 1 : 0
  type        = "zip"
  source_file = "${path.module}/lambda_src/estimate_savings.py"
  output_path = "${path.module}/lambda_zip/estimate_savings.zip"
}

# ── Lambda functions ──────────────────────────────────────────────────────────

resource "aws_lambda_function" "query_audit_trail" {
  count            = var.enable_agentcore ? 1 : 0
  function_name    = "${local.project}-query-audit-trail"
  filename         = data.archive_file.query_audit_trail[0].output_path
  source_code_hash = data.archive_file.query_audit_trail[0].output_base64sha256
  role             = aws_iam_role.agent_lambda[0].arn
  handler          = "query_audit_trail.handler"
  runtime          = "python3.12"
  timeout          = 30
  tags             = local.tags

  environment {
    variables = {
      REGION     = var.region
      TABLE_NAME = aws_dynamodb_table.usage_log.name
    }
  }
}

resource "aws_lambda_function" "get_metrics" {
  count            = var.enable_agentcore ? 1 : 0
  function_name    = "${local.project}-get-metrics"
  filename         = data.archive_file.get_metrics[0].output_path
  source_code_hash = data.archive_file.get_metrics[0].output_base64sha256
  role             = aws_iam_role.agent_lambda[0].arn
  handler          = "get_metrics.handler"
  runtime          = "python3.12"
  timeout          = 30
  tags             = local.tags

  environment {
    variables = {
      REGION = var.region
    }
  }
}

resource "aws_lambda_function" "estimate_savings" {
  count            = var.enable_agentcore ? 1 : 0
  function_name    = "${local.project}-estimate-savings"
  filename         = data.archive_file.estimate_savings[0].output_path
  source_code_hash = data.archive_file.estimate_savings[0].output_base64sha256
  role             = aws_iam_role.agent_lambda[0].arn
  handler          = "estimate_savings.handler"
  runtime          = "python3.12"
  timeout          = 30
  tags             = local.tags

  environment {
    variables = {
      REGION     = var.region
      TABLE_NAME = aws_dynamodb_table.usage_log.name
    }
  }
}

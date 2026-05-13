terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.5"
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}

locals {
  project = "bedrock-metrics-poc"
  tags = {
    Project     = local.project
    Owner       = var.owner
    Environment = var.environment
    AutoDelete  = "yes"
  }
}

# ── DynamoDB audit trail ─────────────────────────────────────────────────────
# Stores every Bedrock call: model, tokens, cost, latency, use_case, tags.
# PAY_PER_REQUEST = $0 while idle. Replaces the create_table_if_not_exists()
# call in dynamodb_logger.py — Python will find the table already here.

resource "aws_dynamodb_table" "usage_log" {
  name         = "bedrock-poc-usage-log"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "call_id"

  attribute {
    name = "call_id"
    type = "S"
  }

  tags = local.tags
}

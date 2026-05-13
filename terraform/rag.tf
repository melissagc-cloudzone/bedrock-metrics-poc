# RAG infrastructure — only deployed when var.enable_rag = true
# Requires iam:CreateRole. Not available under PowerUserAccess.
#
# Usage:
#   terraform apply -var="enable_rag=true"
#   terraform destroy -var="enable_rag=true"

# ── S3 bucket for knowledge base documents ───────────────────────────────────

resource "aws_s3_bucket" "kb_docs" {
  count  = var.enable_rag ? 1 : 0
  bucket = "${local.project}-kb-docs-${data.aws_caller_identity.current.account_id}"
  tags   = local.tags
}

resource "aws_s3_bucket_public_access_block" "kb_docs" {
  count                   = var.enable_rag ? 1 : 0
  bucket                  = aws_s3_bucket.kb_docs[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── OpenSearch Serverless ─────────────────────────────────────────────────────
# Minimum charge: 2 OCUs = $0.48/hr regardless of query volume.
# Create and destroy per session to avoid unexpected charges.

resource "aws_opensearchserverless_security_policy" "encryption" {
  count = var.enable_rag ? 1 : 0
  name  = "${local.project}-enc"
  type  = "encryption"
  policy = jsonencode({
    Rules       = [{ ResourceType = "collection", Resource = ["collection/${local.project}"] }]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_security_policy" "network" {
  count = var.enable_rag ? 1 : 0
  name  = "${local.project}-net"
  type  = "network"
  policy = jsonencode([{
    Rules = [
      { ResourceType = "collection", Resource = ["collection/${local.project}"] },
      { ResourceType = "dashboard", Resource = ["collection/${local.project}"] }
    ]
    AllowFromPublic = true
  }])
}

resource "aws_opensearchserverless_collection" "kb" {
  count = var.enable_rag ? 1 : 0
  name  = local.project
  type  = "VECTORSEARCH"
  tags  = local.tags

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
  ]
}

# ── IAM role for Bedrock Knowledge Base ──────────────────────────────────────

resource "aws_iam_role" "bedrock_kb" {
  count = var.enable_rag ? 1 : 0
  name  = "${local.project}-kb-role"
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

resource "aws_iam_role_policy" "bedrock_kb" {
  count = var.enable_rag ? 1 : 0
  name  = "${local.project}-kb-policy"
  role  = aws_iam_role.bedrock_kb[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.kb_docs[0].arn,
          "${aws_s3_bucket.kb_docs[0].arn}/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["aoss:APIAccessAll"]
        Resource = aws_opensearchserverless_collection.kb[0].arn
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = "arn:aws:bedrock:${var.region}::foundation-model/amazon.titan-embed-text-v2:0"
      }
    ]
  })
}

# ── OpenSearch access policy (grants KB role + account root) ─────────────────

resource "aws_opensearchserverless_access_policy" "kb" {
  count = var.enable_rag ? 1 : 0
  name  = "${local.project}-access"
  type  = "data"
  policy = jsonencode([{
    Rules = [
      {
        ResourceType = "index"
        Resource     = ["index/${local.project}/*"]
        Permission   = ["aoss:*"]
      },
      {
        ResourceType = "collection"
        Resource     = ["collection/${local.project}"]
        Permission   = ["aoss:*"]
      }
    ]
    Principal = [
      aws_iam_role.bedrock_kb[0].arn,
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
    ]
  }])
}

# ── Bedrock Knowledge Base ────────────────────────────────────────────────────

resource "aws_bedrockagent_knowledge_base" "main" {
  count    = var.enable_rag ? 1 : 0
  name     = local.project
  role_arn = aws_iam_role.bedrock_kb[0].arn
  tags     = local.tags

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${var.region}::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.kb[0].arn
      vector_index_name = "bedrock-kb-index"
      field_mapping {
        vector_field   = "bedrock-knowledge-base-default-vector"
        text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
        metadata_field = "AMAZON_BEDROCK_METADATA"
      }
    }
  }

  depends_on = [aws_opensearchserverless_access_policy.kb]
}

resource "aws_bedrockagent_data_source" "main" {
  count             = var.enable_rag ? 1 : 0
  knowledge_base_id = aws_bedrockagent_knowledge_base.main[0].id
  name              = "${local.project}-docs"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = aws_s3_bucket.kb_docs[0].arn
    }
  }
}

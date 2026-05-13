variable "region" {
  type    = string
  default = "us-east-1"
}

variable "owner" {
  type    = string
  default = "melissa"
}

variable "environment" {
  type    = string
  default = "playground"
}

variable "enable_rag" {
  type        = bool
  default     = false
  description = "Set to true to deploy RAG infrastructure (S3, OpenSearch, IAM, Knowledge Base). Requires iam:CreateRole."
}

variable "alert_email" {
  type        = string
  default     = ""
  description = "Email address for CloudWatch alarm notifications. Leave empty to skip subscription."
}

# ── Knowledge Base モジュール ────────────────────────────────────────────────
# Bedrock Knowledge Bases + S3 データソース

locals {
  name_prefix = "${var.project}-${var.environment}"
}

# ── S3 バケット（ドキュメント格納） ─────────────
resource "aws_s3_bucket" "docs" {
  bucket = "${local.name_prefix}-docs-${var.account_id}"
}

resource "aws_s3_bucket_versioning" "docs" {
  bucket = aws_s3_bucket.docs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "docs" {
  bucket = aws_s3_bucket.docs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "docs" {
  bucket                  = aws_s3_bucket.docs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── Bedrock Knowledge Base 用 IAM ロール ─────────
resource "aws_iam_role" "bedrock_kb" {
  name = "${local.name_prefix}-bedrock-kb-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = var.account_id
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "bedrock_kb" {
  name = "${local.name_prefix}-bedrock-kb-policy"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvokeModel"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model_id}"
        ]
      },
      {
        Sid    = "S3Access"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.docs.arn,
          "${aws_s3_bucket.docs.arn}/*"
        ]
      },
      {
        Sid    = "OpenSearchAccess"
        Effect = "Allow"
        Action = ["aoss:APIAccessAll"]
        Resource = [var.collection_arn]
      }
    ]
  })
}

# ── Bedrock Knowledge Base ───────────────────────
resource "aws_bedrockagent_knowledge_base" "main" {
  name     = "${local.name_prefix}-kb"
  role_arn = aws_iam_role.bedrock_kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_embedding_model_id}"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = var.collection_arn
      vector_index_name = "bedrock-knowledge-base-default-index"
      field_mapping {
        vector_field   = "bedrock-knowledge-base-default-vector"
        text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
        metadata_field = "AMAZON_BEDROCK_METADATA"
      }
    }
  }
}

# ── S3 データソース ──────────────────────────────
resource "aws_bedrockagent_data_source" "s3" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.main.id
  name              = "${local.name_prefix}-s3-datasource"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = aws_s3_bucket.docs.arn
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 300
        overlap_percentage = 20
      }
    }
  }
}

# ── SSM Parameter Store ──────────────────────────
resource "aws_ssm_parameter" "knowledge_base_id" {
  name  = "/${var.project}/${var.environment}/knowledge_base_id"
  type  = "String"
  value = aws_bedrockagent_knowledge_base.main.id
}

resource "aws_ssm_parameter" "s3_bucket_name" {
  name  = "/${var.project}/${var.environment}/s3_bucket_name"
  type  = "String"
  value = aws_s3_bucket.docs.bucket
}

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }

  # ローカル state（PoC 用途）
  # 本番化する際は S3 バックエンドに切り替える
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# ── データソース ────────────────────────────────
data "aws_caller_identity" "current" {}

# ── OpenSearch Serverless モジュール ────────────
module "opensearch" {
  source = "../../modules/opensearch"

  project     = var.project
  environment = var.environment
  account_id  = data.aws_caller_identity.current.account_id
}

# ── Knowledge Base モジュール ───────────────────
module "knowledge_base" {
  source = "../../modules/knowledge_base"

  project                    = var.project
  environment                = var.environment
  account_id                 = data.aws_caller_identity.current.account_id
  collection_arn             = module.opensearch.collection_arn
  bedrock_embedding_model_id = var.bedrock_embedding_model_id

  depends_on = [module.opensearch]
}

# ── Lambda + API Gateway モジュール ─────────────
module "lambda" {
  source = "../../modules/lambda"

  project                     = var.project
  environment                 = var.environment
  knowledge_base_id           = module.knowledge_base.knowledge_base_id
  bedrock_generation_model_id = var.bedrock_generation_model_id

  depends_on = [module.knowledge_base]
}

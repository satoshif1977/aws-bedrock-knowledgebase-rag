variable "project" {
  description = "プロジェクト名"
  type        = string
  default     = "bedrock-kb-rag"
}

variable "environment" {
  description = "環境名"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWSリージョン"
  type        = string
  default     = "ap-northeast-1"
}

variable "bedrock_embedding_model_id" {
  description = "埋め込みモデルID"
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "bedrock_generation_model_id" {
  description = "回答生成モデルID"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

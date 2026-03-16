variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "account_id" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "ap-northeast-1"
}

variable "collection_arn" {
  type = string
}

variable "bedrock_embedding_model_id" {
  type = string
}

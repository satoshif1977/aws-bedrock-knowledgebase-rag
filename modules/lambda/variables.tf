variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "knowledge_base_id" {
  type = string
}

variable "bedrock_generation_model_id" {
  type = string
}

variable "log_level" {
  description = "Lambda の構造化ログ出力レベル（debug / info / warn / error）"
  type        = string
  default     = "info"

  validation {
    condition     = contains(["debug", "info", "warn", "error"], var.log_level)
    error_message = "log_level は debug / info / warn / error のいずれかを指定してください。"
  }
}

variable "metrics_namespace" {
  description = "EMF メトリクスの CloudWatch 名前空間"
  type        = string
  default     = "BedrockKbRag"
}

variable "metrics_enabled" {
  description = "EMF メトリクスの出力可否（false にすると出力しない）"
  type        = bool
  default     = true
}

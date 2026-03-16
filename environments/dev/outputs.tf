output "s3_bucket_name" {
  description = "ドキュメント格納 S3 バケット名"
  value       = module.knowledge_base.s3_bucket_name
}

output "knowledge_base_id" {
  description = "Bedrock Knowledge Base ID"
  value       = module.knowledge_base.knowledge_base_id
}

output "api_gateway_url" {
  description = "API Gateway エンドポイント URL"
  value       = module.lambda.api_gateway_url
}

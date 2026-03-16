output "collection_arn" {
  description = "OpenSearch Serverless コレクション ARN"
  value       = aws_opensearchserverless_collection.main.arn
}

output "collection_endpoint" {
  description = "OpenSearch Serverless コレクションエンドポイント"
  value       = aws_opensearchserverless_collection.main.collection_endpoint
}

output "collection_name" {
  description = "コレクション名"
  value       = aws_opensearchserverless_collection.main.name
}

output "knowledge_base_id" {
  value = aws_bedrockagent_knowledge_base.main.id
}

output "s3_bucket_name" {
  value = aws_s3_bucket.docs.bucket
}

output "data_source_id" {
  value = aws_bedrockagent_data_source.s3.data_source_id
}

output "api_gateway_url" {
  description = "API Gateway エンドポイント URL"
  value       = "${aws_api_gateway_stage.dev.invoke_url}/query"
}

output "lambda_function_name" {
  description = "Lambda 関数名"
  value       = aws_lambda_function.query_handler.function_name
}

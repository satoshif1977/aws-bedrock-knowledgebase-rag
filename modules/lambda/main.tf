# ── Lambda + API Gateway モジュール ─────────────────────────────────────────

locals {
  name_prefix          = "${var.project}-${var.environment}"
  lambda_function_name = "${local.name_prefix}-query-handler"
  generation_model_arn = "arn:aws:bedrock:ap-northeast-1::foundation-model/${var.bedrock_generation_model_id}"
}

# ── Lambda 実行ロール ────────────────────────────
resource "aws_iam_role" "lambda" {
  name = "${local.lambda_function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name = "${local.lambda_function_name}-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockAccess"
        Effect = "Allow"
        Action = [
          "bedrock:RetrieveAndGenerate",
          "bedrock:Retrieve",
          "bedrock:InvokeModel",
        ]
        Resource = "*"
      },
      {
        Sid    = "BedrockAgentRuntime"
        Effect = "Allow"
        Action = ["bedrock-agent-runtime:RetrieveAndGenerate"]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# ── CloudWatch Logs ──────────────────────────────
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.lambda_function_name}"
  retention_in_days = 3
}

# ── Lambda ZIP パッケージ ────────────────────────
data "archive_file" "lambda" {
  type        = "zip"
  source_file = "${path.root}/../../lambda/query_handler.py"
  output_path = "${path.module}/query_handler.zip"
}

# ── Lambda 関数 ──────────────────────────────────
resource "aws_lambda_function" "query_handler" {
  function_name    = local.lambda_function_name
  role             = aws_iam_role.lambda.arn
  handler          = "query_handler.lambda_handler"
  runtime          = "python3.11"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      KNOWLEDGE_BASE_ID    = var.knowledge_base_id
      GENERATION_MODEL_ARN = local.generation_model_arn
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# ── API Gateway (REST) ───────────────────────────
resource "aws_api_gateway_rest_api" "main" {
  name = "${local.name_prefix}-api"

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "query" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "query"
}

resource "aws_api_gateway_method" "post" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.query.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "lambda" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.query.id
  http_method             = aws_api_gateway_method.post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.query_handler.invoke_arn
}

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  depends_on = [aws_api_gateway_integration.lambda]

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "dev" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  deployment_id = aws_api_gateway_deployment.main.id
  stage_name    = var.environment
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.query_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

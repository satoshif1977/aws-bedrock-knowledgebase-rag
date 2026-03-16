# ── OpenSearch Serverless モジュール ────────────────────────────────────────
# Bedrock Knowledge Bases のベクトルストアとして使用する
# コレクションタイプ: VECTORSEARCH（セマンティック検索用）

locals {
  name_prefix = "${var.project}-${var.environment}"
  # OpenSearch Serverless のコレクション名は小文字英数字とハイフンのみ
  collection_name = "${local.name_prefix}-kb"
}

# ── 暗号化ポリシー ───────────────────────────────
resource "aws_opensearchserverless_security_policy" "encryption" {
  name = "${local.name_prefix}-enc"
  type = "encryption"

  policy = jsonencode({
    Rules = [
      {
        Resource     = ["collection/${local.collection_name}"]
        ResourceType = "collection"
      }
    ]
    AWSOwnedKey = true
  })
}

# ── ネットワークポリシー ─────────────────────────
resource "aws_opensearchserverless_security_policy" "network" {
  name = "${local.name_prefix}-net"
  type = "network"

  policy = jsonencode([
    {
      Rules = [
        {
          Resource     = ["collection/${local.collection_name}"]
          ResourceType = "collection"
        },
        {
          Resource     = ["collection/${local.collection_name}"]
          ResourceType = "dashboard"
        }
      ]
      AllowFromPublic = true
    }
  ])
}

# ── データアクセスポリシー ───────────────────────
resource "aws_opensearchserverless_access_policy" "data" {
  name = "${local.name_prefix}-data"
  type = "data"

  policy = jsonencode([
    {
      Rules = [
        {
          Resource = ["collection/${local.collection_name}"]
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:DeleteCollectionItems",
            "aoss:UpdateCollectionItems",
            "aoss:DescribeCollectionItems"
          ]
          ResourceType = "collection"
        },
        {
          Resource = ["index/${local.collection_name}/*"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex",
            "aoss:UpdateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument"
          ]
          ResourceType = "index"
        }
      ]
      Principal = [
        "arn:aws:iam::${var.account_id}:root"
      ]
    }
  ])
}

# ── OpenSearch Serverless コレクション ───────────
resource "aws_opensearchserverless_collection" "main" {
  name = local.collection_name
  type = "VECTORSEARCH"

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
    aws_opensearchserverless_access_policy.data,
  ]
}

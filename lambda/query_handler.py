"""
Bedrock Knowledge Bases RAG クエリハンドラー
RetrieveAndGenerate API を使用してドキュメントから回答を生成する
"""
import json
import logging
import os

import boto3

# ── ロガー設定 ───────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── クライアント初期化 ───────────────────────────
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name="ap-northeast-1")

# ── 環境変数 ─────────────────────────────────────
KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
GENERATION_MODEL_ARN = os.environ["GENERATION_MODEL_ARN"]


def lambda_handler(event: dict, context) -> dict:
    """API Gateway からのリクエストを処理して回答を返す"""
    logger.info("event: %s", json.dumps(event))

    try:
        body = json.loads(event.get("body", "{}"))
        query = body.get("query", "").strip()

        if not query:
            return _response(400, {"error": "query は必須です"})

        answer, citations = _retrieve_and_generate(query)

        return _response(200, {
            "query": query,
            "answer": answer,
            "citations": citations,
        })

    except Exception as e:
        logger.exception("エラーが発生しました: %s", e)
        return _response(500, {"error": "内部エラーが発生しました"})


def _retrieve_and_generate(query: str) -> tuple[str, list]:
    """Bedrock Knowledge Bases の RetrieveAndGenerate API を呼び出す"""
    response = bedrock_agent_runtime.retrieve_and_generate(
        input={"text": query},
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                "modelArn": GENERATION_MODEL_ARN,
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {
                        "numberOfResults": 5,
                    }
                },
                "generationConfiguration": {
                    "promptTemplate": {
                        "textPromptTemplate": (
                            "以下の参考情報をもとに、質問に対して日本語で丁寧に回答してください。\n"
                            "参考情報に記載がない場合は「資料に情報がありません」と答えてください。\n\n"
                            "$search_results$\n\n"
                            "質問: $query$"
                        )
                    }
                },
            },
        },
    )

    answer = response["output"]["text"]
    citations = [
        {
            "text": ref.get("content", {}).get("text", ""),
            "source": ref.get("location", {}).get("s3Location", {}).get("uri", ""),
        }
        for citation in response.get("citations", [])
        for ref in citation.get("retrievedReferences", [])
    ]

    return answer, citations


def _response(status_code: int, body: dict) -> dict:
    """API Gateway レスポンスを組み立てる"""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }

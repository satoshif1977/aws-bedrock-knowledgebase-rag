"""
Bedrock Knowledge Bases RAG クエリハンドラー
- mode=rag    : RetrieveAndGenerate API（sessionId による multi-turn 会話対応）
- mode=retrieve: Retrieve API（スコア付き検索結果のみ返す・生成なし）

メタデータフィルター:
  リクエスト body に "filter" キーで Bedrock KB フィルター式を渡す。
  例: {"equals": {"key": "category", "value": "hr"}}
  例: {"startsWith": {"key": "title", "value": "社内規程"}}
  例: {"andAll": [{"equals": {...}}, {"greaterThanOrEquals": {...}}]}
"""

import json
import logging
import os
from typing import Any

import boto3

# ── ロガー設定 ───────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── クライアント初期化 ───────────────────────────
bedrock_agent_runtime = boto3.client(
    "bedrock-agent-runtime",
    region_name=os.environ.get("AWS_REGION", "ap-northeast-1"),
)


# ── 環境変数（起動時バリデーション） ──────────────
def _require_env(key: str) -> str:
    """必須環境変数を取得し、未設定の場合は起動時に RuntimeError を発生させる"""
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"必須環境変数 {key!r} が設定されていません")
    return value


KNOWLEDGE_BASE_ID = _require_env("KNOWLEDGE_BASE_ID")
GENERATION_MODEL_ARN = _require_env("GENERATION_MODEL_ARN")

# ── サポートする単項フィルター演算子 ──────────────
_VALID_OPERATORS = frozenset(
    {
        "equals",
        "notEquals",
        "greaterThan",
        "lessThan",
        "greaterThanOrEquals",
        "lessThanOrEquals",
        "startsWith",
        "in",
        "notIn",
        "listContains",
        "andAll",
        "orAll",
    }
)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """API Gateway からのリクエストを処理して回答を返す"""
    logger.info("event: %s", json.dumps(event))

    try:
        raw_body = event.get("body")
        body = json.loads(raw_body) if raw_body else {}
        query = body.get("query", "").strip()
        num_results = int(body.get("num_results", 5))
        session_id: str | None = body.get("session_id") or None
        mode = body.get("mode", "rag")
        filter_expr: dict[str, Any] | None = body.get("filter") or None

        if not query:
            return _response(400, {"error": "query は必須です"})
        if not (1 <= num_results <= 20):
            return _response(
                400, {"error": "num_results は 1〜20 の範囲で指定してください"}
            )
        if mode not in ("rag", "retrieve"):
            return _response(
                400, {"error": "mode は 'rag' または 'retrieve' を指定してください"}
            )
        if filter_expr is not None and not _is_valid_filter(filter_expr):
            return _response(
                400,
                {
                    "error": f"filter のキーが不正です。使用可能: {sorted(_VALID_OPERATORS)}"
                },
            )

        if mode == "retrieve":
            chunks = _retrieve(query, num_results, filter_expr)
            return _response(200, {"query": query, "chunks": chunks})

        answer, citations, new_session_id = _retrieve_and_generate(
            query, num_results, session_id, filter_expr
        )
        return _response(
            200,
            {
                "query": query,
                "answer": answer,
                "citations": citations,
                "session_id": new_session_id,
            },
        )

    except Exception as e:
        logger.exception("エラーが発生しました: %s", e)
        return _response(500, {"error": "内部エラーが発生しました"})


def _is_valid_filter(filter_expr: dict[str, Any]) -> bool:
    """フィルター式のトップレベルキーが既知の演算子かどうかを確認する"""
    return bool(filter_expr) and all(k in _VALID_OPERATORS for k in filter_expr)


def _retrieve_and_generate(
    query: str,
    num_results: int = 5,
    session_id: str | None = None,
    filter_expr: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], str]:
    """RetrieveAndGenerate API を呼び出す（sessionId を渡すと会話が継続される）"""
    vector_search_config: dict[str, Any] = {"numberOfResults": num_results}
    if filter_expr:
        vector_search_config["filter"] = filter_expr

    params: dict[str, Any] = {
        "input": {"text": query},
        "retrieveAndGenerateConfiguration": {
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                "modelArn": GENERATION_MODEL_ARN,
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": vector_search_config,
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
    }
    if session_id:
        params["sessionId"] = session_id  # 同じセッションに紐付けて会話を継続

    response = bedrock_agent_runtime.retrieve_and_generate(**params)

    answer = response["output"]["text"]
    new_session_id = response.get("sessionId", "")
    citations = [
        {
            "text": ref.get("content", {}).get("text", ""),
            "source": ref.get("location", {}).get("s3Location", {}).get("uri", ""),
            "metadata": ref.get("metadata", {}),  # chunk ID・data source ID 等
        }
        for citation in response.get("citations", [])
        for ref in citation.get("retrievedReferences", [])
    ]

    return answer, citations, new_session_id


def _retrieve(
    query: str,
    num_results: int = 5,
    filter_expr: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Retrieve API でスコア付き検索結果を返す（回答生成なし・デバッグ・精度確認用）"""
    vector_search_config: dict[str, Any] = {"numberOfResults": num_results}
    if filter_expr:
        vector_search_config["filter"] = filter_expr

    response = bedrock_agent_runtime.retrieve(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": vector_search_config},
    )
    return [
        {
            "text": r.get("content", {}).get("text", ""),
            "source": r.get("location", {}).get("s3Location", {}).get("uri", ""),
            "score": round(r.get("score", 0.0), 4),
            "metadata": r.get("metadata", {}),  # chunk ID・data source ID 等
        }
        for r in response.get("retrievalResults", [])
    ]


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """API Gateway レスポンスを組み立てる"""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }

"""
Bedrock Knowledge Bases RAG クエリハンドラー
- mode=rag    : RetrieveAndGenerate API（sessionId による multi-turn 会話対応）
- mode=retrieve: Retrieve API（スコア付き検索結果のみ返す・生成なし）

メタデータフィルター:
  リクエスト body に "filter" キーで Bedrock KB フィルター式を渡す。
  例: {"equals": {"key": "category", "value": "hr"}}
  例: {"startsWith": {"key": "title", "value": "社内規程"}}
  例: {"andAll": [{"equals": {...}}, {"greaterThanOrEquals": {...}}]}

ログとメトリクスは同梱の共通ユーティリティ（logger.py / metrics.py）を通す。
- logger.py  : 機密情報をマスクしたうえで JSON 1 行として出力する
- metrics.py : EMF でクエリ数・レイテンシ・エラー数を CloudWatch へ送る
"""

import json
import os
import sys
from typing import Any

import boto3

sys.path.insert(0, os.path.dirname(__file__))
from logger import StructuredLogger, create_logger_from_env, retry_logger  # noqa: E402
from metrics import (  # noqa: E402
    MetricsCollector,
    create_metrics_from_env,
    retry_metrics,
)
from retry import RetryConfig, retry_call  # noqa: E402

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

# ── リトライ設定 ─────────────────────────────────
# Bedrock は同時実行が増えると ThrottlingException を返すため、
# 指数バックオフ + フルジッターで自動リトライする（retry.py を参照）
RETRY_CONFIG = RetryConfig(
    max_attempts=int(os.environ.get("RETRY_MAX_ATTEMPTS", "4")),
    base_delay=float(os.environ.get("RETRY_BASE_DELAY", "0.5")),
    max_delay=float(os.environ.get("RETRY_MAX_DELAY", "8.0")),
)

# ── ロガー / メトリクス ──────────────────────────
# 既定値はモジュール読み込み時ではなく呼び出し時に作る。
# Lambda の再利用コンテナで環境変数の変更が反映されない事故を避けるため。


def _default_logger() -> StructuredLogger:
    """LOG_LEVEL からロガーを組み立てる（未設定なら info）"""
    return create_logger_from_env()


def _default_metrics() -> MetricsCollector:
    """METRICS_NAMESPACE / METRICS_ENABLED からコレクタを組み立てる"""
    return create_metrics_from_env(Handler="bedrock-kb-rag-query")


def _retry_hook(
    log: StructuredLogger,
    mx: MetricsCollector,
    operation: str,
):
    """retry_call(on_retry=...) に渡すフック。ログとメトリクスの両方へ流す"""
    to_log = retry_logger(log, operation)
    to_metrics = retry_metrics(mx, operation)

    def on_retry(attempt: int, delay_seconds: float, exc: BaseException) -> None:
        to_log(attempt, delay_seconds, exc)
        to_metrics(attempt, delay_seconds, exc)

    return on_retry


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


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    *,
    logger: StructuredLogger | None = None,
    metrics: MetricsCollector | None = None,
) -> dict[str, Any]:
    """API Gateway からのリクエストを処理して回答を返す

    logger / metrics は差し替え可能にしてある（テストから出力を検証するため）。
    """
    log = logger or _default_logger()
    mx = metrics or _default_metrics()

    # ★イベント全体をそのまま出すと body に含まれる個人情報まで残ってしまう。
    # 構造化ロガーのマスキングを通し、必要な項目だけを出す。
    log.info(
        "リクエストを受信しました",
        path=event.get("path"),
        http_method=event.get("httpMethod"),
        has_body=bool(event.get("body")),
    )

    try:
        raw_body = event.get("body")
        body = json.loads(raw_body) if raw_body else {}
        query = body.get("query", "").strip()
        num_results = int(body.get("num_results", 5))
        session_id: str | None = body.get("session_id") or None
        mode = body.get("mode", "rag")
        filter_expr: dict[str, Any] | None = body.get("filter") or None

        if not query:
            return _bad_request(log, mx, "query は必須です", reason="query_missing")
        if not (1 <= num_results <= 20):
            return _bad_request(
                log,
                mx,
                "num_results は 1〜20 の範囲で指定してください",
                reason="num_results_out_of_range",
            )
        if mode not in ("rag", "retrieve"):
            return _bad_request(
                log,
                mx,
                "mode は 'rag' または 'retrieve' を指定してください",
                reason="mode_invalid",
            )
        if filter_expr is not None and not _is_valid_filter(filter_expr):
            return _bad_request(
                log,
                mx,
                f"filter のキーが不正です。使用可能: {sorted(_VALID_OPERATORS)}",
                reason="filter_invalid",
            )

        mx.set_dimensions(Mode=mode)
        mx.add_metric("QueryCount", 1, unit="Count")
        mx.set_property("has_filter", filter_expr is not None)
        mx.set_property("has_session", session_id is not None)

        if mode == "retrieve":
            with mx.timer("QueryLatency"):
                chunks = _retrieve(query, num_results, filter_expr, log=log, mx=mx)
            mx.add_metric("ChunkCount", len(chunks), unit="Count")
            log.info("検索が完了しました", mode=mode, chunk_count=len(chunks))
            return _response(200, {"query": query, "chunks": chunks})

        with mx.timer("QueryLatency"):
            answer, citations, new_session_id = _retrieve_and_generate(
                query, num_results, session_id, filter_expr, log=log, mx=mx
            )
        mx.add_metric("CitationCount", len(citations), unit="Count")
        log.info(
            "回答を生成しました",
            mode=mode,
            citation_count=len(citations),
            answer_length=len(answer),
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
        mx.add_metric("ErrorCount", 1, unit="Count")
        log.error("エラーが発生しました", error=e)
        return _response(500, {"error": "内部エラーが発生しました"})
    finally:
        # 成功・失敗どちらでもメトリクスは必ず出す
        mx.flush()


def _bad_request(
    log: StructuredLogger,
    mx: MetricsCollector,
    message: str,
    *,
    reason: str,
) -> dict[str, Any]:
    """400 を返しつつ、理由をログとメトリクスに残す

    reason はプロパティとして持たせる（ディメンションにすると理由の種類だけ
    カスタムメトリクスが増えてしまうため）。
    """
    mx.set_property("bad_request_reason", reason)
    mx.add_metric("BadRequestCount", 1, unit="Count")
    log.warn("リクエストが不正です", reason=reason)
    return _response(400, {"error": message})


def _is_valid_filter(filter_expr: dict[str, Any]) -> bool:
    """フィルター式のトップレベルキーが既知の演算子かどうかを確認する"""
    return bool(filter_expr) and all(k in _VALID_OPERATORS for k in filter_expr)


def _retrieve_and_generate(
    query: str,
    num_results: int = 5,
    session_id: str | None = None,
    filter_expr: dict[str, Any] | None = None,
    *,
    log: StructuredLogger | None = None,
    mx: MetricsCollector | None = None,
) -> tuple[str, list[dict[str, Any]], str]:
    """
    RetrieveAndGenerate API を呼び出す（sessionId を渡すと会話が継続される）

    ThrottlingException 等の一時エラーは retry.py の指数バックオフで自動リトライする。
    """
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

    response = retry_call(
        bedrock_agent_runtime.retrieve_and_generate,
        config=RETRY_CONFIG,
        on_retry=_retry_hook(
            log or _default_logger(),
            mx or _default_metrics(),
            "bedrock.retrieve_and_generate",
        ),
        **params,
    )

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
    *,
    log: StructuredLogger | None = None,
    mx: MetricsCollector | None = None,
) -> list[dict[str, Any]]:
    """Retrieve API でスコア付き検索結果を返す（回答生成なし・デバッグ・精度確認用）"""
    vector_search_config: dict[str, Any] = {"numberOfResults": num_results}
    if filter_expr:
        vector_search_config["filter"] = filter_expr

    response = retry_call(
        bedrock_agent_runtime.retrieve,
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": vector_search_config},
        config=RETRY_CONFIG,
        on_retry=_retry_hook(
            log or _default_logger(),
            mx or _default_metrics(),
            "bedrock.retrieve",
        ),
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

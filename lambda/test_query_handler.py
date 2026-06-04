"""
aws-bedrock-knowledgebase-rag Lambda ユニットテスト
AWS 接続なしでレスポンス生成・ハンドラーを検証する
"""

import json
import os
from unittest.mock import MagicMock, patch

import sys

# モジュール読み込み前に環境変数を設定（module-level の os.environ アクセス対策）
os.environ.setdefault("KNOWLEDGE_BASE_ID", "test-kb-id")
os.environ.setdefault(
    "GENERATION_MODEL_ARN",
    "arn:aws:bedrock:ap-northeast-1::foundation-model/test",
)

sys.path.insert(0, os.path.dirname(__file__))
from query_handler import lambda_handler, _response


class TestResponse:
    def test_200レスポンスの構造(self):
        resp = _response(200, {"answer": "test"})
        assert resp["statusCode"] == 200
        assert json.loads(resp["body"])["answer"] == "test"
        assert resp["headers"]["Content-Type"] == "application/json"

    def test_400レスポンス(self):
        resp = _response(400, {"error": "invalid"})
        assert resp["statusCode"] == 400

    def test_CORSヘッダーが含まれる(self):
        resp = _response(200, {})
        assert resp["headers"]["Access-Control-Allow-Origin"] == "*"


class TestLambdaHandler:
    def _make_event(self, query="テスト質問"):
        return {"body": json.dumps({"query": query})}

    @patch("query_handler.bedrock_agent_runtime")
    @patch.dict(
        "os.environ",
        {
            "KNOWLEDGE_BASE_ID": "test-kb-id",
            "GENERATION_MODEL_ARN": "arn:aws:bedrock:ap-northeast-1::foundation-model/test",
        },
    )
    def test_正常系_200を返す(self, mock_bedrock):
        mock_bedrock.retrieve_and_generate.return_value = {
            "output": {"text": "テスト回答です"},
            "citations": [],
        }
        result = lambda_handler(self._make_event(), MagicMock())
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["answer"] == "テスト回答です"
        assert body["query"] == "テスト質問"

    def test_クエリ空で400(self):
        event = {"body": json.dumps({"query": ""})}
        result = lambda_handler(event, MagicMock())
        assert result["statusCode"] == 400

    @patch("query_handler.bedrock_agent_runtime")
    def test_bedrock例外で500(self, mock_bedrock):
        mock_bedrock.retrieve_and_generate.side_effect = Exception("connection error")
        result = lambda_handler(self._make_event(), MagicMock())
        assert result["statusCode"] == 500

    @patch("query_handler.bedrock_agent_runtime")
    def test_citations付き正常系(self, mock_bedrock):  # ⑮ citations が返る正常系
        mock_bedrock.retrieve_and_generate.return_value = {
            "output": {"text": "有給休暇は年10日付与されます"},
            "citations": [
                {
                    "retrievedReferences": [
                        {
                            "content": {"text": "有給休暇規程 第3条..."},
                            "location": {"s3Location": {"uri": "s3://bucket/hr-policy.txt"}},
                        }
                    ]
                }
            ],
        }
        result = lambda_handler(self._make_event("有給休暇の日数は？"), MagicMock())
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert len(body["citations"]) == 1
        assert body["citations"][0]["source"] == "s3://bucket/hr-policy.txt"

    def test_num_results範囲外で400(self):  # ⑯ num_results バリデーション
        event = {"body": json.dumps({"query": "テスト", "num_results": 0})}
        result = lambda_handler(event, MagicMock())
        assert result["statusCode"] == 400

    def test_bodyがNoneでも400を返す(self):  # ⑰ body が None のエッジケース
        event = {"body": None}
        result = lambda_handler(event, MagicMock())
        assert result["statusCode"] == 400

    @patch("query_handler.bedrock_agent_runtime")
    def test_session_idが引き継がれる(self, mock_bedrock):  # ③ multi-turn 会話
        mock_bedrock.retrieve_and_generate.return_value = {
            "output": {"text": "継続回答です"},
            "citations": [],
            "sessionId": "session-abc-123",
        }
        event = {"body": json.dumps({"query": "続けて教えて", "session_id": "session-abc-123"})}
        result = lambda_handler(event, MagicMock())
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["session_id"] == "session-abc-123"
        # sessionId が API 呼び出しに渡されているか確認
        call_kwargs = mock_bedrock.retrieve_and_generate.call_args.kwargs
        assert call_kwargs.get("sessionId") == "session-abc-123"

    @patch("query_handler.bedrock_agent_runtime")
    def test_retrieve_モードでスコア付き結果を返す(self, mock_bedrock):  # ⑨ スコア表示
        mock_bedrock.retrieve.return_value = {
            "retrievalResults": [
                {
                    "content": {"text": "有給休暇は年10日です"},
                    "location": {"s3Location": {"uri": "s3://bucket/hr.txt"}},
                    "score": 0.9876,
                }
            ]
        }
        event = {"body": json.dumps({"query": "有給休暇", "mode": "retrieve"})}
        result = lambda_handler(event, MagicMock())
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert len(body["chunks"]) == 1
        assert body["chunks"][0]["score"] == 0.9876
        assert body["chunks"][0]["source"] == "s3://bucket/hr.txt"

    def test_mode不正で400(self):
        event = {"body": json.dumps({"query": "テスト", "mode": "invalid"})}
        result = lambda_handler(event, MagicMock())
        assert result["statusCode"] == 400

    @patch("query_handler.bedrock_agent_runtime")
    def test_フィルター付きretrieveでfilterがAPIに渡る(self, mock_bedrock):
        """filter が Retrieve API の vectorSearchConfiguration に正しく渡されること"""
        mock_bedrock.retrieve.return_value = {
            "retrievalResults": [
                {
                    "content": {"text": "人事規程の内容"},
                    "location": {"s3Location": {"uri": "s3://bucket/hr.txt"}},
                    "score": 0.91,
                    "metadata": {"x-amz-bedrock-kb-chunk-id": "chunk-001"},
                }
            ]
        }
        filter_expr = {"equals": {"key": "category", "value": "hr"}}
        event = {"body": json.dumps({"query": "有給休暇", "mode": "retrieve", "filter": filter_expr})}
        result = lambda_handler(event, MagicMock())

        assert result["statusCode"] == 200
        call_kwargs = mock_bedrock.retrieve.call_args.kwargs
        vs_config = call_kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]
        assert vs_config["filter"] == filter_expr
        body = json.loads(result["body"])
        assert body["chunks"][0]["metadata"] == {"x-amz-bedrock-kb-chunk-id": "chunk-001"}

    @patch("query_handler.bedrock_agent_runtime")
    def test_フィルター付きRAGでfilterがAPIに渡る(self, mock_bedrock):
        """filter が RetrieveAndGenerate API の vectorSearchConfiguration に正しく渡されること"""
        mock_bedrock.retrieve_and_generate.return_value = {
            "output": {"text": "フィルター適用後の回答"},
            "citations": [],
        }
        filter_expr = {"startsWith": {"key": "title", "value": "社内規程"}}
        event = {"body": json.dumps({"query": "テスト", "filter": filter_expr})}
        result = lambda_handler(event, MagicMock())

        assert result["statusCode"] == 200
        call_kwargs = mock_bedrock.retrieve_and_generate.call_args.kwargs
        kb_config = call_kwargs["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"]
        vs_config = kb_config["retrievalConfiguration"]["vectorSearchConfiguration"]
        assert vs_config["filter"] == filter_expr

    @patch("query_handler.bedrock_agent_runtime")
    def test_citationsにmetadataが含まれる(self, mock_bedrock):
        """RetrieveAndGenerate のレスポンスから metadata が引用情報に含まれること"""
        mock_bedrock.retrieve_and_generate.return_value = {
            "output": {"text": "有給休暇の回答"},
            "citations": [
                {
                    "retrievedReferences": [
                        {
                            "content": {"text": "有給休暇規程 第3条..."},
                            "location": {"s3Location": {"uri": "s3://bucket/hr-policy.pdf"}},
                            "metadata": {
                                "x-amz-bedrock-kb-chunk-id": "chunk-abc",
                                "x-amz-bedrock-kb-data-source-id": "ds-001",
                            },
                        }
                    ]
                }
            ],
        }
        event = {"body": json.dumps({"query": "有給休暇の日数は？"})}
        result = lambda_handler(event, MagicMock())

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        citation = body["citations"][0]
        assert citation["source"] == "s3://bucket/hr-policy.pdf"
        assert citation["metadata"]["x-amz-bedrock-kb-chunk-id"] == "chunk-abc"

    def test_不正なfilterキーで400(self):
        """サポート外の演算子名が filter に含まれる場合 400 を返すこと"""
        event = {"body": json.dumps({"query": "テスト", "filter": {"unknownOp": {"key": "k", "value": "v"}}})}
        result = lambda_handler(event, MagicMock())
        assert result["statusCode"] == 400

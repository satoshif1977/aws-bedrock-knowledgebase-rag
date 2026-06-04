"""
Bedrock Knowledge Bases RAG - Streamlit Web UI
起動: aws-vault exec personal-dev-source -- streamlit run app.py
"""
import os
from urllib.parse import urlparse

import boto3
import streamlit as st


# ── ヘルパー ─────────────────────────────────────
def _source_label(uri: str) -> str:
    """S3 URI からファイル名を抽出して表示用ラベルを返す。
    例: s3://bucket/docs/hr-policy.pdf → hr-policy.pdf
    """
    if not uri:
        return "不明"
    try:
        path = urlparse(uri).path
        return path.split("/")[-1] or uri
    except Exception:
        return uri


# サポートする演算子と表示名のマッピング
_FILTER_OPERATORS: dict[str, str] = {
    "equals": "等しい (equals)",
    "notEquals": "等しくない (notEquals)",
    "startsWith": "で始まる (startsWith)",
    "greaterThanOrEquals": "以上 (greaterThanOrEquals)",
    "lessThanOrEquals": "以下 (lessThanOrEquals)",
}

# ── ページ設定 ───────────────────────────────────
st.set_page_config(
    page_title="Bedrock KB RAG",
    page_icon="🔍",
    layout="wide",
)

# ── Bedrock クライアント（キャッシュで再利用）────────
@st.cache_resource
def get_bedrock_client():
    return boto3.client(
        "bedrock-agent-runtime",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1"),
    )

# ── セッション状態の初期化 ───────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── サイドバー設定 ───────────────────────────────
with st.sidebar:
    st.header("設定")
    knowledge_base_id = st.text_input(
        "Knowledge Base ID",
        help="terraform output knowledge_base_id で確認",
    )
    generation_model_id = st.selectbox(
        "生成モデル",
        options=[
            "anthropic.claude-haiku-4-5-20251001-v1:0",
            "anthropic.claude-3-5-haiku-20241022-v1:0",
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
        ],
    )
    num_results = st.slider("検索件数", min_value=1, max_value=10, value=5)
    st.divider()

    mode = st.radio(
        "モード",
        options=["RAG（回答生成）", "検索のみ（スコア表示）"],
        index=0,
        help=(
            "RAG: 質問に対してモデルが回答を生成します（multi-turn 会話対応）。\n"
            "検索のみ: 関連チャンクと信頼スコアを表示します（回答生成なし）。"
        ),
    )
    st.divider()

    st.subheader("メタデータフィルター（オプション）")
    use_filter = st.checkbox("フィルターを使用する")
    filter_key = ""
    filter_operator = "equals"
    filter_value = ""
    if use_filter:
        filter_key = st.text_input("フィルターキー", placeholder="例: category")
        filter_operator = st.selectbox(
            "演算子",
            options=list(_FILTER_OPERATORS.keys()),
            format_func=lambda k: _FILTER_OPERATORS[k],
        )
        filter_value = st.text_input("フィルター値", placeholder="例: hr")
    st.divider()

    if st.button("🔄 会話をリセット", use_container_width=True):
        st.session_state.session_id = None
        st.session_state.messages = []
        st.rerun()
    if st.session_state.session_id:
        st.caption(f"Session: `{st.session_state.session_id[:8]}...`")
    st.divider()
    st.caption("aws-bedrock-knowledgebase-rag PoC")

# ── メイン画面 ───────────────────────────────────
st.title("🔍 Bedrock Knowledge Bases RAG")
st.caption("OpenSearch Serverless × Bedrock Knowledge Bases による セマンティック検索 Q&A")

if not knowledge_base_id:
    st.warning("サイドバーで Knowledge Base ID を設定してください。")
    st.stop()

bedrock_agent_runtime = get_bedrock_client()
aws_region = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")
generation_model_arn = f"arn:aws:bedrock:{aws_region}::foundation-model/{generation_model_id}"

# ── 会話履歴の表示（RAG モードのみ） ────────────
if st.session_state.messages:
    st.subheader("会話履歴")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg.get("citations"):
                with st.expander(f"参照ドキュメント ({len(msg['citations'])} 件)"):
                    for i, c in enumerate(msg["citations"], 1):
                        label = _source_label(c["source"])
                        st.markdown(f"**[{i}] {label}**")
                        if c["source"]:
                            st.caption(f"　{c['source']}")
                        preview = c["text"][:300] + "..." if len(c["text"]) > 300 else c["text"]
                        st.caption(preview)
                        st.divider()
    st.divider()

# ── クエリ入力 ───────────────────────────────────
query = st.text_area("質問を入力してください", height=100, placeholder="例: 有給休暇の申請方法は？")

if st.button("質問する", type="primary", disabled=not query):
    vector_search_config: dict = {"numberOfResults": num_results}
    if use_filter and filter_key and filter_value:
        vector_search_config["filter"] = {
            filter_operator: {"key": filter_key, "value": filter_value}
        }

    with st.spinner("Bedrock Knowledge Bases で検索中..."):
        try:
            if mode == "検索のみ（スコア表示）":
                # ── Retrieve モード: スコア付き検索結果 ──
                response = bedrock_agent_runtime.retrieve(
                    knowledgeBaseId=knowledge_base_id,
                    retrievalQuery={"text": query},
                    retrievalConfiguration={
                        "vectorSearchConfiguration": vector_search_config,
                    },
                )
                chunks = [
                    {
                        "text": r.get("content", {}).get("text", ""),
                        "source": r.get("location", {}).get("s3Location", {}).get("uri", ""),
                        "score": round(r.get("score", 0.0), 4),
                        "metadata": r.get("metadata", {}),
                    }
                    for r in response.get("retrievalResults", [])
                ]
                st.subheader(f"検索結果（{len(chunks)} 件）")
                for i, chunk in enumerate(chunks, 1):
                    score_pct = chunk["score"] * 100
                    label = _source_label(chunk["source"])
                    with st.expander(f"[{i}]  スコア: {score_pct:.1f}%　 {label}"):
                        st.progress(chunk["score"], text=f"信頼スコア: {score_pct:.1f}%")
                        st.caption(
                            chunk["text"][:500] + "..." if len(chunk["text"]) > 500 else chunk["text"]
                        )
                        if chunk["metadata"]:
                            st.divider()
                            meta_items = {
                                k: v for k, v in chunk["metadata"].items()
                                if not k.startswith("x-amz-bedrock-kb-source")  # URI は source で表示済み
                            }
                            if meta_items:
                                st.caption("**メタデータ**")
                                for mk, mv in meta_items.items():
                                    st.caption(f"　`{mk}`: {mv}")

            else:
                # ── RAG モード: multi-turn 会話 ──────────
                params: dict = {
                    "input": {"text": query},
                    "retrieveAndGenerateConfiguration": {
                        "type": "KNOWLEDGE_BASE",
                        "knowledgeBaseConfiguration": {
                            "knowledgeBaseId": knowledge_base_id,
                            "modelArn": generation_model_arn,
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
                if st.session_state.session_id:
                    params["sessionId"] = st.session_state.session_id  # 会話継続

                response = bedrock_agent_runtime.retrieve_and_generate(**params)
                answer = response["output"]["text"]
                st.session_state.session_id = response.get("sessionId")
                citations = [
                    {
                        "text": ref.get("content", {}).get("text", ""),
                        "source": ref.get("location", {}).get("s3Location", {}).get("uri", ""),
                        "metadata": ref.get("metadata", {}),
                    }
                    for citation in response.get("citations", [])
                    for ref in citation.get("retrievedReferences", [])
                ]

                # 会話履歴に追加
                st.session_state.messages.append({"role": "user", "content": query})
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "citations": citations,
                })

                st.success("回答")
                st.write(answer)
                if citations:
                    with st.expander(f"参照ドキュメント ({len(citations)} 件)"):
                        for i, c in enumerate(citations, 1):
                            label = _source_label(c["source"])
                            st.markdown(f"**[{i}] {label}**")
                            if c["source"]:
                                st.caption(f"　{c['source']}")
                            preview = c["text"][:300] + "..." if len(c["text"]) > 300 else c["text"]
                            st.caption(preview)
                            if c.get("metadata"):
                                chunk_id = c["metadata"].get("x-amz-bedrock-kb-chunk-id", "")
                                if chunk_id:
                                    st.caption(f"　chunk: `{chunk_id}`")
                            st.divider()

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

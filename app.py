"""
Bedrock Knowledge Bases RAG - Streamlit Web UI
起動: aws-vault exec personal-dev-source -- streamlit run app.py
"""
import json

import boto3
import streamlit as st

# ── ページ設定 ───────────────────────────────────
st.set_page_config(
    page_title="Bedrock KB RAG",
    page_icon="🔍",
    layout="wide",
)

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
            "anthropic.claude-3-haiku-20240307-v1:0",
            "anthropic.claude-3-sonnet-20240229-v1:0",
        ],
    )
    num_results = st.slider("検索件数", min_value=1, max_value=10, value=5)
    st.divider()
    st.caption("aws-bedrock-knowledgebase-rag PoC")

# ── メイン画面 ───────────────────────────────────
st.title("🔍 Bedrock Knowledge Bases RAG")
st.caption("OpenSearch Serverless × Bedrock Knowledge Bases による セマンティック検索 Q&A")

if not knowledge_base_id:
    st.warning("サイドバーで Knowledge Base ID を設定してください。")
    st.stop()

# ── Bedrock クライアント ─────────────────────────
bedrock_agent_runtime = boto3.client(
    "bedrock-agent-runtime",
    region_name="ap-northeast-1",
)

# ── クエリ入力 ───────────────────────────────────
query = st.text_area("質問を入力してください", height=100, placeholder="例: 有給休暇の申請方法は？")

if st.button("質問する", type="primary", disabled=not query):
    with st.spinner("Bedrock Knowledge Bases で検索・回答生成中..."):
        try:
            generation_model_arn = (
                f"arn:aws:bedrock:ap-northeast-1::foundation-model/{generation_model_id}"
            )
            response = bedrock_agent_runtime.retrieve_and_generate(
                input={"text": query},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": knowledge_base_id,
                        "modelArn": generation_model_arn,
                        "retrievalConfiguration": {
                            "vectorSearchConfiguration": {
                                "numberOfResults": num_results,
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
            citations = response.get("citations", [])

            st.success("回答")
            st.write(answer)

            if citations:
                with st.expander(f"参照ドキュメント ({len(citations)} 件)"):
                    for i, citation in enumerate(citations, 1):
                        for ref in citation.get("retrievedReferences", []):
                            source = (
                                ref.get("location", {})
                                .get("s3Location", {})
                                .get("uri", "不明")
                            )
                            text = ref.get("content", {}).get("text", "")
                            st.markdown(f"**[{i}] {source}**")
                            st.caption(text[:300] + "..." if len(text) > 300 else text)
                            st.divider()

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

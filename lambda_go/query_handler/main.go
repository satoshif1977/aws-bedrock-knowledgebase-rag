// aws-bedrock-knowledgebase-rag: Go 実装（Python 版との並置）
//
// Python 版との比較ポイント:
//   - コールドスタートが Python より高速（バイナリ実行・ランタイム起動なし）
//   - 型安全: 構造体でリクエスト/レスポンスを厳密に定義
//   - init() でクライアントを初期化 → Python のモジュールトップ変数と同等
//   - 対応モード: rag（RetrieveAndGenerate）/ retrieve（Retrieve のみ）
//
// ビルド方法:
//
//	GOOS=linux GOARCH=arm64 go build -o bootstrap main.go
//	zip lambda_go.zip bootstrap
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	bedrockagentruntime "github.com/aws/aws-sdk-go-v2/service/bedrockagentruntime"
	"github.com/aws/aws-sdk-go-v2/service/bedrockagentruntime/types"
)

// ── 環境変数 ──────────────────────────────────────────────────
var (
	knowledgeBaseID   = getEnv("KNOWLEDGE_BASE_ID", "")
	generationModelARN = getEnv("GENERATION_MODEL_ARN", "")
)

// ── AWS クライアント（init で初期化） ─────────────────────────
var bedrockClient *bedrockagentruntime.Client

func init() {
	cfg, err := config.LoadDefaultConfig(context.Background())
	if err != nil {
		log.Fatalf("AWS 設定の読み込みに失敗: %v", err)
	}
	bedrockClient = bedrockagentruntime.NewFromConfig(cfg)
}

// ── リクエスト / レスポンス型 ────────────────────────────────
type QueryRequest struct {
	Query      string         `json:"query"`
	NumResults int            `json:"num_results"`
	SessionID  string         `json:"session_id"`
	Mode       string         `json:"mode"`
	Filter     map[string]any `json:"filter"`
}

type Chunk struct {
	Text     string         `json:"text"`
	Source   string         `json:"source"`
	Score    float64        `json:"score"`
	Metadata map[string]any `json:"metadata"`
}

type Citation struct {
	Text     string         `json:"text"`
	Source   string         `json:"source"`
	Metadata map[string]any `json:"metadata"`
}

type RAGResponse struct {
	Query     string     `json:"query"`
	Answer    string     `json:"answer,omitempty"`
	Citations []Citation `json:"citations,omitempty"`
	SessionID string     `json:"session_id,omitempty"`
	Chunks    []Chunk    `json:"chunks,omitempty"`
}

// ── バリデーション ────────────────────────────────────────────
var validOperators = map[string]bool{
	"equals": true, "notEquals": true,
	"greaterThan": true, "lessThan": true,
	"greaterThanOrEquals": true, "lessThanOrEquals": true,
	"startsWith": true, "in": true, "notIn": true,
	"listContains": true, "andAll": true, "orAll": true,
}

func isValidFilter(filter map[string]any) bool {
	if len(filter) == 0 {
		return false
	}
	for k := range filter {
		if !validOperators[k] {
			return false
		}
	}
	return true
}

// ── ヘルパー ──────────────────────────────────────────────────
func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func apiResponse(statusCode int, body any) (events.APIGatewayProxyResponse, error) {
	b, _ := json.Marshal(body)
	return events.APIGatewayProxyResponse{
		StatusCode: statusCode,
		Headers: map[string]string{
			"Content-Type":                "application/json",
			"Access-Control-Allow-Origin": "*",
		},
		Body: string(b),
	}, nil
}

func errResponse(statusCode int, msg string) (events.APIGatewayProxyResponse, error) {
	return apiResponse(statusCode, map[string]string{"error": msg})
}

// ── RetrieveAndGenerate（RAG モード） ─────────────────────────
func retrieveAndGenerate(ctx context.Context, req QueryRequest) (RAGResponse, error) {
	vectorCfg := &types.KnowledgeBaseVectorSearchConfiguration{
		NumberOfResults: aws.Int32(int32(req.NumResults)),
	}

	kbCfg := &types.KnowledgeBaseRetrieveAndGenerateConfiguration{
		KnowledgeBaseId: aws.String(knowledgeBaseID),
		ModelArn:        aws.String(generationModelARN),
		RetrievalConfiguration: &types.KnowledgeBaseRetrievalConfiguration{
			VectorSearchConfiguration: vectorCfg,
		},
		GenerationConfiguration: &types.GenerationConfiguration{
			PromptTemplate: &types.PromptTemplate{
				TextPromptTemplate: aws.String(
					"以下の参考情報をもとに、質問に対して日本語で丁寧に回答してください。\n" +
						"参考情報に記載がない場合は「資料に情報がありません」と答えてください。\n\n" +
						"$search_results$\n\n質問: $query$",
				),
			},
		},
	}

	input := &bedrockagentruntime.RetrieveAndGenerateInput{
		Input: &types.RetrieveAndGenerateInput{Text: aws.String(req.Query)},
		RetrieveAndGenerateConfiguration: &types.RetrieveAndGenerateConfiguration{
			Type:                       types.RetrieveAndGenerateTypeKnowledgeBase,
			KnowledgeBaseConfiguration: kbCfg,
		},
	}
	if req.SessionID != "" {
		input.SessionId = aws.String(req.SessionID)
	}

	out, err := bedrockClient.RetrieveAndGenerate(ctx, input)
	if err != nil {
		return RAGResponse{}, fmt.Errorf("RetrieveAndGenerate エラー: %w", err)
	}

	citations := make([]Citation, 0)
	for _, c := range out.Citations {
		for _, ref := range c.RetrievedReferences {
			uri := ""
			if ref.Location != nil && ref.Location.S3Location != nil && ref.Location.S3Location.Uri != nil {
				uri = *ref.Location.S3Location.Uri
			}
			text := ""
			if ref.Content != nil && ref.Content.Text != nil {
				text = *ref.Content.Text
			}
			citations = append(citations, Citation{
				Text:   text,
				Source: uri,
			})
		}
	}

	sessionID := ""
	if out.SessionId != nil {
		sessionID = *out.SessionId
	}
	answer := ""
	if out.Output != nil && out.Output.Text != nil {
		answer = *out.Output.Text
	}

	return RAGResponse{
		Query:     req.Query,
		Answer:    answer,
		Citations: citations,
		SessionID: sessionID,
	}, nil
}

// ── Retrieve（検索のみモード） ────────────────────────────────
func retrieve(ctx context.Context, req QueryRequest) (RAGResponse, error) {
	vectorCfg := &types.KnowledgeBaseVectorSearchConfiguration{
		NumberOfResults: aws.Int32(int32(req.NumResults)),
	}

	input := &bedrockagentruntime.RetrieveInput{
		KnowledgeBaseId: aws.String(knowledgeBaseID),
		RetrievalQuery:  &types.KnowledgeBaseQuery{Text: aws.String(req.Query)},
		RetrievalConfiguration: &types.KnowledgeBaseRetrievalConfiguration{
			VectorSearchConfiguration: vectorCfg,
		},
	}

	out, err := bedrockClient.Retrieve(ctx, input)
	if err != nil {
		return RAGResponse{}, fmt.Errorf("Retrieve エラー: %w", err)
	}

	chunks := make([]Chunk, 0, len(out.RetrievalResults))
	for _, r := range out.RetrievalResults {
		uri := ""
		if r.Location != nil && r.Location.S3Location != nil && r.Location.S3Location.Uri != nil {
			uri = *r.Location.S3Location.Uri
		}
		text := ""
		if r.Content != nil && r.Content.Text != nil {
			text = *r.Content.Text
		}
		score := 0.0
		if r.Score != nil {
			score = *r.Score
		}
		chunks = append(chunks, Chunk{
			Text:   text,
			Source: uri,
			Score:  score,
		})
	}

	return RAGResponse{Query: req.Query, Chunks: chunks}, nil
}

// ── Lambda ハンドラー ─────────────────────────────────────────
func Handler(ctx context.Context, event events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	var req QueryRequest
	if err := json.Unmarshal([]byte(event.Body), &req); err != nil {
		return errResponse(400, "リクエストの解析に失敗しました")
	}

	req.Query = strings.TrimSpace(req.Query)
	if req.Query == "" {
		return errResponse(400, "query は必須です")
	}
	if req.NumResults == 0 {
		req.NumResults = 5 // JSON ゼロ値は未指定扱い → デフォルト
	}
	if req.NumResults < 1 || req.NumResults > 20 {
		return errResponse(400, "num_results は 1〜20 の範囲で指定してください")
	}
	if req.Mode == "" {
		req.Mode = "rag"
	}
	if req.Mode != "rag" && req.Mode != "retrieve" {
		return errResponse(400, "mode は 'rag' または 'retrieve' を指定してください")
	}
	if req.Filter != nil && !isValidFilter(req.Filter) {
		return errResponse(400, "filter のキーが不正です")
	}

	log.Printf("クエリ受信: mode=%s query=%.50s", req.Mode, req.Query)

	var (
		result RAGResponse
		err    error
	)
	if req.Mode == "retrieve" {
		result, err = retrieve(ctx, req)
	} else {
		result, err = retrieveAndGenerate(ctx, req)
	}
	if err != nil {
		log.Printf("エラー: %v", err)
		return errResponse(500, "内部エラーが発生しました")
	}

	return apiResponse(200, result)
}

func main() {
	lambda.Start(Handler)
}

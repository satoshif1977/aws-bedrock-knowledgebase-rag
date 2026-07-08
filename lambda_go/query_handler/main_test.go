package main

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/aws/aws-lambda-go/events"
)

// ── isValidFilter テスト ──────────────────────────────────────

func TestIsValidFilter_ValidOperators(t *testing.T) {
	cases := []struct {
		name   string
		filter map[string]any
		want   bool
	}{
		{"equals", map[string]any{"equals": map[string]any{"key": "category", "value": "hr"}}, true},
		{"notEquals", map[string]any{"notEquals": map[string]any{"key": "type", "value": "x"}}, true},
		{"startsWith", map[string]any{"startsWith": map[string]any{"key": "title", "value": "社内"}}, true},
		{"greaterThan", map[string]any{"greaterThan": map[string]any{"key": "year", "value": 2020}}, true},
		{"lessThan", map[string]any{"lessThan": map[string]any{"key": "year", "value": 2030}}, true},
		{"greaterThanOrEquals", map[string]any{"greaterThanOrEquals": map[string]any{"key": "year", "value": 2020}}, true},
		{"lessThanOrEquals", map[string]any{"lessThanOrEquals": map[string]any{"key": "year", "value": 2030}}, true},
		{"in", map[string]any{"in": map[string]any{"key": "tag", "value": []string{"a", "b"}}}, true},
		{"notIn", map[string]any{"notIn": map[string]any{"key": "tag", "value": []string{"x"}}}, true},
		{"listContains", map[string]any{"listContains": map[string]any{"key": "tags", "value": "hr"}}, true},
		{"andAll", map[string]any{"andAll": []any{}}, true},
		{"orAll", map[string]any{"orAll": []any{}}, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := isValidFilter(tc.filter)
			if got != tc.want {
				t.Errorf("isValidFilter(%v) = %v, want %v", tc.filter, got, tc.want)
			}
		})
	}
}

func TestIsValidFilter_InvalidOperator(t *testing.T) {
	filter := map[string]any{"invalidOp": map[string]any{"key": "x", "value": "y"}}
	if isValidFilter(filter) {
		t.Error("不正な演算子なのに true が返った")
	}
}

func TestIsValidFilter_EmptyFilter(t *testing.T) {
	if isValidFilter(map[string]any{}) {
		t.Error("空フィルターなのに true が返った")
	}
}

func TestIsValidFilter_NilFilter(t *testing.T) {
	if isValidFilter(nil) {
		t.Error("nil フィルターなのに true が返った")
	}
}

// ── getEnv テスト ─────────────────────────────────────────────

func TestGetEnv_WithFallback(t *testing.T) {
	got := getEnv("__NON_EXISTENT_ENV__", "fallback_value")
	if got != "fallback_value" {
		t.Errorf("getEnv fallback = %q, want %q", got, "fallback_value")
	}
}

func TestGetEnv_WithValue(t *testing.T) {
	t.Setenv("TEST_KEY_RAG", "hello")
	got := getEnv("TEST_KEY_RAG", "fallback")
	if got != "hello" {
		t.Errorf("getEnv = %q, want %q", got, "hello")
	}
}

// ── apiResponse テスト ────────────────────────────────────────

func TestApiResponse_StatusAndHeaders(t *testing.T) {
	resp, err := apiResponse(200, map[string]string{"message": "ok"})
	if err != nil {
		t.Fatalf("apiResponse エラー: %v", err)
	}
	if resp.StatusCode != 200 {
		t.Errorf("StatusCode = %d, want 200", resp.StatusCode)
	}
	if resp.Headers["Content-Type"] != "application/json" {
		t.Errorf("Content-Type = %q", resp.Headers["Content-Type"])
	}
	if resp.Headers["Access-Control-Allow-Origin"] != "*" {
		t.Errorf("CORS header = %q", resp.Headers["Access-Control-Allow-Origin"])
	}
}

func TestApiResponse_BodyJSON(t *testing.T) {
	body := map[string]string{"key": "value"}
	resp, _ := apiResponse(200, body)
	var got map[string]string
	if err := json.Unmarshal([]byte(resp.Body), &got); err != nil {
		t.Fatalf("Body が JSON でない: %v", err)
	}
	if got["key"] != "value" {
		t.Errorf("Body[key] = %q, want %q", got["key"], "value")
	}
}

func TestErrResponse_StatusAndMessage(t *testing.T) {
	resp, _ := errResponse(400, "query は必須です")
	if resp.StatusCode != 400 {
		t.Errorf("StatusCode = %d, want 400", resp.StatusCode)
	}
	var got map[string]string
	json.Unmarshal([]byte(resp.Body), &got)
	if got["error"] != "query は必須です" {
		t.Errorf("error = %q", got["error"])
	}
}

// ── Handler バリデーションテスト（AWS 呼び出しなし） ──────────

func makeEvent(body string) events.APIGatewayProxyRequest {
	return events.APIGatewayProxyRequest{Body: body}
}

func TestHandler_EmptyQuery(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{"query":""}`))
	if resp.StatusCode != 400 {
		t.Errorf("StatusCode = %d, want 400", resp.StatusCode)
	}
}

func TestHandler_MissingQuery(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{}`))
	if resp.StatusCode != 400 {
		t.Errorf("StatusCode = %d, want 400", resp.StatusCode)
	}
}

func TestHandler_WhitespaceQuery(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"   "}`))
	if resp.StatusCode != 400 {
		t.Errorf("StatusCode = %d, want 400", resp.StatusCode)
	}
}

func TestHandler_InvalidJSON(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`not-json`))
	if resp.StatusCode != 400 {
		t.Errorf("StatusCode = %d, want 400", resp.StatusCode)
	}
}

func TestHandler_NumResultsOutOfRange_Low(t *testing.T) {
	// num_results=-1 は範囲外（Go JSON では 0 はゼロ値=未指定扱いでデフォルト5になるため -1 で確認）
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","num_results":-1}`))
	if resp.StatusCode != 400 {
		t.Errorf("StatusCode = %d, want 400", resp.StatusCode)
	}
}

func TestHandler_NumResultsOutOfRange_High(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","num_results":21}`))
	if resp.StatusCode != 400 {
		t.Errorf("StatusCode = %d, want 400", resp.StatusCode)
	}
}

func TestHandler_InvalidMode(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","mode":"invalid"}`))
	if resp.StatusCode != 400 {
		t.Errorf("StatusCode = %d, want 400", resp.StatusCode)
	}
}

func TestHandler_InvalidFilter(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","filter":{"badOp":{"key":"x","value":"y"}}}`))
	if resp.StatusCode != 400 {
		t.Errorf("StatusCode = %d, want 400", resp.StatusCode)
	}
}

func TestHandler_EmptyBody_Returns400(t *testing.T) {
	// 空文字列は JSON パース失敗 → 400
	resp, _ := Handler(context.Background(), makeEvent(""))
	if resp.StatusCode != 400 {
		t.Errorf("StatusCode = %d, want 400", resp.StatusCode)
	}
}

func TestHandler_NumResultsZero_DefaultApplied(t *testing.T) {
	// num_results=0 は未指定扱い → デフォルト5に変換されバリデーション通過（400 にならない）
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","num_results":0}`))
	if resp.StatusCode == 400 {
		t.Error("num_results=0 は 400 ではなくデフォルト5に変換されるべき")
	}
}

func TestHandler_NumResultsOne_Valid(t *testing.T) {
	// num_results=1 は最小値としてバリデーション通過（400 にならない）
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","num_results":1}`))
	if resp.StatusCode == 400 {
		t.Errorf("num_results=1 は最小値としてバリデーション通過するべき: got %d", resp.StatusCode)
	}
}

func TestHandler_NumResultsTwenty_Valid(t *testing.T) {
	// num_results=20 は最大値としてバリデーション通過（400 にならない）
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","num_results":20}`))
	if resp.StatusCode == 400 {
		t.Errorf("num_results=20 は最大値としてバリデーション通過するべき: got %d", resp.StatusCode)
	}
}

func TestHandler_ModeEmpty_DefaultRag(t *testing.T) {
	// mode="" はデフォルト "rag" になりバリデーション通過（400 にならない）
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","mode":""}`))
	if resp.StatusCode == 400 {
		t.Error("mode='' はデフォルト rag に変換されバリデーション通過するべき")
	}
}

func TestHandler_ModeRetrieve_Valid(t *testing.T) {
	// mode="retrieve" はバリデーション通過（400 にならない）
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","mode":"retrieve"}`))
	if resp.StatusCode == 400 {
		t.Errorf("mode='retrieve' はバリデーション通過するべき: got %d", resp.StatusCode)
	}
}

func TestHandler_ValidFilter_Passes(t *testing.T) {
	// 有効な filter はバリデーション通過（400 にならない）
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","filter":{"equals":{"key":"cat","value":"hr"}}}`))
	if resp.StatusCode == 400 {
		t.Error("有効なフィルターで 400 が返ってはいけない")
	}
}

func TestApiResponse_500Status(t *testing.T) {
	resp, err := apiResponse(500, map[string]string{"error": "内部エラー"})
	if err != nil {
		t.Fatalf("apiResponse エラー: %v", err)
	}
	if resp.StatusCode != 500 {
		t.Errorf("StatusCode = %d, want 500", resp.StatusCode)
	}
	var got map[string]string
	json.Unmarshal([]byte(resp.Body), &got)
	if got["error"] != "内部エラー" {
		t.Errorf("error = %q", got["error"])
	}
}

func TestRAGResponseJSON_Serialization(t *testing.T) {
	rag := RAGResponse{
		Query:     "テスト質問",
		Answer:    "テスト回答",
		Citations: []Citation{{Text: "本文", Source: "s3://bucket/doc.txt"}},
		SessionID: "session-xyz",
	}
	resp, err := apiResponse(200, rag)
	if err != nil {
		t.Fatalf("apiResponse エラー: %v", err)
	}
	var got RAGResponse
	if err := json.Unmarshal([]byte(resp.Body), &got); err != nil {
		t.Fatalf("Body 逆シリアライズ失敗: %v", err)
	}
	if got.Query != "テスト質問" {
		t.Errorf("Query = %q, want テスト質問", got.Query)
	}
	if len(got.Citations) != 1 {
		t.Errorf("Citations len = %d, want 1", len(got.Citations))
	}
	if got.SessionID != "session-xyz" {
		t.Errorf("SessionID = %q, want session-xyz", got.SessionID)
	}
}

func TestGetEnv_EmptyStringFallsBack(t *testing.T) {
	// 環境変数が空文字列の場合も fallback を返す（getEnv は v != "" で判定）
	t.Setenv("TEST_EMPTY_RAG_KEY", "")
	got := getEnv("TEST_EMPTY_RAG_KEY", "default_value")
	if got != "default_value" {
		t.Errorf("getEnv with empty value = %q, want %q", got, "default_value")
	}
}

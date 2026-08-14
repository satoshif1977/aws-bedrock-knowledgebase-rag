package main

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
)

// ── isValidFilter エッジケース ────────────────────────────────

func TestIsValidFilter_MultipleValidOps(t *testing.T) {
	// 複数の valid な演算子が共存しても true を返す
	filter := map[string]any{
		"equals":      map[string]any{"key": "category", "value": "hr"},
		"greaterThan": map[string]any{"key": "year", "value": 2020},
	}
	if !isValidFilter(filter) {
		t.Error("複数の valid な演算子は true を返すべき")
	}
}

func TestIsValidFilter_MixedValidInvalid(t *testing.T) {
	// valid と invalid の演算子が混在する場合は false
	filter := map[string]any{
		"equals":  map[string]any{"key": "x", "value": "y"},
		"contains": "invalid_op",
	}
	if isValidFilter(filter) {
		t.Error("invalid な演算子が混在する場合は false を返すべき")
	}
}

func TestIsValidFilter_SingleAndAll(t *testing.T) {
	filter := map[string]any{"andAll": []any{}}
	if !isValidFilter(filter) {
		t.Error("andAll は valid")
	}
}

func TestIsValidFilter_SingleOrAll(t *testing.T) {
	filter := map[string]any{"orAll": []any{}}
	if !isValidFilter(filter) {
		t.Error("orAll は valid")
	}
}

func TestIsValidFilter_CaseSensitive(t *testing.T) {
	// 大文字始まり（"Equals"）は invalid
	filter := map[string]any{"Equals": map[string]any{"key": "x", "value": "y"}}
	if isValidFilter(filter) {
		t.Error("演算子名は大文字小文字を区別する（'Equals' は invalid）")
	}
}

// ── QueryRequest JSON パース ───────────────────────────────────

func TestQueryRequest_AllFields_Unmarshaled(t *testing.T) {
	raw := `{"query":"テスト","num_results":5,"session_id":"sess-abc","mode":"rag","filter":{"equals":{"key":"cat","value":"hr"}}}`
	var req QueryRequest
	if err := json.Unmarshal([]byte(raw), &req); err != nil {
		t.Fatalf("unmarshal error: %v", err)
	}
	if req.Query != "テスト" {
		t.Errorf("Query = %q", req.Query)
	}
	if req.NumResults != 5 {
		t.Errorf("NumResults = %d", req.NumResults)
	}
	if req.SessionID != "sess-abc" {
		t.Errorf("SessionID = %q", req.SessionID)
	}
	if req.Mode != "rag" {
		t.Errorf("Mode = %q", req.Mode)
	}
	if req.Filter == nil {
		t.Error("Filter should not be nil")
	}
}

func TestQueryRequest_ZeroValuesOnEmptyJSON(t *testing.T) {
	var req QueryRequest
	json.Unmarshal([]byte(`{}`), &req)
	if req.NumResults != 0 {
		t.Errorf("NumResults should be 0 (zero value), got %d", req.NumResults)
	}
	if req.Query != "" {
		t.Errorf("Query should be empty, got %q", req.Query)
	}
	if req.Filter != nil {
		t.Error("Filter should be nil")
	}
}

// ── Chunk 構造体テスト ────────────────────────────────────────

func TestChunk_JSONSerialization(t *testing.T) {
	chunk := Chunk{
		Text:   "ドキュメント本文",
		Source: "s3://bucket/file.pdf",
		Score:  0.92,
	}
	b, err := json.Marshal(chunk)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}
	var got Chunk
	if err := json.Unmarshal(b, &got); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}
	if got.Text != chunk.Text {
		t.Errorf("Text = %q, want %q", got.Text, chunk.Text)
	}
	if got.Source != chunk.Source {
		t.Errorf("Source = %q, want %q", got.Source, chunk.Source)
	}
	if got.Score != chunk.Score {
		t.Errorf("Score = %v, want %v", got.Score, chunk.Score)
	}
}

func TestChunk_ScoreZeroValue(t *testing.T) {
	chunk := Chunk{Text: "テキスト", Source: "s3://x"}
	b, _ := json.Marshal(chunk)
	var got Chunk
	json.Unmarshal(b, &got)
	if got.Score != 0.0 {
		t.Errorf("Score zero value = %v", got.Score)
	}
}

// ── RAGResponse バリエーション ────────────────────────────────

func TestRAGResponse_WithChunks(t *testing.T) {
	rag := RAGResponse{
		Query: "検索クエリ",
		Chunks: []Chunk{
			{Text: "chunk1", Source: "s3://a", Score: 0.9},
			{Text: "chunk2", Source: "s3://b", Score: 0.8},
		},
	}
	resp, err := apiResponse(200, rag)
	if err != nil {
		t.Fatalf("apiResponse error: %v", err)
	}
	var got RAGResponse
	json.Unmarshal([]byte(resp.Body), &got)
	if len(got.Chunks) != 2 {
		t.Errorf("Chunks len = %d, want 2", len(got.Chunks))
	}
	if got.Chunks[0].Score != 0.9 {
		t.Errorf("Chunks[0].Score = %v, want 0.9", got.Chunks[0].Score)
	}
}

func TestRAGResponse_EmptyCitationsOmitted(t *testing.T) {
	// Citations が nil/空の場合 omitempty で JSON から省略される
	rag := RAGResponse{Query: "q", Answer: "a"}
	b, _ := json.Marshal(rag)
	body := string(b)
	if strings.Contains(body, "citations") {
		t.Error("citations フィールドは空のとき omitempty で省略されるべき")
	}
}

func TestRAGResponse_MultiCitations(t *testing.T) {
	rag := RAGResponse{
		Query: "q",
		Citations: []Citation{
			{Text: "ref1", Source: "s3://a"},
			{Text: "ref2", Source: "s3://b"},
			{Text: "ref3", Source: "s3://c"},
		},
	}
	resp, _ := apiResponse(200, rag)
	var got RAGResponse
	json.Unmarshal([]byte(resp.Body), &got)
	if len(got.Citations) != 3 {
		t.Errorf("Citations len = %d, want 3", len(got.Citations))
	}
}

func TestRAGResponse_QueryOnly(t *testing.T) {
	rag := RAGResponse{Query: "最小構成"}
	resp, err := apiResponse(200, rag)
	if err != nil {
		t.Fatalf("apiResponse error: %v", err)
	}
	var got RAGResponse
	json.Unmarshal([]byte(resp.Body), &got)
	if got.Query != "最小構成" {
		t.Errorf("Query = %q", got.Query)
	}
}

func TestCitation_EmptyFields(t *testing.T) {
	c := Citation{Text: "", Source: ""}
	b, err := json.Marshal(c)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}
	var got Citation
	json.Unmarshal(b, &got)
	if got.Text != "" || got.Source != "" {
		t.Errorf("empty Citation fields should round-trip: got Text=%q Source=%q", got.Text, got.Source)
	}
}

// ── Handler 追加境界値 ────────────────────────────────────────

func TestHandler_JapaneseQuery_Valid(t *testing.T) {
	// 日本語クエリはバリデーション通過
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"社内規程について教えてください"}`))
	if resp.StatusCode == 400 {
		t.Error("日本語クエリは 400 を返すべきでない")
	}
}

func TestHandler_LongQuery_Valid(t *testing.T) {
	// 200文字のクエリはバリデーション通過
	longQuery := strings.Repeat("あ", 200)
	body, _ := json.Marshal(map[string]string{"query": longQuery})
	resp, _ := Handler(context.Background(), makeEvent(string(body)))
	if resp.StatusCode == 400 {
		t.Error("長いクエリは 400 を返すべきでない")
	}
}

func TestHandler_SessionID_DoesNotCause400(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","session_id":"sess-xyz"}`))
	if resp.StatusCode == 400 {
		t.Error("session_id があっても 400 を返すべきでない")
	}
}

func TestHandler_FilterNull_Valid(t *testing.T) {
	// filter が null の場合 nil として扱われ、バリデーションをスキップする
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","filter":null}`))
	if resp.StatusCode == 400 {
		t.Error("filter=null はバリデーション通過するべき")
	}
}

func TestHandler_NumResults10_Valid(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","num_results":10}`))
	if resp.StatusCode == 400 {
		t.Errorf("num_results=10 は中間値として有効: got %d", resp.StatusCode)
	}
}

func TestHandler_NumResults2_Valid(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","num_results":2}`))
	if resp.StatusCode == 400 {
		t.Errorf("num_results=2 は有効: got %d", resp.StatusCode)
	}
}

func TestHandler_NumResultsMinus1_Returns400(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","num_results":-1}`))
	if resp.StatusCode != 400 {
		t.Errorf("num_results=-1 は 400 を返すべき: got %d", resp.StatusCode)
	}
}

func TestHandler_NumResults21_Returns400(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test","num_results":21}`))
	if resp.StatusCode != 400 {
		t.Errorf("num_results=21 は 400 を返すべき: got %d", resp.StatusCode)
	}
}

func TestHandler_WhitespaceOnlyTabs_Returns400(t *testing.T) {
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"\t\t"}`))
	if resp.StatusCode != 400 {
		t.Errorf("タブのみの query は 400: got %d", resp.StatusCode)
	}
}

func TestHandler_ResponseBody_IsValidJSON(t *testing.T) {
	// バリデーション通過ケースのレスポンスが JSON デコード可能
	resp, _ := Handler(context.Background(), makeEvent(`{"query":"test"}`))
	var m map[string]any
	if err := json.Unmarshal([]byte(resp.Body), &m); err != nil {
		t.Errorf("response body is not valid JSON: %v", err)
	}
}

// ── errResponse バリエーション ────────────────────────────────

func TestErrResponse_404(t *testing.T) {
	resp, _ := errResponse(404, "リソースが見つかりません")
	if resp.StatusCode != 404 {
		t.Errorf("StatusCode = %d, want 404", resp.StatusCode)
	}
}

func TestErrResponse_500(t *testing.T) {
	resp, _ := errResponse(500, "内部エラー")
	if resp.StatusCode != 500 {
		t.Errorf("StatusCode = %d, want 500", resp.StatusCode)
	}
}

func TestErrResponse_ContentType(t *testing.T) {
	resp, _ := errResponse(400, "error")
	if resp.Headers["Content-Type"] != "application/json" {
		t.Errorf("Content-Type = %q, want application/json", resp.Headers["Content-Type"])
	}
}

func TestErrResponse_MessageInBody(t *testing.T) {
	resp, _ := errResponse(400, "テストエラーメッセージ")
	if !strings.Contains(resp.Body, "テストエラーメッセージ") {
		t.Errorf("body does not contain error message: %s", resp.Body)
	}
}

// ── apiResponse 追加 ──────────────────────────────────────────

func TestApiResponse_BodyIsString(t *testing.T) {
	resp, _ := apiResponse(200, map[string]int{"count": 42})
	if resp.Body == "" {
		t.Error("Body should not be empty string")
	}
	// Body が文字列型であること（JSON エンコード済み）
	var m map[string]int
	if err := json.Unmarshal([]byte(resp.Body), &m); err != nil {
		t.Errorf("Body is not JSON: %v", err)
	}
	if m["count"] != 42 {
		t.Errorf("count = %d, want 42", m["count"])
	}
}

func TestApiResponse_NilBodyReturnsNull(t *testing.T) {
	resp, err := apiResponse(200, nil)
	if err != nil {
		t.Fatalf("apiResponse(nil) error: %v", err)
	}
	if resp.Body == "" {
		t.Error("Body should not be empty even for nil")
	}
}

// ── Benchmark ─────────────────────────────────────────────────

func BenchmarkIsValidFilter(b *testing.B) {
	filter := map[string]any{"equals": map[string]any{"key": "category", "value": "hr"}}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		isValidFilter(filter)
	}
}

func BenchmarkApiResponse(b *testing.B) {
	body := RAGResponse{
		Query:  "ベンチマーク用クエリ",
		Answer: "ベンチマーク用回答テキスト",
		Citations: []Citation{
			{Text: "引用1", Source: "s3://bucket/doc1.pdf"},
		},
	}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		apiResponse(200, body) //nolint:errcheck
	}
}

func BenchmarkHandler_Validation(b *testing.B) {
	event := makeEvent(`{"query":"ベンチマーク用クエリ","num_results":5,"mode":"rag"}`)
	ctx := context.Background()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		Handler(ctx, event) //nolint:errcheck
	}
}

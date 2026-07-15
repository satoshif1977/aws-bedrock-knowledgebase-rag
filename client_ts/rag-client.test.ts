"use strict";

import {
  validateQuery,
  validateNumResults,
  validateMode,
  isValidFilter,
  normalizeRequest,
  validateRequest,
  extractAnswer,
  extractSources,
  sortChunksByScore,
  formatResponseSummary,
  VALID_OPERATORS,
  DEFAULT_NUM_RESULTS,
  MIN_NUM_RESULTS,
  MAX_NUM_RESULTS,
  DEFAULT_MODE,
} from "./rag-client";
import type { QueryRequest, RAGResponse, Citation, Chunk } from "./types";

// ── validateQuery ─────────────────────────────────────────────

describe("validateQuery", () => {
  test("有効なクエリは valid=true", () => {
    const result = validateQuery("有給休暇の申請方法は？");
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  test("空文字は valid=false", () => {
    const result = validateQuery("");
    expect(result.valid).toBe(false);
    expect(result.errors).toContain("query は必須です");
  });

  test("スペースのみは valid=false", () => {
    const result = validateQuery("   ");
    expect(result.valid).toBe(false);
  });

  test("タブのみは valid=false", () => {
    const result = validateQuery("\t\n");
    expect(result.valid).toBe(false);
  });

  test("前後空白があっても有効なクエリは valid=true", () => {
    const result = validateQuery("  テスト質問  ");
    expect(result.valid).toBe(true);
  });
});

// ── validateNumResults ────────────────────────────────────────

describe("validateNumResults", () => {
  test("0 はデフォルト扱いで valid=true", () => {
    expect(validateNumResults(0).valid).toBe(true);
  });

  test("1 は valid=true（最小値）", () => {
    expect(validateNumResults(MIN_NUM_RESULTS).valid).toBe(true);
  });

  test("20 は valid=true（最大値）", () => {
    expect(validateNumResults(MAX_NUM_RESULTS).valid).toBe(true);
  });

  test("10 は valid=true", () => {
    expect(validateNumResults(10).valid).toBe(true);
  });

  test("-1 は valid=false（範囲外）", () => {
    const result = validateNumResults(-1);
    expect(result.valid).toBe(false);
    expect(result.errors[0]).toMatch(/num_results/);
  });

  test("21 は valid=false（範囲外）", () => {
    expect(validateNumResults(21).valid).toBe(false);
  });
});

// ── validateMode ──────────────────────────────────────────────

describe("validateMode", () => {
  test("'rag' は valid=true", () => {
    expect(validateMode("rag").valid).toBe(true);
  });

  test("'retrieve' は valid=true", () => {
    expect(validateMode("retrieve").valid).toBe(true);
  });

  test("'invalid' は valid=false", () => {
    const result = validateMode("invalid");
    expect(result.valid).toBe(false);
    expect(result.errors[0]).toMatch(/mode/);
  });

  test("空文字は valid=false", () => {
    expect(validateMode("").valid).toBe(false);
  });
});

// ── isValidFilter ─────────────────────────────────────────────

describe("isValidFilter", () => {
  test("null は false", () => {
    expect(isValidFilter(null)).toBe(false);
  });

  test("undefined は false", () => {
    expect(isValidFilter(undefined)).toBe(false);
  });

  test("空オブジェクトは false", () => {
    expect(isValidFilter({})).toBe(false);
  });

  test("有効な演算子 'equals' は true", () => {
    expect(isValidFilter({ equals: { key: "category", value: "hr" } })).toBe(true);
  });

  test("有効な演算子 'in' は true", () => {
    expect(isValidFilter({ in: { key: "tag", value: ["a", "b"] } })).toBe(true);
  });

  test("有効な演算子 'andAll' は true", () => {
    expect(isValidFilter({ andAll: [] })).toBe(true);
  });

  test("有効な演算子 'orAll' は true", () => {
    expect(isValidFilter({ orAll: [] })).toBe(true);
  });

  test("不正な演算子は false", () => {
    expect(isValidFilter({ invalidOp: { key: "x", value: "y" } } as any)).toBe(false);
  });

  test("VALID_OPERATORS に 12 種が含まれる", () => {
    expect(VALID_OPERATORS.size).toBe(12);
  });
});

// ── normalizeRequest ──────────────────────────────────────────

describe("normalizeRequest", () => {
  test("numResults=0 は DEFAULT_NUM_RESULTS に補完される", () => {
    const req: QueryRequest = { query: "テスト", numResults: 0 };
    const normalized = normalizeRequest(req);
    expect(normalized.numResults).toBe(DEFAULT_NUM_RESULTS);
  });

  test("numResults が未指定の場合も DEFAULT_NUM_RESULTS に補完される", () => {
    const req: QueryRequest = { query: "テスト" };
    const normalized = normalizeRequest(req);
    expect(normalized.numResults).toBe(DEFAULT_NUM_RESULTS);
  });

  test("mode が未指定の場合 DEFAULT_MODE ('rag') に補完される", () => {
    const req: QueryRequest = { query: "テスト" };
    const normalized = normalizeRequest(req);
    expect(normalized.mode).toBe(DEFAULT_MODE);
  });

  test("query の前後空白が除去される", () => {
    const req: QueryRequest = { query: "  有給の申請  " };
    const normalized = normalizeRequest(req);
    expect(normalized.query).toBe("有給の申請");
  });

  test("指定済みの numResults はそのまま維持される", () => {
    const req: QueryRequest = { query: "テスト", numResults: 10 };
    const normalized = normalizeRequest(req);
    expect(normalized.numResults).toBe(10);
  });
});

// ── validateRequest ───────────────────────────────────────────

describe("validateRequest", () => {
  const valid: QueryRequest = { query: "有給休暇の申請方法は？" };

  test("有効なリクエストは valid=true", () => {
    const result = validateRequest(valid);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  test("query が空は valid=false", () => {
    const result = validateRequest({ query: "" });
    expect(result.valid).toBe(false);
  });

  test("num_results=-1 は valid=false", () => {
    const result = validateRequest({ query: "テスト", numResults: -1 });
    expect(result.valid).toBe(false);
  });

  test("mode='invalid' は valid=false", () => {
    const result = validateRequest({ query: "テスト", mode: "invalid" as any });
    expect(result.valid).toBe(false);
  });

  test("filter に不正な演算子は valid=false", () => {
    const result = validateRequest({ query: "テスト", filter: { badOp: {} } as any });
    expect(result.valid).toBe(false);
    expect(result.errors).toContain("filter のキーが不正です");
  });

  test("有効な filter は valid=true", () => {
    const result = validateRequest({
      query: "テスト",
      filter: { equals: { key: "category", value: "hr" } },
    });
    expect(result.valid).toBe(true);
  });
});

// ── extractAnswer ─────────────────────────────────────────────

describe("extractAnswer", () => {
  test("answer が存在する場合そのまま返す", () => {
    const response: RAGResponse = { query: "q", answer: "有給は社内ポータルから申請します。" };
    expect(extractAnswer(response)).toBe("有給は社内ポータルから申請します。");
  });

  test("answer が undefined の場合フォールバックを返す", () => {
    const response: RAGResponse = { query: "q" };
    expect(extractAnswer(response)).toBe("回答を取得できませんでした。");
  });

  test("answer が空文字の場合フォールバックを返す", () => {
    const response: RAGResponse = { query: "q", answer: "" };
    expect(extractAnswer(response)).toBe("回答を取得できませんでした。");
  });

  test("answer の前後空白のみはフォールバックを返す", () => {
    const response: RAGResponse = { query: "q", answer: "   " };
    expect(extractAnswer(response)).toBe("回答を取得できませんでした。");
  });
});

// ── extractSources ────────────────────────────────────────────

describe("extractSources", () => {
  test("S3 URI 一覧を抽出できる", () => {
    const citations: Citation[] = [
      { text: "内容1", source: "s3://bucket/doc1.txt" },
      { text: "内容2", source: "s3://bucket/doc2.txt" },
    ];
    const sources = extractSources(citations);
    expect(sources).toEqual(["s3://bucket/doc1.txt", "s3://bucket/doc2.txt"]);
  });

  test("source が空文字の Citation は除外される", () => {
    const citations: Citation[] = [
      { text: "内容1", source: "" },
      { text: "内容2", source: "s3://bucket/doc.txt" },
    ];
    const sources = extractSources(citations);
    expect(sources).toEqual(["s3://bucket/doc.txt"]);
  });

  test("空配列は空配列を返す", () => {
    expect(extractSources([])).toEqual([]);
  });
});

// ── sortChunksByScore ─────────────────────────────────────────

describe("sortChunksByScore", () => {
  test("スコア降順でソートされる", () => {
    const chunks: Chunk[] = [
      { text: "B", source: "s3://b", score: 0.7 },
      { text: "A", source: "s3://a", score: 0.9 },
      { text: "C", source: "s3://c", score: 0.5 },
    ];
    const sorted = sortChunksByScore(chunks);
    expect(sorted[0].score).toBe(0.9);
    expect(sorted[1].score).toBe(0.7);
    expect(sorted[2].score).toBe(0.5);
  });

  test("元の配列を変更しない（イミュータブル）", () => {
    const chunks: Chunk[] = [
      { text: "B", source: "s3://b", score: 0.7 },
      { text: "A", source: "s3://a", score: 0.9 },
    ];
    sortChunksByScore(chunks);
    expect(chunks[0].score).toBe(0.7);
  });

  test("空配列は空配列を返す", () => {
    expect(sortChunksByScore([])).toEqual([]);
  });
});

// ── formatResponseSummary ─────────────────────────────────────

describe("formatResponseSummary", () => {
  test("query を含むサマリーを返す", () => {
    const response: RAGResponse = { query: "有給の申請方法は？" };
    expect(formatResponseSummary(response)).toContain("query=");
  });

  test("answer が存在する場合 answer_len を含む", () => {
    const response: RAGResponse = { query: "q", answer: "回答です" };
    expect(formatResponseSummary(response)).toContain("answer_len=");
  });

  test("citations が存在する場合 citations 件数を含む", () => {
    const response: RAGResponse = {
      query: "q",
      citations: [{ text: "t", source: "s" }],
    };
    expect(formatResponseSummary(response)).toContain("citations=1");
  });

  test("session_id が存在する場合サマリーに含む", () => {
    const response: RAGResponse = { query: "q", sessionId: "abc-123" };
    expect(formatResponseSummary(response)).toContain("session_id=abc-123");
  });
});

// ── 追加テスト（件数拡充） ─────────────────────────────────────────

describe("validateQuery (詳細)", () => {
  test("1文字のクエリは valid=true", () => {
    expect(validateQuery("Q").valid).toBe(true);
  });

  test("改行のみは valid=false", () => {
    expect(validateQuery("\n").valid).toBe(false);
  });

  test("日本語クエリは valid=true", () => {
    expect(validateQuery("経費精算の締め日はいつですか？").valid).toBe(true);
  });
});

describe("validateMode (詳細)", () => {
  test("大文字 'RAG' は valid=false（case sensitive）", () => {
    expect(validateMode("RAG").valid).toBe(false);
  });

  test("大文字混在 'Retrieve' は valid=false", () => {
    expect(validateMode("Retrieve").valid).toBe(false);
  });

  test("'rag' は errors が空", () => {
    expect(validateMode("rag").errors).toHaveLength(0);
  });
});

describe("isValidFilter (詳細)", () => {
  test("'startsWith' は true", () => {
    expect(isValidFilter({ startsWith: { key: "title", value: "AWS" } })).toBe(true);
  });

  test("'greaterThan' は true", () => {
    expect(isValidFilter({ greaterThan: { key: "score", value: 0.8 } })).toBe(true);
  });

  test("'lessThan' は true", () => {
    expect(isValidFilter({ lessThan: { key: "year", value: 2024 } })).toBe(true);
  });

  test("有効+不正の演算子混在は false", () => {
    expect(
      isValidFilter({ equals: { key: "x", value: "y" }, badOp: {} } as any)
    ).toBe(false);
  });
});

describe("normalizeRequest (詳細)", () => {
  test("mode='retrieve' はそのまま維持される", () => {
    const req: QueryRequest = { query: "テスト", mode: "retrieve" };
    expect(normalizeRequest(req).mode).toBe("retrieve");
  });

  test("sessionId が保持される", () => {
    const req: QueryRequest = { query: "テスト", sessionId: "sess-abc" };
    expect(normalizeRequest(req).sessionId).toBe("sess-abc");
  });

  test("filter が保持される", () => {
    const filter = { equals: { key: "category", value: "hr" } };
    const req: QueryRequest = { query: "テスト", filter };
    expect(normalizeRequest(req).filter).toEqual(filter);
  });

  test("numResults=5（指定済み）はそのまま維持される", () => {
    const req: QueryRequest = { query: "テスト", numResults: 5 };
    expect(normalizeRequest(req).numResults).toBe(5);
  });
});

describe("validateRequest (詳細)", () => {
  test("numResults=21 は valid=false", () => {
    expect(validateRequest({ query: "テスト", numResults: 21 }).valid).toBe(false);
  });

  test("query 空 + mode 不正で複数エラーが含まれる", () => {
    const result = validateRequest({ query: "", mode: "bad" as any });
    expect(result.errors.length).toBeGreaterThanOrEqual(2);
  });

  test("mode='retrieve' は valid=true", () => {
    expect(validateRequest({ query: "テスト", mode: "retrieve" }).valid).toBe(true);
  });

  test("filter=null は valid=true（null は isValidFilter でスキップ）", () => {
    expect(validateRequest({ query: "テスト", filter: null as any }).valid).toBe(true);
  });
});

describe("extractAnswer (詳細)", () => {
  test("長い回答はそのまま返す", () => {
    const long = "回答".repeat(100);
    const response: RAGResponse = { query: "q", answer: long };
    expect(extractAnswer(response)).toBe(long);
  });

  test("answer が正しく trim される（前後空白のみでない場合は保持）", () => {
    const response: RAGResponse = { query: "q", answer: "  回答あり  " };
    expect(extractAnswer(response)).toBe("回答あり");
  });
});

describe("extractSources (詳細)", () => {
  test("単一 citation の source を返す", () => {
    const sources = extractSources([{ text: "t", source: "s3://bucket/file.txt" }]);
    expect(sources).toEqual(["s3://bucket/file.txt"]);
  });

  test("全 source が空文字なら空配列を返す", () => {
    const citations: Citation[] = [
      { text: "t1", source: "" },
      { text: "t2", source: "" },
    ];
    expect(extractSources(citations)).toEqual([]);
  });
});

describe("sortChunksByScore (詳細)", () => {
  test("単一チャンクはそのまま返す", () => {
    const chunks: Chunk[] = [{ text: "only", source: "s3://x", score: 0.8 }];
    expect(sortChunksByScore(chunks)).toHaveLength(1);
  });

  test("既ソート済みはそのまま（順序が変わらない）", () => {
    const chunks: Chunk[] = [
      { text: "A", source: "s3://a", score: 0.9 },
      { text: "B", source: "s3://b", score: 0.5 },
    ];
    const sorted = sortChunksByScore(chunks);
    expect(sorted[0].score).toBe(0.9);
    expect(sorted[1].score).toBe(0.5);
  });

  test("スコアが同じ場合も長さが変わらない", () => {
    const chunks: Chunk[] = [
      { text: "A", source: "s3://a", score: 0.7 },
      { text: "B", source: "s3://b", score: 0.7 },
    ];
    expect(sortChunksByScore(chunks)).toHaveLength(2);
  });
});

describe("formatResponseSummary (詳細)", () => {
  test("optional フィールドなしなら query のみ含む", () => {
    const response: RAGResponse = { query: "テスト質問" };
    const summary = formatResponseSummary(response);
    expect(summary).toContain('query="テスト質問"');
    expect(summary).not.toContain("answer_len");
    expect(summary).not.toContain("citations");
  });

  test("chunks が存在する場合 chunks 件数を含む", () => {
    const response: RAGResponse = {
      query: "q",
      chunks: [
        { text: "t1", source: "s3://a", score: 0.9 },
        { text: "t2", source: "s3://b", score: 0.8 },
      ],
    };
    expect(formatResponseSummary(response)).toContain("chunks=2");
  });

  test("answer_len の値が実際の文字列長と一致する", () => {
    const answer = "回答テスト";
    const response: RAGResponse = { query: "q", answer };
    const summary = formatResponseSummary(response);
    expect(summary).toContain(`answer_len=${answer.length}`);
  });
});

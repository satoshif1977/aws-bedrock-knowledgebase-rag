"use strict";

/**
 * aws-bedrock-knowledgebase-rag TypeScript クライアント 詳細ユニットテスト
 *
 * 境界値・エラーメッセージ内容・型保証・複合シナリオを中心に検証する。
 */

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
  DEFAULT_NUM_RESULTS,
  MIN_NUM_RESULTS,
  MAX_NUM_RESULTS,
} from "./rag-client";
import type { QueryRequest, RAGResponse, Citation, Chunk } from "./types";

// ── validateNumResults 詳細 ───────────────────────────────────

describe("validateNumResults (詳細)", () => {
  test("MIN+1（2）は valid=true", () => {
    expect(validateNumResults(MIN_NUM_RESULTS + 1).valid).toBe(true);
  });

  test("MAX-1（19）は valid=true", () => {
    expect(validateNumResults(MAX_NUM_RESULTS - 1).valid).toBe(true);
  });

  test("0 は errors が空", () => {
    expect(validateNumResults(0).errors).toHaveLength(0);
  });

  test("FAIL 時の errors メッセージに '1〜20' が含まれる", () => {
    const result = validateNumResults(-1);
    expect(result.errors[0]).toContain("1〜20");
  });
});

// ── validateMode 詳細 ─────────────────────────────────────────

describe("validateMode (詳細)", () => {
  test("'retrieve' は errors が空", () => {
    expect(validateMode("retrieve").errors).toHaveLength(0);
  });

  test("不正 mode の error message に 'rag' と 'retrieve' が含まれる", () => {
    const result = validateMode("unknown");
    expect(result.errors[0]).toContain("rag");
    expect(result.errors[0]).toContain("retrieve");
  });
});

// ── isValidFilter 詳細 ────────────────────────────────────────

describe("isValidFilter (詳細)", () => {
  test("'notEquals' は true", () => {
    expect(isValidFilter({ notEquals: { key: "status", value: "deleted" } })).toBe(true);
  });

  test("'greaterThanOrEquals' は true", () => {
    expect(isValidFilter({ greaterThanOrEquals: { key: "score", value: 0.5 } })).toBe(true);
  });

  test("'listContains' は true", () => {
    expect(isValidFilter({ listContains: { key: "tags", value: "aws" } })).toBe(true);
  });
});

// ── normalizeRequest 詳細 ─────────────────────────────────────

describe("normalizeRequest (詳細)", () => {
  test("DEFAULT_NUM_RESULTS は 5", () => {
    expect(DEFAULT_NUM_RESULTS).toBe(5);
  });

  test("1 文字のクエリもトリム後に正しく維持される", () => {
    const req: QueryRequest = { query: " Q " };
    expect(normalizeRequest(req).query).toBe("Q");
  });
});

// ── validateRequest 詳細 ──────────────────────────────────────

describe("validateRequest (詳細)", () => {
  test("numResults=0 は valid=true（デフォルト扱い）", () => {
    const result = validateRequest({ query: "テスト", numResults: 0 });
    expect(result.valid).toBe(true);
  });

  test("有効なリクエストの errors は空配列", () => {
    const result = validateRequest({ query: "有給の申請方法は？" });
    expect(result.errors).toEqual([]);
  });
});

// ── extractSources 詳細 ───────────────────────────────────────

describe("extractSources (詳細)", () => {
  test("有効な source が 2 件の場合 length が 2", () => {
    const citations: Citation[] = [
      { text: "t1", source: "s3://bucket/doc1.txt" },
      { text: "t2", source: "s3://bucket/doc2.txt" },
    ];
    expect(extractSources(citations)).toHaveLength(2);
  });

  test("返却される各 source は文字列型", () => {
    const citations: Citation[] = [
      { text: "t", source: "s3://bucket/file.pdf" },
    ];
    for (const src of extractSources(citations)) {
      expect(typeof src).toBe("string");
    }
  });
});

// ── sortChunksByScore 詳細 ────────────────────────────────────

describe("sortChunksByScore (詳細)", () => {
  test("score=0 のチャンクは末尾に来る", () => {
    const chunks: Chunk[] = [
      { text: "A", source: "s3://a", score: 0 },
      { text: "B", source: "s3://b", score: 0.8 },
      { text: "C", source: "s3://c", score: 0.5 },
    ];
    const sorted = sortChunksByScore(chunks);
    expect(sorted[sorted.length - 1].score).toBe(0);
  });

  test("ソート後も各チャンクの text フィールドが保持される", () => {
    const chunks: Chunk[] = [
      { text: "低スコア", source: "s3://a", score: 0.3 },
      { text: "高スコア", source: "s3://b", score: 0.9 },
    ];
    const sorted = sortChunksByScore(chunks);
    expect(sorted[0].text).toBe("高スコア");
    expect(sorted[1].text).toBe("低スコア");
  });

  test("3 要素ソートで先頭が最高スコア・末尾が最低スコア", () => {
    const chunks: Chunk[] = [
      { text: "C", source: "s3://c", score: 0.4 },
      { text: "A", source: "s3://a", score: 0.95 },
      { text: "B", source: "s3://b", score: 0.6 },
    ];
    const sorted = sortChunksByScore(chunks);
    expect(sorted[0].score).toBeGreaterThan(sorted[1].score);
    expect(sorted[1].score).toBeGreaterThan(sorted[2].score);
  });
});

// ── formatResponseSummary 詳細 ────────────────────────────────

describe("formatResponseSummary (詳細)", () => {
  test("query の値がダブルクォートで囲まれる", () => {
    const response: RAGResponse = { query: "テスト" };
    const summary = formatResponseSummary(response);
    expect(summary).toContain('"テスト"');
  });

  test("citations が空配列の場合 citations は含まれない", () => {
    const response: RAGResponse = { query: "q", citations: [] };
    expect(formatResponseSummary(response)).not.toContain("citations");
  });

  test("citations が 3 件の場合 'citations=3' が含まれる", () => {
    const response: RAGResponse = {
      query: "q",
      citations: [
        { text: "t1", source: "s1" },
        { text: "t2", source: "s2" },
        { text: "t3", source: "s3" },
      ],
    };
    expect(formatResponseSummary(response)).toContain("citations=3");
  });
});

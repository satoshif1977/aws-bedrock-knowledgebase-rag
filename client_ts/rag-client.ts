/**
 * aws-bedrock-knowledgebase-rag: TypeScript クライアントユーティリティ
 *
 * Python 版 lambda/query_handler.py および
 * Go 版 lambda_go/query_handler/main.go に対応する型安全なユーティリティ関数群。
 * AWS 呼び出し部分を分離し、ビジネスロジックをテスト可能に設計。
 */

import type {
  QueryRequest,
  RAGResponse,
  Citation,
  Chunk,
  ValidationResult,
  FilterExpression,
  FilterOperator,
} from "./types";

// ── 定数 ─────────────────────────────────────────────────────

export const VALID_OPERATORS: ReadonlySet<FilterOperator> = new Set([
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
]);

export const DEFAULT_NUM_RESULTS = 5;
export const MIN_NUM_RESULTS = 1;
export const MAX_NUM_RESULTS = 20;
export const DEFAULT_MODE = "rag" as const;

// ── クエリバリデーション ──────────────────────────────────────

/**
 * query フィールドを検証する
 * Go 版 Handler() の strings.TrimSpace + 空チェックに対応
 */
export function validateQuery(query: string): ValidationResult {
  const trimmed = query.trim();
  if (trimmed === "") {
    return { valid: false, errors: ["query は必須です"] };
  }
  return { valid: true, errors: [] };
}

/**
 * num_results フィールドを検証する
 * Go 版の範囲チェック（1〜20、0 はデフォルト扱い）に対応
 */
export function validateNumResults(numResults: number): ValidationResult {
  if (numResults === 0) {
    return { valid: true, errors: [] };
  }
  if (numResults < MIN_NUM_RESULTS || numResults > MAX_NUM_RESULTS) {
    return {
      valid: false,
      errors: [`num_results は ${MIN_NUM_RESULTS}〜${MAX_NUM_RESULTS} の範囲で指定してください`],
    };
  }
  return { valid: true, errors: [] };
}

/**
 * mode フィールドを検証する
 * Go 版のモードチェックに対応
 */
export function validateMode(mode: string): ValidationResult {
  if (mode !== "rag" && mode !== "retrieve") {
    return {
      valid: false,
      errors: ["mode は 'rag' または 'retrieve' を指定してください"],
    };
  }
  return { valid: true, errors: [] };
}

// ── フィルターバリデーション ──────────────────────────────────

/**
 * メタデータフィルターのオペレーターを検証する
 * Go 版 isValidFilter() に対応
 */
export function isValidFilter(filter: FilterExpression | null | undefined): boolean {
  if (!filter || Object.keys(filter).length === 0) {
    return false;
  }
  return Object.keys(filter).every((key) => VALID_OPERATORS.has(key as FilterOperator));
}

// ── リクエスト正規化 ─────────────────────────────────────────

/**
 * QueryRequest を正規化する（デフォルト値の補完）
 * Go 版 Handler() のゼロ値補完ロジックに対応
 */
export function normalizeRequest(req: QueryRequest): Required<Omit<QueryRequest, "sessionId" | "filter">> & Pick<QueryRequest, "sessionId" | "filter"> {
  return {
    query: req.query.trim(),
    numResults: req.numResults === undefined || req.numResults === 0 ? DEFAULT_NUM_RESULTS : req.numResults,
    mode: req.mode ?? DEFAULT_MODE,
    sessionId: req.sessionId,
    filter: req.filter,
  };
}

/**
 * QueryRequest 全体を検証する
 */
export function validateRequest(req: QueryRequest): ValidationResult {
  const errors: string[] = [];

  const queryResult = validateQuery(req.query);
  if (!queryResult.valid) errors.push(...queryResult.errors);

  if (req.numResults !== undefined) {
    const numResult = validateNumResults(req.numResults);
    if (!numResult.valid) errors.push(...numResult.errors);
  }

  if (req.mode !== undefined) {
    const modeResult = validateMode(req.mode);
    if (!modeResult.valid) errors.push(...modeResult.errors);
  }

  if (req.filter !== undefined && req.filter !== null && !isValidFilter(req.filter)) {
    errors.push("filter のキーが不正です");
  }

  return { valid: errors.length === 0, errors };
}

// ── レスポンス加工ユーティリティ ──────────────────────────────

/**
 * RAGResponse から回答テキストを取得する
 * 回答がない場合はフォールバックメッセージを返す
 */
export function extractAnswer(response: RAGResponse): string {
  return response.answer?.trim() || "回答を取得できませんでした。";
}

/**
 * Citation 配列から S3 URI 一覧を抽出する
 */
export function extractSources(citations: Citation[]): string[] {
  return citations.map((c) => c.source).filter((s) => s !== "");
}

/**
 * Chunk 配列をスコア降順でソートする
 */
export function sortChunksByScore(chunks: Chunk[]): Chunk[] {
  return [...chunks].sort((a, b) => b.score - a.score);
}

/**
 * RAGResponse のサマリー文字列を生成する（ログ・デバッグ用）
 */
export function formatResponseSummary(response: RAGResponse): string {
  const parts: string[] = [`query="${response.query}"`];
  if (response.answer) {
    parts.push(`answer_len=${response.answer.length}`);
  }
  if (response.citations?.length) {
    parts.push(`citations=${response.citations.length}`);
  }
  if (response.chunks?.length) {
    parts.push(`chunks=${response.chunks.length}`);
  }
  if (response.sessionId) {
    parts.push(`session_id=${response.sessionId}`);
  }
  return parts.join(" ");
}

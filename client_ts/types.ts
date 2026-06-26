/**
 * aws-bedrock-knowledgebase-rag: TypeScript 型定義
 *
 * Python 版（lambda/query_handler.py）・Go 版（lambda_go/query_handler/main.go）との対応:
 *   - QueryRequest   ← Python/Go の QueryRequest 構造体
 *   - Chunk          ← Go の Chunk 構造体
 *   - Citation       ← Go の Citation 構造体
 *   - RAGResponse    ← Python/Go の RAGResponse 構造体
 */

// ── クエリリクエスト型 ────────────────────────────────────────

export type RAGMode = "rag" | "retrieve";

export interface QueryRequest {
  query: string;
  numResults?: number;
  sessionId?: string;
  mode?: RAGMode;
  filter?: FilterExpression;
}

// ── メタデータフィルター型 ───────────────────────────────────
// Go 版 isValidFilter() の validOperators に対応

export type FilterOperator =
  | "equals"
  | "notEquals"
  | "greaterThan"
  | "lessThan"
  | "greaterThanOrEquals"
  | "lessThanOrEquals"
  | "startsWith"
  | "in"
  | "notIn"
  | "listContains"
  | "andAll"
  | "orAll";

export type FilterExpression = Partial<Record<FilterOperator, unknown>>;

// ── レスポンス型 ─────────────────────────────────────────────

export interface Chunk {
  text: string;
  source: string;
  score: number;
  metadata?: Record<string, unknown>;
}

export interface Citation {
  text: string;
  source: string;
  metadata?: Record<string, unknown>;
}

export interface RAGResponse {
  query: string;
  answer?: string;
  citations?: Citation[];
  sessionId?: string;
  chunks?: Chunk[];
}

// ── バリデーション結果型 ──────────────────────────────────────

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

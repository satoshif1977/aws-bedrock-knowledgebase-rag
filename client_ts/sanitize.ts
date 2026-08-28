/**
 * クエリ入力のサニタイズ・安全性チェックユーティリティ
 *
 * RAG パイプラインに渡す前にユーザー入力を正規化・検証する。
 * プロンプトインジェクション対策の基本的なガードレールを提供する。
 */

// ── 定数 ─────────────────────────────────────────────────────
export const MAX_QUERY_LENGTH = 2000;
export const MIN_QUERY_LENGTH = 1;

/** 制御文字（C0/C1）の正規表現。改行・タブは許可する。 */
const CONTROL_CHARS_PATTERN = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]/g;

/** プロンプトインジェクションの疑いがあるパターン */
const INJECTION_PATTERNS: readonly RegExp[] = [
  /ignore\s+(all\s+)?previous\s+instructions/i,
  /disregard\s+(all\s+)?previous/i,
  /you\s+are\s+now\s+/i,
  /system\s*:\s*/i,
  /\<\/?system\>/i,
  /\[\s*INST\s*\]/i,
];

// ── サニタイズ結果型 ─────────────────────────────────────────
export interface SanitizeResult {
  sanitized: string;
  original: string;
  wasModified: boolean;
  warnings: string[];
}

export interface SafetyCheckResult {
  safe: boolean;
  reasons: string[];
}

// ── サニタイズ関数 ───────────────────────────────────────────

/**
 * クエリ文字列をサニタイズする。
 * - 前後の空白を除去
 * - 制御文字を除去（改行・タブは保持）
 * - 連続する空白を単一スペースに正規化
 */
export function sanitizeQuery(query: string): SanitizeResult {
  const original = query;
  const warnings: string[] = [];

  let sanitized = query.trim();

  const controlRemoved = sanitized.replace(CONTROL_CHARS_PATTERN, "");
  if (controlRemoved !== sanitized) {
    warnings.push("制御文字を除去しました");
    sanitized = controlRemoved;
  }

  const normalized = sanitized.replace(/[^\S\n]+/g, " ");
  if (normalized !== sanitized) {
    warnings.push("連続する空白を正規化しました");
    sanitized = normalized;
  }

  sanitized = sanitized.trim();

  return {
    sanitized,
    original,
    wasModified: sanitized !== original,
    warnings,
  };
}

/**
 * クエリの長さを検証する。
 */
export function checkQueryLength(query: string): SafetyCheckResult {
  const reasons: string[] = [];

  if (query.length < MIN_QUERY_LENGTH) {
    reasons.push(`クエリが短すぎます（最小${MIN_QUERY_LENGTH}文字）`);
  }

  if (query.length > MAX_QUERY_LENGTH) {
    reasons.push(`クエリが長すぎます（最大${MAX_QUERY_LENGTH}文字、現在${query.length}文字）`);
  }

  return { safe: reasons.length === 0, reasons };
}

/**
 * プロンプトインジェクションの基本的な検出を行う。
 * 疑わしいパターンが含まれている場合は safe: false を返す。
 */
export function checkInjection(query: string): SafetyCheckResult {
  const reasons: string[] = [];

  for (const pattern of INJECTION_PATTERNS) {
    if (pattern.test(query)) {
      reasons.push(`不正なパターンを検出: ${pattern.source}`);
    }
  }

  return { safe: reasons.length === 0, reasons };
}

/**
 * サニタイズ + 全チェックを一括で実行する。
 */
export function sanitizeAndCheck(query: string): SanitizeResult & { safety: SafetyCheckResult } {
  const result = sanitizeQuery(query);
  const lengthCheck = checkQueryLength(result.sanitized);
  const injectionCheck = checkInjection(result.sanitized);

  const allReasons = [...lengthCheck.reasons, ...injectionCheck.reasons];

  return {
    ...result,
    safety: {
      safe: lengthCheck.safe && injectionCheck.safe,
      reasons: allReasons,
    },
  };
}

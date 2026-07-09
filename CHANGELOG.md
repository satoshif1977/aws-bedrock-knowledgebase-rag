# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [1.8.0] - 2026-07-10

### Added
- Python ユニットテスト 16 件 → 39 件に拡充（境界値・エラーメッセージ・複合パターン）
- Go ユニットテスト 17 件 → 37 件に拡充（境界値・デフォルト動作・RAGResponse JSON 等）
- ruff / black CI ワークフロー追加（`python-ci.yml`）

### Fixed
- `test_query_handler.py`: black フォーマット修正

### Changed
- Dependabot: `boto3` v1.43.36 → v1.43.40 更新・`actions/setup-node` v4 → v6 更新

## [1.7.0] - 2026-06-26

### Added
- **Go Lambda 並置版** (`lambda_go/query_handler/`)
  - Python 版 `lambda/query_handler.py` を Go で再実装
  - Bedrock Agent Runtime SDK（RetrieveAndGenerate / Retrieve）使用
  - `rag` / `retrieve` モード対応
  - フィルター演算子バリデーション（12種）
  - ユニットテスト 20 件（`main_test.go`）
- **TypeScript クライアントユーティリティ** (`client_ts/`)
  - Python/Go 版と対応する型定義（`types.ts`）
  - バリデーション・正規化・レスポンス加工ユーティリティ（`rag-client.ts`）
  - Jest テスト 49 件（`rag-client.test.ts`）、全件 PASS
- **CI ワークフロー追加**
  - `go-test.yml`: Go ユニットテスト CI
  - `ts-test.yml`: TypeScript Jest テスト CI（typecheck 込み）
- **README 更新**
  - Go / TypeScript バッジ追加
  - 3 言語比較表・言語並置ディレクトリ構成を追記

## [1.6.0] - 2026-06-18

### Changed
- `ci.yml`: `terraform_version` を `~1.6` → `~1.9` に更新（他リポジトリと統一）

## [1.5.0] - 2026-06-16

### Changed
- boto3 >=1.43.18 -> >=1.43.29
- streamlit >=1.57.0 -> >=1.58.0

## [1.4.0] - 2026-06-04

### Added
- **メタデータフィルタリング強化**
  - Lambda `query_handler.py`: `filter` パラメータを受け取り Bedrock KB API に渡す
  - 対応演算子: `equals` / `notEquals` / `startsWith` / `greaterThanOrEquals` / `lessThanOrEquals` / `in` / `listContains` / `andAll` / `orAll`
  - 不正な演算子名は 400 バリデーションエラーで返す
  - Streamlit UI: 演算子ドロップダウンを追加（5種類から選択可能）
- **ソース引用表示の改善**
  - `_source_label()` ヘルパー: S3 URI から人間が読みやすいファイル名を抽出
  - 引用・検索結果の表示を `s3://...` 生 URI → ファイル名に変更（フルパスはサブテキストで表示）
  - `citations` / `chunks` に `metadata` フィールドを追加（chunk ID・data source ID 等）
  - 検索結果 expander 内でメタデータキーを一覧表示
  - RAG 引用 expander 内で `x-amz-bedrock-kb-chunk-id` を表示
- **テスト追加**（4ケース）
  - フィルター付き Retrieve で `filter` が API に渡ること
  - フィルター付き RAG で `filter` が API に渡ること
  - `citations` に `metadata` が含まれること
  - 不正な `filter` キーで 400 を返すこと（合計 16 件）

## [1.3.0] - 2026-06-01

### Changed
- hashicorp/aws provider を v5 から v6 にアップグレード（`terraform plan` で 0 changes/0 destroys 確認済み）
- streamlit を >=1.57.0 に更新
- GitHub Actions: `actions/setup-python` を v6 に更新、`hashicorp/setup-terraform` を v4 に更新

## [1.2.1] - 2026-05-26

### Added
- `.gitignore` に draw.io バックアップ（`.*.bkp`）パターンを追加
- `knowledge_docs/sample.txt` をリポジトリに追加
- `docs/screenshots/demo.gif` をリポジトリに追加

### Fixed
- README のモデル名を `Claude 3 Haiku` → `Claude 3.5 Haiku` に統一（3か所）

## [1.2.0] - 2026-05-26

### Added
- `app.py`: サイドバーにメタデータフィルター UI 追加（キー・値のイコールフィルター）
- `lambda/query_handler.py`: リクエスト body から `num_results` を受け取れるよう対応（デフォルト: 5）

### Fixed
- `app.py`: `region_name` ハードコードを `AWS_DEFAULT_REGION` 環境変数参照に修正

## [1.1.0] - 2026-05-19

### Added
- CONTRIBUTING.md 追加（PR プロセス・スタイルガイド）

### Changed
- Claude 3 Haiku → Claude 3.5 Haiku（`anthropic.claude-3-5-haiku-20241022-v1:0`）に移行（EOL: 2026-09-10）

## [1.0.1] - 2026-05-13

### Added
- SECURITY.md 追加
- README にトラブルシューティング・ローカル開発テスト方法セクション追加

### Fixed
- `lambda/query_handler.py` の `region_name="ap-northeast-1"` ハードコードを環境変数参照に修正
- `os.environ["KEY"]` を `os.environ.get("KEY")` + 起動時バリデーションに統一（`KeyError` 防止）

## [1.0.0] - 2026-03-16

### Added
- 初回実装：Amazon Bedrock Knowledge Bases（OpenSearch Serverless）による本格 RAG
  - Bedrock Knowledge Base で S3 ドキュメントをベクトル化・インデックス化
  - `RetrieveAndGenerate` API で RAG 回答生成
  - Streamlit Web UI
- Terraform IaC（Bedrock KB / OpenSearch Serverless / S3 / Lambda / IAM）
- GitHub Actions CI（Python lint + Checkov セキュリティスキャン）

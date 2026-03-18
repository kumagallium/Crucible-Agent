# テスト概要

## CI

GitHub Actions で push / PR 時に自動実行される。
結果は Actions の Summary タブにカバレッジテーブルとして表示。

```
.github/workflows/test.yml
```

---

## テスト実行

```bash
pip install -e ".[dev]"
pytest
```

### テストファイル一覧

| ファイル | 件数 | 対象 |
|---------|------|------|
| `test_config.py` | 8 | 設定管理 (Settings) |
| `test_schemas.py` | 16 | Pydantic スキーマ |
| `test_discovery.py` | 8 | Crucible Registry 自動検出 |
| `test_loader.py` | 10 | プロンプトプロファイル管理 |
| `test_adapter.py` | 28 | mcp-agent 結合層 |
| `test_runner.py` | 9 | エージェント実行オーケストレーション |
| `test_routes.py` | 16 | FastAPI エンドポイント |
| `test_provenance.py` | 12 | PROV-DM 来歴記録（Python 3.10+） |

### 各モジュールのテスト内容

**test_config.py** — 設定管理
- Settings の全フィールド存在・型確認
- 環境変数によるオーバーライド

**test_schemas.py** — API スキーマ
- AgentRunRequest: 必須/オプションフィールド、デフォルト値
- AgentRunOptions: max_turns=10, require_approval=False
- TokenUsage: 初期値 0
- AgentRunResponse, ToolCallRecord, HealthResponse, ToolInfo, ProfileInfo の構築

**test_discovery.py** — Crucible Registry 連携
- API レスポンスのパース（/mcp → streamable-http, /sse → sse）
- running サーバーのみフィルタ
- 接続エラー/タイムアウト → 空リスト（フォールバック）
- API キーヘッダーの付与
- 空レスポンスの処理

**test_loader.py** — プロンプトプロファイル
- `list_profiles`: ディレクトリ名取得、ドットディレクトリ除外、空ディレクトリ
- `load_profile`: 既存プロファイルの読み込み、未存在 → BASE_PROMPT
- `build_instruction`: 引数なし → BASE_PROMPT、プロファイル指定、カスタム指示の追加

**test_adapter.py** — mcp-agent 結合層
- `_discovered_to_server_configs`: streamable-http→sse 変換、空リスト
- イベント抽出ヘルパー群: `_get_event_type`, `_get_event_content`, `_get_tool_id`, `_get_tool_name`, `_get_tool_input`, `_get_tool_output`, `_get_token_usage`（属性/dict/欠落の各パターン）
- `_extract_tool_call`: ツール呼び出し情報の抽出
- `run()`: ストリーミング成功、`generate_str` へのフォールバック
- `run_stream()`: text_delta / tool_use / done イベントの送出

**test_runner.py** — エージェント実行
- `_resolve_servers`: 明示指定→フィルタ、None→全返却、空結果
- `run_agent`: 成功、プロファイル指定、カスタム指示、session_id 自動生成
- `run_agent_stream`: イベント中継、承認パラメータ転送

**test_routes.py** — API エンドポイント
- GET /health: 全コンポーネント正常→healthy、LiteLLM/Crucible 異常→degraded
- GET /tools: ツール一覧取得、検出失敗→空リスト
- GET /profiles: プロファイル一覧
- POST /agent/run: 成功、例外時の動作、422 バリデーション、来歴記録失敗の影響なし

**test_provenance.py** — 来歴記録（Python 3.10+ のみ）
- SQLAlchemy モデル: テーブル名、カラム、外部キー
- `record_agent_run`: Activity + Entity 作成、ツール呼び出し分の追加 Entity、長文の切り詰め
- `get_session_history`: 時系列順の返却

### モック戦略

| 外部依存 | モック方法 |
|---------|----------|
| mcp-agent ライブラリ | `sys.modules` にモック登録 |
| Crucible Registry API | `httpx.AsyncClient` をモック |
| PostgreSQL | `AsyncMock` でセッションをモック |
| LiteLLM | httpx モック（ヘルスチェック） |
| Settings (.env) | conftest.py で TestSettings に差し替え |

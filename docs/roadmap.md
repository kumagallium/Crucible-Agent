# Roadmap: Crucible Agent

## 概要

Crucible Agent は **任意のフロントエンドから MCP サーバー群を活用する汎用エージェントランタイム**。
本ロードマップはフェーズごとに「動くもの」を積み上げる方針で構成する。

## ターゲットディレクトリ構成

```
src/crucible_agent/
├── __init__.py
├── main.py              ← FastAPI エントリポイント
├── config.py            ← 設定管理（pydantic-settings）
│
├── api/                 ← REST / WebSocket エンドポイント
│   ├── __init__.py
│   ├── routes.py        ← POST /agent/run, WS /agent/ws, GET /health, GET /tools
│   └── schemas.py       ← Pydantic リクエスト/レスポンスモデル
│
├── agent/               ← mcp-agent ラッパー（薄いアダプター層）
│   ├── __init__.py
│   ├── runner.py        ← エージェントループ実行
│   └── adapter.py       ← mcp-agent との結合（ここだけ外部依存）
│
├── crucible/            ← Crucible 連携
│   ├── __init__.py
│   └── discovery.py     ← Crucible API からツール自動検出
│
├── provenance/          ← PROV-DM 来歴記録
│   ├── __init__.py
│   ├── recorder.py      ← エージェント行動の記録
│   └── models.py        ← DB モデル（SQLAlchemy）
│
└── prompts/             ← プロンプトプロファイル
    ├── __init__.py
    ├── loader.py        ← プロファイル読み込み・切り替え
    └── templates/       ← ドメイン別プロンプト
        └── science/
            └── experiment_planner.md
```

---

## Phase 1: 最小限の動作（垂直スライス）

**ゴール**: `docker compose up` → health check OK → 1メッセージ送って LLM 応答が返る

| # | ファイル | 内容 |
|---|---------|------|
| 1 | `config.py` | pydantic-settings で環境変数を読み込む (`LITELLM_API_BASE`, `LLM_MODEL` など) |
| 2 | `main.py` | FastAPI app 作成、ルーターマウント |
| 3 | `api/schemas.py` | `AgentRunRequest`, `AgentRunResponse` の Pydantic モデル |
| 4 | `api/routes.py` | `GET /health`, `POST /agent/run` のスケルトン |
| 5 | `agent/adapter.py` | mcp-agent `MCPApp` + `OpenAIAugmentedLLM` の最小接続 |
| 6 | `agent/runner.py` | adapter を呼び出すシンプルなラッパー |

**検証方法**:
```bash
docker compose up -d
curl http://localhost:8090/health
curl -X POST http://localhost:8090/agent/run \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}'
```

**判断ポイント**:
- mcp-agent の安定性を実際に確認する
- 不安定であれば adapter_fallback.py（MCP Python SDK 直接利用）に早期切り替え

---

## Phase 2: Crucible 連携

**ゴール**: Crucible に登録された MCP サーバーを自動検出し、ツールとして利用できる

| # | ファイル | 内容 |
|---|---------|------|
| 1 | `crucible/discovery.py` | `GET /api/servers` → `ServerConfig` リストに変換 |
| 2 | `api/routes.py` | `GET /tools` エンドポイント追加 |
| 3 | `agent/runner.py` | discovery 結果を adapter に渡す |

**フォールバック**: Crucible 接続不可時は `mcp_agent.config.yaml` の直書き設定を使用

**検証方法**:
```bash
# Crucible が起動している状態で
curl http://localhost:8090/tools
# → Crucible に登録されたツール一覧が返る

curl -X POST http://localhost:8090/agent/run \
  -d '{"message": "利用可能なツールを教えて"}'
# → 検出されたツールを使った応答が返る
```

---

## Phase 3: ストリーミング + 来歴記録

**ゴール**: WebSocket でリアルタイム応答、全 tool_use ステップを DB に記録

| # | ファイル | 内容 |
|---|---------|------|
| 1 | `api/routes.py` | `WS /agent/ws` エンドポイント |
| 2 | `api/schemas.py` | WebSocket メッセージ型 (`text_delta`, `tool_start`, `tool_end` 等) |
| 3 | `provenance/models.py` | SQLAlchemy モデル (Entity, Activity, Agent) |
| 4 | `provenance/recorder.py` | tool_use ステップごとに PROV-DM レコード作成 |
| 5 | Alembic 初期化 | DB マイグレーション設定 |

**検証方法**:
```bash
# WebSocket テスト（websocat 等で）
websocat ws://localhost:8090/agent/ws
> {"type": "message", "content": "hello"}
# → text_delta, done 等のストリームが返る

# DB に来歴が記録されていることを確認
docker compose exec postgres psql -U agent -d crucible_agent \
  -c "SELECT * FROM activities ORDER BY created_at DESC LIMIT 5;"
```

---

## Phase 4: プロンプトプロファイル

**ゴール**: ドメイン別のプロンプトを切り替えられる仕組み

| # | ファイル | 内容 |
|---|---------|------|
| 1 | `prompts/loader.py` | `templates/` 配下のプロファイルを名前で読み込む |
| 2 | `api/routes.py` | `POST /profile-config` — プロファイル設定の登録・更新 |
| 3 | `api/schemas.py` | プロファイル設定のリクエスト/レスポンスモデル |
| 4 | `agent/runner.py` | プロファイルからシステムプロンプトを構築 |

**プロファイル構成例**:
```
templates/
├── science/
│   └── experiment_planner.md    ← 実験計画・データ解析支援
├── devops/
│   └── incident_responder.md    ← 障害対応・インフラ運用
└── general/
    └── assistant.md             ← 汎用アシスタント
```

---

## 設計原則（全フェーズ共通）

1. **薄いアダプター層**: mcp-agent 依存は `adapter.py` に集約。破壊的変更時はここだけ差し替える
2. **LiteLLM 迂回可能**: `LITELLM_API_BASE` を変えるだけで直接 LLM に接続できる
3. **Crucible 疎結合**: Crucible なしでも `mcp_agent.config.yaml` 直書きで動作する
4. **非同期ファースト**: async/await をデフォルトにする
5. **型安全**: Pydantic モデルと型ヒントを必須にする

## 依存関係の注意

| ライブラリ | リスク | 対策 |
|-----------|--------|------|
| mcp-agent (lastmile-ai) | v0.x 台で API 不安定 | adapter.py に隔離、fallback 実装を準備 |
| LiteLLM | Proxy の挙動変更 | 環境変数で迂回可能な設計 |
| MCP SDK | プロトコル進化中 | SSE → Streamable HTTP 移行に備える |

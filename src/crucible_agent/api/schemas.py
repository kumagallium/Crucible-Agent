"""Pydantic リクエスト/レスポンスモデル"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- POST /agent/run ---


class AgentRunOptions(BaseModel):
    """エージェント実行オプション"""

    max_turns: int = Field(default=10, description="最大ループ回数")
    require_approval: bool = Field(default=False, description="tool 実行前に承認を求めるか")
    model: str | None = Field(default=None, description="使用モデル名（省略時は環境変数 LLM_MODEL）")


class AgentRunRequest(BaseModel):
    """POST /agent/run リクエスト"""

    message: str = Field(..., description="ユーザーのメッセージ")
    session_id: str | None = Field(default=None, description="会話セッション ID（省略時は新規作成）")
    profile_config_id: str | None = Field(default=None, description="プロファイル設定 ID")
    options: AgentRunOptions = Field(default_factory=AgentRunOptions)


class ToolCallRecord(BaseModel):
    """ツール呼び出しの記録"""

    tool_name: str
    server: str
    input: dict
    output: dict
    duration_ms: int


class TokenUsage(BaseModel):
    """トークン使用量"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class AgentRunResponse(BaseModel):
    """POST /agent/run レスポンス"""

    session_id: str
    message: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    provenance_id: str | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)


# --- GET /health ---


class HealthResponse(BaseModel):
    """GET /health レスポンス"""

    status: str = "healthy"
    components: dict[str, str] = Field(default_factory=dict)
    version: str

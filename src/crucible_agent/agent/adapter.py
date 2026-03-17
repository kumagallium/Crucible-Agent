"""mcp-agent との結合層 — 外部依存はここに集約する

mcp-agent が破壊的変更を入れた場合、このファイルだけ差し替えれば済む設計。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.config import (
    MCPServerSettings,
    MCPSettings,
    OpenAISettings,
    Settings as MCPAgentSettings,
)
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM

from crucible_agent.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AdapterResult:
    """adapter の実行結果"""

    message: str
    tool_calls: list[dict]
    token_usage: dict


def _build_mcp_settings(server_configs: dict[str, MCPServerSettings] | None = None) -> MCPAgentSettings:
    """mcp-agent 用の Settings を組み立てる"""
    mcp = MCPSettings(servers=server_configs or {})
    openai = OpenAISettings(
        default_model=settings.llm_model,
        base_url=f"{settings.litellm_api_base}/v1",
    )
    return MCPAgentSettings(
        execution_engine="asyncio",
        mcp=mcp,
        openai=openai,
    )


# アプリケーションレベルの MCPApp インスタンス
_mcp_app: MCPApp | None = None


def get_mcp_app(
    server_configs: dict[str, MCPServerSettings] | None = None,
) -> MCPApp:
    """MCPApp のシングルトンを取得（初回呼び出し時に生成）"""
    global _mcp_app
    if _mcp_app is None:
        mcp_settings = _build_mcp_settings(server_configs)
        _mcp_app = MCPApp(name="crucible_agent", settings=mcp_settings)
        logger.info("MCPApp initialized (model=%s, base_url=%s)", settings.llm_model, settings.litellm_api_base)
    return _mcp_app


async def run(
    instruction: str,
    message: str,
    server_names: list[str] | None = None,
) -> AdapterResult:
    """mcp-agent を使ってエージェントを1回実行する

    Args:
        instruction: システムプロンプト
        message: ユーザーメッセージ
        server_names: 使用する MCP サーバー名リスト
    """
    mcp_app = get_mcp_app()

    async with mcp_app.run():
        agent = Agent(
            name="crucible_assistant",
            instruction=instruction,
            server_names=server_names or [],
        )

        async with agent:
            llm = await agent.attach_llm(OpenAIAugmentedLLM)
            result = await llm.generate_str(message)

    return AdapterResult(
        message=result,
        tool_calls=[],  # Phase 3 で tool_call 記録を実装
        token_usage={},  # Phase 3 で token_usage 記録を実装
    )

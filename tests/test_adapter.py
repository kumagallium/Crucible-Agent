"""adapter.py のテスト — MCP SDK + httpx 実装"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from crucible_agent.agent.adapter import (
    AdapterResult,
    StreamEvent,
    _call_tool,
    run,
    run_stream,
)


class TestCallTool:
    @pytest.mark.asyncio
    async def test_tool_found_and_called(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "tool output"
        mock_result.content = [mock_block]
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        sessions = {"my_tool": mock_session}
        result = await _call_tool(sessions, "my_tool", {"arg": "val"})
        assert result == "tool output"
        mock_session.call_tool.assert_called_once_with("my_tool", {"arg": "val"})

    @pytest.mark.asyncio
    async def test_tool_not_found(self):
        result = await _call_tool({}, "missing_tool", {})
        data = json.loads(result)
        assert "error" in data
        assert "missing_tool" in data["error"]

    @pytest.mark.asyncio
    async def test_tool_call_exception(self):
        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(side_effect=RuntimeError("connection lost"))

        result = await _call_tool({"broken": mock_session}, "broken", {})
        data = json.loads(result)
        assert "error" in data
        assert "connection lost" in data["error"]


class TestRun:
    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        llm_response = {
            "choices": [{"message": {"content": "Hello!", "role": "assistant"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        with patch("crucible_agent.agent.adapter._connect_servers", new_callable=AsyncMock) as mock_connect, \
             patch("crucible_agent.agent.adapter._call_llm", new_callable=AsyncMock) as mock_llm:
            mock_connect.return_value = ({}, [])
            mock_llm.return_value = llm_response

            result = await run("instruction", "hello")

        assert isinstance(result, AdapterResult)
        assert result.message == "Hello!"
        assert result.token_usage["total_tokens"] == 15
        assert result.tool_calls == []

    @pytest.mark.asyncio
    async def test_tool_call_loop(self):
        # 1回目: LLM がツール呼び出し
        llm_tool_response = {
            "choices": [{"message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "tc1",
                    "function": {"name": "search", "arguments": '{"q": "test"}'},
                }],
            }}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        # 2回目: LLM がテキスト応答
        llm_text_response = {
            "choices": [{"message": {"content": "Found it!", "role": "assistant"}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "search result"
        mock_result.content = [mock_block]
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with patch("crucible_agent.agent.adapter._connect_servers", new_callable=AsyncMock) as mock_connect, \
             patch("crucible_agent.agent.adapter._call_llm", new_callable=AsyncMock) as mock_llm:
            mock_connect.return_value = ({"search": mock_session}, [{"type": "function", "function": {"name": "search"}}])
            mock_llm.side_effect = [llm_tool_response, llm_text_response]

            result = await run("instruction", "hello")

        assert result.message == "Found it!"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["tool_name"] == "search"


class TestRunStream:
    @pytest.mark.asyncio
    async def test_text_response_stream(self):
        llm_response = {
            "choices": [{"message": {"content": "Streamed!", "role": "assistant"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }

        with patch("crucible_agent.agent.adapter._connect_servers", new_callable=AsyncMock) as mock_connect, \
             patch("crucible_agent.agent.adapter._call_llm", new_callable=AsyncMock) as mock_llm:
            mock_connect.return_value = ({}, [])
            mock_llm.return_value = llm_response

            events = []
            async for ev in run_stream("instruction", "hello"):
                events.append(ev)

        assert len(events) == 2
        assert events[0].type == "text_delta"
        assert events[0].content == "Streamed!"
        assert events[1].type == "done"

    @pytest.mark.asyncio
    async def test_tool_call_stream(self):
        llm_tool_response = {
            "choices": [{"message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "tc1",
                    "function": {"name": "calc", "arguments": '{"x": 1}'},
                }],
            }}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        llm_text_response = {
            "choices": [{"message": {"content": "Done", "role": "assistant"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "42"
        mock_result.content = [mock_block]
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with patch("crucible_agent.agent.adapter._connect_servers", new_callable=AsyncMock) as mock_connect, \
             patch("crucible_agent.agent.adapter._call_llm", new_callable=AsyncMock) as mock_llm:
            mock_connect.return_value = ({"calc": mock_session}, [])
            mock_llm.side_effect = [llm_tool_response, llm_text_response]

            events = []
            async for ev in run_stream("instruction", "hello"):
                events.append(ev)

        types = [e.type for e in events]
        assert "tool_start" in types
        assert "tool_end" in types
        assert "text_delta" in types
        assert "done" in types

    @pytest.mark.asyncio
    async def test_error_event_on_exception(self):
        with patch("crucible_agent.agent.adapter._connect_servers", new_callable=AsyncMock) as mock_connect, \
             patch("crucible_agent.agent.adapter._call_llm", new_callable=AsyncMock) as mock_llm:
            mock_connect.return_value = ({}, [])
            mock_llm.side_effect = RuntimeError("LLM down")

            events = []
            async for ev in run_stream("instruction", "hello"):
                events.append(ev)

        assert events[-1].type == "error"
        assert "LLM down" in events[-1].content

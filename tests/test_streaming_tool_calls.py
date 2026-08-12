from __future__ import annotations

from types import SimpleNamespace

import pytest

from model_router import ModelRouter


def _chunk(*, content=None, tool_calls=None, finish_reason=None, usage=None):
    return SimpleNamespace(
        model="mobile-stream-model",
        usage=usage,
        choices=[SimpleNamespace(
            delta=SimpleNamespace(
                content=content,
                reasoning_content=None,
                tool_calls=tool_calls or [],
            ),
            finish_reason=finish_reason,
        )],
    )


def _tool_delta(index, *, call_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


@pytest.mark.asyncio
async def test_stream_response_reconstructs_tool_calls_without_dropping_text():
    chunks = [
        _chunk(tool_calls=[_tool_delta(0, call_id="call_1", name="cal", arguments='{"x":')]),
        _chunk(
            content="正在计算",
            tool_calls=[_tool_delta(0, name="culator", arguments="1}")],
        ),
        _chunk(finish_reason="tool_calls", usage=SimpleNamespace(total_tokens=12)),
    ]

    class FakeRouter:
        async def chat_stream(self, *args, **kwargs):
            assert kwargs["raw_chunks"] is True
            for chunk in chunks:
                yield chunk

    deltas = []
    response = await ModelRouter.chat_stream_response(
        FakeRouter(),
        [{"role": "user", "content": "算一下"}],
        tools=[{"type": "function"}],
        delta_callback=deltas.append,
    )

    assert deltas == ["正在计算"]
    assert response.choices[0].message.content == "正在计算"
    assert response.choices[0].finish_reason == "tool_calls"
    tool_call = response.choices[0].message.tool_calls[0]
    assert tool_call.id == "call_1"
    assert tool_call.function.name == "calculator"
    assert tool_call.function.arguments == '{"x":1}'
    assert response.usage.total_tokens == 12


@pytest.mark.asyncio
async def test_message_processor_pushes_accumulated_deltas_while_returning_response():
    from agent_core.message_processor import MessageProcessorMixin

    expected = SimpleNamespace(choices=[])

    class FakeRouter:
        async def chat_stream_response(self, messages, **kwargs):
            await kwargs["delta_callback"]("手机")
            await kwargs["delta_callback"]("本地")
            return expected

    processor = SimpleNamespace(router=FakeRouter())
    events = []

    result = await MessageProcessorMixin._stream_llm_response_with_tools(
        processor,
        [{"role": "user", "content": "测试"}],
        status_callback=events.append,
        tools=[{"type": "function"}],
    )

    assert result is expected
    assert events == [
        {"type": "stream_text", "delta": "手机", "accumulated": "手机"},
        {"type": "stream_text", "delta": "本地", "accumulated": "手机本地"},
    ]

"""Contract tests for the basic-chat LangGraph conversion."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

import basic_chat.nodes as nodes
from basic_chat.graph import graph
from basic_chat.models import OpenAIModelConfig, build_openai_model
from basic_chat.state import BasicChatState


class _FakeModel:
    """Fake model returning a fixed assistant reply."""

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        """Return a fixed assistant reply for the given messages."""
        return AIMessage(content="hello back")


@pytest.mark.contract
def test_graph_compiles_with_expected_structure() -> None:
    """The compiled graph exposes the three expected nodes in order."""
    node_names = set(graph.get_graph().nodes.keys())
    assert {"ChatInput-in", "OpenAIModel-model", "ChatOutput-out"} <= node_names


@pytest.mark.contract
def test_accepts_chat_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invoking the graph with one user text message yields one reply."""
    monkeypatch.setattr(nodes, "build_openai_model", lambda _config: _FakeModel())
    result = graph.invoke({"messages": [HumanMessage(content="hi")]})
    messages = result["messages"]
    assert len(messages) == 2
    assert messages[0].content == "hi"
    assert messages[0].type == "human"
    assert messages[1].content == "hello back"
    assert messages[1].type == "ai"
    assert result["output"].content == "hello back"


@pytest.mark.contract
def test_constructs_compatible_model() -> None:
    """The factory builds a ChatOpenAI with normalized configuration."""
    model = build_openai_model(
        OpenAIModelConfig(
            model="test-model",
            base_url="https://api.example.com/v1",
            temperature=0.5,
            max_tokens=128,
            stream=True,
        )
    )
    assert model.model_name == "test-model"
    assert model.temperature == 0.5
    assert model.max_tokens == 128
    assert model.streaming is True
    assert "api.example.com" in str(model.openai_api_base)


@pytest.mark.contract
def test_zero_max_tokens_delegates_to_provider() -> None:
    """A zero max_tokens value is passed through as None."""
    model = build_openai_model(OpenAIModelConfig(model="test-model", max_tokens=0))
    assert model.max_tokens is None


@pytest.mark.contract
def test_state_channels_use_add_messages() -> None:
    """The messages channel is declared with the add_messages reducer."""
    assert "messages" in BasicChatState.__annotations__
    assert isinstance(BasicChatState, type)

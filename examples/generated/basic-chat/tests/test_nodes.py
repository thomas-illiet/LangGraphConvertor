"""Unit tests for the basic-chat node adapters."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from basic_chat import nodes
from basic_chat.nodes import chat_input_node, chat_output_node


def _state(messages: list[BaseMessage]) -> dict[str, Any]:
    """Build a minimal state dict for node tests."""
    return {"messages": messages}


class TestChatInputNode:
    """Tests for the chat_input_node input adapter."""

    def test_passes_through_existing_human_message(self) -> None:
        """An existing human message is left in place for the model node."""
        human = HumanMessage(content="hello")
        result = chat_input_node(_state([human]))
        assert result == {}

    def test_appends_placeholder_when_messages_empty(self) -> None:
        """An empty state gets a placeholder HumanMessage appended."""
        result = chat_input_node(_state([]))
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], HumanMessage)

    def test_appends_placeholder_when_last_message_is_not_human(self) -> None:
        """A non-human trailing message triggers a placeholder append."""
        result = chat_input_node(_state([AIMessage(content="hi")]))
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], HumanMessage)


class TestChatOutputNode:
    """Tests for the chat_output_node output adapter."""

    def test_returns_last_message(self) -> None:
        """The output adapter exposes the last message with its content."""
        human = HumanMessage(content="hello")
        ai = AIMessage(content="hi there")
        result = chat_output_node(_state([human, ai]))
        assert result["output"] is ai

    def test_rejects_missing_upstream_message(self) -> None:
        """Missing upstream output raises instead of inventing content."""
        with pytest.raises(ValueError, match="no upstream message"):
            chat_output_node(_state([]))


class TestOpenAIModelNode:
    """Tests for the openai_model_node model invocation."""

    def test_invokes_model_and_appends_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The node calls the model with state messages and appends the reply."""
        captured: dict[str, Any] = {}

        class _FakeModel:
            """Fake model that records its invocation arguments."""

            def invoke(self, messages: list[BaseMessage]) -> AIMessage:
                captured["messages"] = messages
                return AIMessage(content="ok")

        def _fake_build(config: Any) -> _FakeModel:
            captured["config"] = config
            return _FakeModel()

        monkeypatch.setattr(nodes, "build_openai_model", _fake_build)
        human = HumanMessage(content="hello")
        result = nodes.openai_model_node(_state([human]))
        assert captured["config"].model == "test-model"
        assert captured["messages"] == [human]
        assert result["messages"][0].content == "ok"

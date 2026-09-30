"""Node adapters for the basic-chat conversion."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from basic_chat.models import OpenAIModelConfig, build_openai_model
from basic_chat.state import BasicChatState

__all__ = ["chat_input_node", "chat_output_node", "openai_model_node"]


def chat_input_node(state: BasicChatState) -> dict[str, Any]:
    """Normalize the public chat input into a HumanMessage.

    When the graph is invoked with an existing ``messages`` channel the latest
    human message is treated as the input and left in place. When invoked
    without messages, an empty HumanMessage placeholder is appended so the
    downstream model node always has a value to consume.
    """
    messages = state.get("messages", []) if isinstance(state, dict) else state.messages
    if messages and isinstance(messages[-1], HumanMessage):
        return {}
    return {"messages": [HumanMessage(content="")]}


def openai_model_node(state: BasicChatState) -> dict[str, Any]:
    """Invoke the configured OpenAI-compatible model over the messages channel."""
    model = build_openai_model(
        OpenAIModelConfig(
            model="test-model",
            temperature=0.0,
            max_tokens=0,
            stream=True,
        )
    )
    messages = state.get("messages", []) if isinstance(state, dict) else state.messages
    response = model.invoke(messages)
    return {"messages": [response]}


def chat_output_node(state: BasicChatState) -> dict[str, Any]:
    """Expose the final assistant message through the graph output.

    Rejects missing upstream output instead of inventing content.
    """
    messages = state.get("messages", []) if isinstance(state, dict) else state.messages
    if not messages:
        raise ValueError("ChatOutput received no upstream message")
    return {"output": messages[-1]}

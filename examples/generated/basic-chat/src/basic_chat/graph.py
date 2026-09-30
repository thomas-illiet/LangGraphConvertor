"""Compiled LangGraph graph for the basic-chat conversion."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from basic_chat.nodes import chat_input_node, chat_output_node, openai_model_node
from basic_chat.state import BasicChatState

__all__ = ["graph"]

_builder = StateGraph(BasicChatState)
_builder.add_node("ChatInput-in", chat_input_node)
_builder.add_node("OpenAIModel-model", openai_model_node)
_builder.add_node("ChatOutput-out", chat_output_node)
_builder.add_edge(START, "ChatInput-in")
_builder.add_edge("ChatInput-in", "OpenAIModel-model")
_builder.add_edge("OpenAIModel-model", "ChatOutput-out")
_builder.add_edge("ChatOutput-out", END)

graph: CompiledStateGraph = _builder.compile()

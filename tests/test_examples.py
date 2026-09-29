"""Validate the reference Langflow 1.12.x chat and RAG exports."""

from __future__ import annotations

from pathlib import Path

from langflow_converter_mcp.parser import parse_export, validate_dsl_semantics
from langflow_converter_mcp.planner import build_plan

_ROOT = Path(__file__).parents[1]


def test_reference_chat_flow_is_generation_ready() -> None:
    """The chat fixture covers direct model invocation without hidden knowledge."""
    dsl, diagnostics = parse_export((_ROOT / "examples/basic-chat.json").read_text())
    plan, plan_diagnostics = build_plan(dsl)

    assert diagnostics + validate_dsl_semantics(dsl) + plan_diagnostics == []
    assert {item.type for item in plan.definitions} == {
        "ChatInput",
        "OpenAIModel",
        "ChatOutput",
    }
    assert "OpenAIModel-model" in plan.nodes
    assert {"langchain-openai", "langchain-core"} <= set(plan.dependencies)


def test_reference_rag_flow_is_generation_ready() -> None:
    """The RAG fixture covers loading, splitting, embeddings, Chroma, and retrieval."""
    dsl, diagnostics = parse_export((_ROOT / "examples/local-rag.json").read_text())
    plan, plan_diagnostics = build_plan(dsl)

    assert diagnostics + validate_dsl_semantics(dsl) + plan_diagnostics == []
    assert dsl.capabilities.rag
    assert {item.type for item in plan.definitions} == {
        "FileLoader",
        "TextSplitter",
        "OpenAIEmbeddings",
        "Chroma",
        "TextInput",
        "Retriever",
        "TypeConvert",
        "JSONOutput",
    }
    assert {"langchain-chroma", "langchain-openai", "pypdf"} <= set(plan.dependencies)

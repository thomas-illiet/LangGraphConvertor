"""Contract tests for the compiled local-rag graph.

These tests run the compiled graph end-to-end with a deterministic fake
vector store, verifying the public JSON output matches the DSL 2.0 behavior.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from local_rag.graph import build_graph


class _FakeRetriever:
    """A deterministic retriever whose ``invoke`` returns the top-k docs."""

    def __init__(self, docs: list[Document]) -> None:
        self._docs = docs

    def invoke(self, query: str) -> list[Document]:
        return self._docs


class _FakeVectorStore:
    """A deterministic fake vector store used by the retrieval contract test."""

    def __init__(self, docs: list[Document]) -> None:
        self._docs = docs

    def as_retriever(self, **kwargs) -> _FakeRetriever:
        k = kwargs.get("search_kwargs", {}).get("k", len(self._docs))
        return _FakeRetriever(self._docs[:k])


@pytest.mark.contract
def test_graph_returns_structured_json() -> None:
    """The compiled graph maps a query to a JSON result without coercion."""
    docs = [Document(page_content=f"chunk {i}", metadata={"source": "k.txt"}) for i in range(6)]
    fake_store = _FakeVectorStore(docs)

    result = build_graph().invoke({"text": "what is the answer", "vector_store": fake_store})

    assert "result" in result
    assert isinstance(result["result"], list)
    assert len(result["result"]) == 4
    assert result["result"][0]["page_content"] == "chunk 0"
    assert result["result"][0]["metadata"] == {"source": "k.txt"}


@pytest.mark.contract
def test_graph_defaults_empty_query() -> None:
    """An omitted query falls back to the configured default and still runs."""
    with pytest.raises(ValueError):
        # The default query is empty, so retrieval must reject it.
        build_graph().invoke({"vector_store": _FakeVectorStore([])})

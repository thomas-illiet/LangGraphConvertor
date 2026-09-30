"""Unit tests for the retrieval node."""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from local_rag import retriever


class _FakeRetriever:
    """A deterministic retriever whose ``invoke`` returns the top-k docs."""

    def __init__(self, docs: list[Document]) -> None:
        self._docs = docs

    def invoke(self, query: str) -> list[Document]:
        return self._docs


class _FakeVectorStore:
    """A deterministic stand-in for a vector store with ``as_retriever``."""

    def __init__(self, docs: list[Document]) -> None:
        self._docs = docs

    def as_retriever(self, **kwargs) -> _FakeRetriever:
        k = kwargs.get("search_kwargs", {}).get("k", len(self._docs))
        return _FakeRetriever(self._docs[:k])


def test_retrieves_top_k() -> None:
    """At most k ordered documents are returned with unchanged metadata."""
    docs = [Document(page_content=f"d{i}", metadata={"i": i}) for i in range(10)]
    result = retriever.search(_FakeVectorStore(docs), "q", k=4)
    assert len(result) == 4
    assert [d.metadata["i"] for d in result] == [0, 1, 2, 3]


def test_rejects_empty_query() -> None:
    """An empty query raises a typed error."""
    with pytest.raises(ValueError):
        retriever.search(_FakeVectorStore([]), "")

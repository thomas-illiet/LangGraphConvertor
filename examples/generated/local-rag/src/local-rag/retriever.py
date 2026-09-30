"""Semantic retrieval node for the local-rag flow."""

from __future__ import annotations

from typing import Any

from local_rag import config
from local_rag.state import state_get


def query_text(state: Any) -> str:
    """Return the normalized query text from state."""
    text = state_get(state, "text")
    if text is None:
        text = config.DEFAULT_QUERY
    if not isinstance(text, str):
        raise TypeError("query must be a string")
    return text


def search(
    vector_store: Any,
    query: str,
    k: int | None = None,
    search_type: str | None = None,
) -> list[Any]:
    """Retrieve the most relevant documents for ``query``.

    Returns at most ``k`` ordered documents with unchanged metadata. The
    vector store is asked to build its own retriever so the underlying
    provider's field names and options are respected.
    """
    if not query:
        raise ValueError("query must not be empty")
    k = k if k is not None else config.RETRIEVER_K
    search_type = search_type or config.RETRIEVER_SEARCH_TYPE
    retriever = vector_store.as_retriever(search_type=search_type, search_kwargs={"k": k})
    return retriever.invoke(query)


def retriever_node(state: Any) -> dict[str, Any]:
    """LangGraph node that retrieves documents for the input query."""
    vector_store = state_get(state, "vector_store")
    if vector_store is None:
        raise ValueError("vector_store must be provided before retrieval")
    return {"retrieved_documents": search(vector_store, query_text(state))}

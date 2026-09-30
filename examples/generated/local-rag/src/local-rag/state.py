"""Typed state channels for the local-rag LangGraph conversion."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RAGState(BaseModel):
    """State channels shared by the local-rag graph nodes.

    The channels mirror the DSL 2.0 ``state`` entries so producers and
    consumers read and write the same named values.
    """

    # TextInput-query.text (persisted public input)
    text: str | None = None

    # FileLoader-docs.documents
    documents: list[Any] | None = None

    # TextSplitter-chunks.documents
    chunks: list[Any] | None = None

    # OpenAIEmbeddings-embeddings.embeddings (resource, not serializable)
    embeddings: Any | None = None

    # Chroma-store.vector_store (resource, not serializable)
    vector_store: Any | None = None

    # Retriever-search.documents
    retrieved_documents: list[Any] | None = None

    # TypeConvert-json.converted
    conversion_output: Any | None = None

    # JSONOutput-out.json (structured public output)
    result: Any | None = None


def state_get(state: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a state that may be a dict or a :class:`RAGState`."""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)

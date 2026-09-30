"""Chroma vector store factory for the local-rag flow."""

from __future__ import annotations

from typing import Any

from langchain_chroma import Chroma

from local_rag import config
from local_rag.embeddings import make_embeddings


def make_vector_store(
    embeddings: Any | None = None,
) -> Chroma:
    """Build a persisted Chroma vector store.

    The persistence directory is confined beneath the project data root.
    Ingestion of documents happens explicitly in the ingestion step, never
    inside graph invocation, so documents are not duplicated on re-runs.
    """
    if embeddings is None:
        embeddings = make_embeddings()
    persist_directory = config.resolve_workspace_path(config.CHROMA_PERSIST_DIRECTORY)
    persist_directory.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=config.CHROMA_COLLECTION,
        embedding_function=embeddings,
        persist_directory=str(persist_directory),
    )


def ingest(store: Chroma, documents: list[Any]) -> None:
    """Add ``documents`` to ``store`` exactly once during explicit ingestion."""
    if documents:
        store.add_documents(documents)

"""Document splitting node for the local-rag flow."""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from local_rag import config
from local_rag.state import state_get


def make_splitter() -> RecursiveCharacterTextSplitter:
    """Build the recursive text splitter with validated chunk settings."""
    if config.CHUNK_OVERLAP >= config.CHUNK_SIZE:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    return RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )


def split_documents(documents: list[Document]) -> list[Document]:
    """Split documents into overlapping chunks, preserving source metadata."""
    splitter = make_splitter()
    chunks: list[Document] = []
    for document in documents:
        parts = splitter.split_text(document.page_content)
        for index, part in enumerate(parts):
            metadata = dict(document.metadata)
            metadata["chunk_index"] = index
            chunks.append(Document(page_content=part, metadata=metadata))
    return chunks


def splitter_node(state: Any) -> dict[str, Any]:
    """LangGraph node that splits loaded documents into chunks."""
    documents = state_get(state, "documents") or []
    return {"chunks": split_documents(documents)}

"""Unit tests for the document splitting node."""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from local_rag import config
from local_rag import splitter as splitter_module


def test_splits_with_overlap() -> None:
    """A long document splits into ordered, bounded, overlapping chunks."""
    document = Document(page_content="word " * 200, metadata={"source": "doc.txt"})
    chunks = splitter_module.split_documents([document])
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.page_content) <= config.CHUNK_SIZE
        assert chunk.metadata.get("source") == "doc.txt"
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_rejects_overlap_gte_size(monkeypatch) -> None:
    """chunk_overlap greater than or equal to chunk_size is rejected."""
    monkeypatch.setattr(config, "CHUNK_SIZE", 10)
    monkeypatch.setattr(config, "CHUNK_OVERLAP", 10)
    with pytest.raises(ValueError):
        splitter_module.make_splitter()

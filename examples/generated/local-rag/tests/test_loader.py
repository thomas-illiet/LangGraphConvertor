"""Unit tests for the document loading node."""

from __future__ import annotations

import pytest

from local_rag import config, loader


def test_loads_text() -> None:
    """Loading the declared knowledge file produces a document with metadata."""
    # Ensure the declared fixture exists in the data root.
    target = config.data_root() / "knowledge.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text("hello world\n", encoding="utf-8")
    loaded = loader.load_documents()
    assert len(loaded) >= 1
    assert loaded[0].page_content
    assert "source" in loaded[0].metadata


def test_rejects_path_escape() -> None:
    """A parent traversal path is rejected before the file is read."""
    with pytest.raises(ValueError):
        config.resolve_workspace_path("../../etc/passwd")

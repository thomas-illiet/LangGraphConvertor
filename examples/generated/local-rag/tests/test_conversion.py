"""Unit tests for the deterministic type conversion node."""

from __future__ import annotations

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage

from local_rag import conversion


def test_converts_message_to_text() -> None:
    """A message with string content converts to its exact text."""
    message = AIMessage(content="hello")
    assert conversion.convert(message, "text") == "hello"


def test_converts_documents_to_json() -> None:
    """Documents convert to a JSON list preserving content and metadata."""
    doc = Document(page_content="abc", metadata={"source": "x.txt"})
    result = conversion.convert([doc], "json")
    assert result == [{"page_content": "abc", "metadata": {"source": "x.txt"}}]


def test_rejects_unsupported_pair() -> None:
    """An unsupported source and target pair raises a typed error."""
    with pytest.raises(conversion.ConversionError):
        conversion.convert(object(), "json")

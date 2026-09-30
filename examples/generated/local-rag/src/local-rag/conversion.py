"""Deterministic type conversion node for the local-rag flow."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage

from local_rag.state import state_get

_JSON = "json"


class ConversionError(ValueError):
    """Raised when a source and target type pair is unsupported."""


def _to_json(value: Any) -> Any:
    """Convert a supported value into a JSON-compatible representation."""
    if isinstance(value, list):
        return [_to_json(item) for item in value]
    if isinstance(value, BaseMessage):
        return {"role": value.type, "content": value.content}
    if isinstance(value, Document):
        return {"page_content": value.page_content, "metadata": value.metadata}
    if isinstance(value, (dict, str, int, float, bool)) or value is None:
        return value
    if isinstance(value, tuple):
        return list(value)
    raise ConversionError(f"Cannot convert {type(value).__name__} to json")


def convert(value: Any, target_type: str) -> Any:
    """Convert ``value`` into the representation named by ``target_type``.

    Only explicit, deterministic conversions are performed. Unsupported
    source and target pairs raise a typed error instead of implicitly
    coercing to a string.
    """
    if target_type == _JSON:
        # Round-trip through the JSON codec to reject non-serializable data.
        return json.loads(json.dumps(_to_json(value)))
    if target_type == "text":
        if isinstance(value, BaseMessage):
            content = value.content
            if not isinstance(content, str):
                raise ConversionError("message content is not text")
            return content
        if isinstance(value, (str, int, float, bool)) or value is None:
            return str(value)
        raise ConversionError(f"Cannot convert {type(value).__name__} to text")
    raise ConversionError(f"Unsupported target type: {target_type}")


def convert_node(state: Any) -> dict[str, Any]:
    """LangGraph node that converts retrieved documents to JSON."""
    documents = state_get(state, "retrieved_documents")
    if documents is None:
        documents = []
    value = convert(list(documents), _JSON)
    return {"conversion_output": value}

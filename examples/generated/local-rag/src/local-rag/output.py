"""Structured output node for the local-rag flow."""

from __future__ import annotations

import json
from typing import Any

from local_rag.state import state_get


class OutputError(ValueError):
    """Raised when a value cannot be serialized as JSON."""


def _serialize(value: Any) -> Any:
    """Ensure ``value`` is JSON-compatible and return it unchanged."""
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise OutputError("result is not JSON-serializable") from exc
    return value


def output_node(state: Any) -> dict[str, Any]:
    """LangGraph node that publishes the structured result to state.

    The connected value is returned without lossy string conversion, so key
    names and scalar types are preserved for the public output.
    """
    value = state_get(state, "conversion_output")
    if value is None:
        value = []
    return {"result": _serialize(value)}

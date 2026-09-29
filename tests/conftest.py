"""Shared pytest fixtures for converter and MCP integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def supported_flow() -> dict[str, Any]:
    """Return a minimal supported chat input-to-output Langflow export."""
    return {
        "id": "flow-1",
        "name": "Test flow",
        "data": {
            "nodes": [
                {
                    "id": "ChatInput-a",
                    "data": {
                        "type": "ChatInput",
                        "node": {
                            "lf_version": "1.12.0",
                            "template": {},
                            "outputs": [{"name": "message", "types": ["Message"]}],
                        },
                    },
                },
                {
                    "id": "ChatOutput-b",
                    "data": {
                        "type": "ChatOutput",
                        "node": {
                            "lf_version": "1.12.0",
                            "template": {
                                "input_value": {
                                    "value": "",
                                    "input_types": ["Message"],
                                    "required": True,
                                }
                            },
                            "outputs": [{"name": "message", "types": ["Message"]}],
                        },
                    },
                },
            ],
            "edges": [
                {
                    "source": "ChatInput-a",
                    "target": "ChatOutput-b",
                    "data": {
                        "sourceHandle": {"name": "message", "output_types": ["Message"]},
                        "targetHandle": {
                            "fieldName": "input_value",
                            "inputTypes": ["Message"],
                        },
                    },
                }
            ],
        },
    }


@pytest.fixture
def flow_file(tmp_path: Path, supported_flow: dict[str, Any]) -> Path:
    """Persist the supported flow fixture inside an isolated workspace."""
    path = tmp_path / "flow.json"
    path.write_text(json.dumps(supported_flow), encoding="utf-8")
    return path

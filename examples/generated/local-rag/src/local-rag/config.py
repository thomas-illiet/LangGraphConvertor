"""Configuration and workspace-relative path confinement for local-rag."""

from __future__ import annotations

import os
from pathlib import Path

# Root directory that contains the generated package and the data directory.
# config.py lives at <project>/src/<package>/config.py, so the project root is
# two levels above this file's parent (the package directory).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATA_ROOT = _PROJECT_ROOT / "data"

# Component configuration captured from the DSL 2.0, never from source_config.
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "text-embedding-model"
CHROMA_COLLECTION = "reference"
CHROMA_PERSIST_DIRECTORY = Path(".chroma")
RETRIEVER_K = 4
RETRIEVER_SEARCH_TYPE = "similarity"
KNOWLEDGE_PATH = Path("data/knowledge.txt")
DEFAULT_QUERY = ""


def data_root() -> Path:
    """Return the absolute data root for the generated project."""
    return _DATA_ROOT


def resolve_workspace_path(raw: str | Path) -> Path:
    """Resolve ``raw`` to an absolute path and confine it beneath the data root.

    A path that already lies under the data root is used as-is. A bare
    relative path is anchored at the data root. Anything that escapes the
    data root is rejected.

    Raises
    ------
    ValueError
        If the resolved path escapes the data root boundary.

    """
    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        anchored = _DATA_ROOT / candidate
        # If the relative path already contains the data root, anchor at the
        # project root so the path is not doubled.
        if "data" in candidate.parts:
            anchored = _PROJECT_ROOT / candidate
        resolved = anchored.resolve()
    root = _DATA_ROOT.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"Path escapes the data root: {raw}")
    return resolved


def openai_api_key() -> str | None:
    """Return the OpenAI API key from the environment, if present."""
    return os.environ.get("OPENAI_API_KEY") or None

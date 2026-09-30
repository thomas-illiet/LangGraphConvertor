"""Document loading node for the local-rag flow."""

from __future__ import annotations

from typing import Any

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document

from local_rag import config


def load_documents() -> list[Document]:
    """Load the declared knowledge file as LangChain documents.

    The loader is selected from the validated file extension. The path is
    confined to the project data root and remote files are never fetched.
    """
    path = config.resolve_workspace_path(config.KNOWLEDGE_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Knowledge file not found: {path}")
    if path.suffix.lower() == ".pdf":
        loader: Any = PyPDFLoader(str(path))
    elif path.suffix.lower() in {".txt", ".md", ".text"}:
        loader = TextLoader(str(path), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported knowledge file type: {path.suffix}")
    return loader.load()


def loader_node(state: Any) -> dict[str, Any]:
    """LangGraph node that writes loaded documents to state."""
    return {"documents": load_documents()}

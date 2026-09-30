"""Compiled LangGraph for the local-rag conversion.

The graph wires the resolved nodes according to the DSL 2.0 connections:

    FileLoader-docs  -> TextSplitter-chunks -> (Chroma ingestion)
    OpenAIEmbeddings -> Chroma-store
    TextInput-query  -> Retriever-search     -> TypeConvert-json
    Chroma-store     -> Retriever-search
    TypeConvert-json -> JSONOutput-out

Ingestion of documents into the vector store is an explicit, one-time step
(:func:`ingest`) so it is never duplicated during graph invocation. The
compiled ``graph`` exposes the retrieval path from the query to the JSON
result.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from local_rag import config
from local_rag.conversion import convert_node
from local_rag.loader import loader_node
from local_rag.output import output_node
from local_rag.retriever import retriever_node
from local_rag.splitter import splitter_node
from local_rag.state import RAGState, state_get
from local_rag.vector_store import ingest, make_vector_store


def _vector_store_node(state: Any) -> dict[str, Any]:
    """Build the vector store resource and make it available to retrieval."""
    return {"vector_store": make_vector_store(state_get(state, "embeddings"))}


def _ingestion_node(state: Any) -> dict[str, Any]:
    """Ingest split chunks into the vector store exactly once."""
    vector_store = state_get(state, "vector_store")
    if vector_store is not None:
        ingest(vector_store, state_get(state, "chunks") or [])
    return {}


def _prepare(state: Any) -> dict[str, Any]:
    """Materialize input and resource nodes for the retrieval path."""
    prepared: dict[str, Any] = {}
    if state_get(state, "text") is None:
        prepared["text"] = config.DEFAULT_QUERY
    if state_get(state, "vector_store") is None:
        prepared["vector_store"] = make_vector_store(state_get(state, "embeddings"))
    return prepared


def build_graph():
    """Build and compile the retrieval graph from query to JSON result."""
    builder: StateGraph = StateGraph(RAGState)
    builder.add_node("prepare", _prepare)
    builder.add_node("retrieve", retriever_node)
    builder.add_node("convert", convert_node)
    builder.add_node("output", output_node)

    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "retrieve")
    builder.add_edge("retrieve", "convert")
    builder.add_edge("convert", "output")
    builder.add_edge("output", END)
    return builder.compile()


def build_ingestion_graph():
    """Build and compile the one-time ingestion graph."""
    builder: StateGraph = StateGraph(RAGState)
    builder.add_node("load", loader_node)
    builder.add_node("split", splitter_node)
    builder.add_node("vector_store", _vector_store_node)
    builder.add_node("ingest", _ingestion_node)

    builder.add_edge(START, "load")
    builder.add_edge("load", "split")
    builder.add_edge("load", "vector_store")
    builder.add_edge("vector_store", "ingest")
    builder.add_edge("split", "ingest")
    builder.add_edge("ingest", END)
    return builder.compile()


graph = build_graph()

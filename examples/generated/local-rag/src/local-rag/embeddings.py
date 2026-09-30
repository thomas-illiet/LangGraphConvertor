"""OpenAI-compatible embeddings factory for the local-rag flow."""

from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from local_rag import config


def make_embeddings() -> OpenAIEmbeddings:
    """Instantiate the OpenAI embeddings resource.

    The model identifier and the optional API base URL come from the DSL
    config. Credentials are read from the environment and are never written
    into logs or state.
    """
    return OpenAIEmbeddings(
        model=config.EMBEDDING_MODEL,
        openai_api_key=config.openai_api_key(),
    )

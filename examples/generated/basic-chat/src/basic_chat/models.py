"""Factory for the OpenAIModel component resource."""

from __future__ import annotations

import os
from dataclasses import dataclass

from langchain_openai import ChatOpenAI

__all__ = ["OpenAIModelConfig", "build_openai_model"]


@dataclass(frozen=True, slots=True)
class OpenAIModelConfig:
    """Normalized configuration for the OpenAIModel component."""

    model: str
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int = 0
    stream: bool = True


def _resolve_api_key() -> str:
    """Resolve the OpenAI API key from the environment without embedding it.

    A placeholder is used when no credential is configured so the factory can
    construct the model for inspection without a real credential.
    """
    return os.environ.get("OPENAI_API_KEY", "") or "missing-openai-api-key"


def build_openai_model(config: OpenAIModelConfig) -> ChatOpenAI:
    """Build a ChatOpenAI instance from normalized configuration.

    The API key is never embedded in generated code; it is resolved from the
    ``OPENAI_API_KEY`` environment variable at construction time.
    """
    max_tokens = config.max_tokens if config.max_tokens > 0 else None
    return ChatOpenAI(
        model=config.model,
        base_url=config.base_url,
        api_key=_resolve_api_key(),
        temperature=config.temperature,
        max_tokens=max_tokens,
        streaming=config.stream,
    )

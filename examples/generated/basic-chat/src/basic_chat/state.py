"""Typed state channels for the basic-chat conversion."""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict

__all__ = ["BasicChatState"]


class BasicChatState(BaseModel):
    """Shared state for the basic-chat graph.

    The ``messages`` channel uses the ``add_messages`` reducer so each node can
    append messages without replacing conversation history. ``output`` carries
    the final public assistant message to the graph output schema.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    messages: Annotated[list[AnyMessage], add_messages]
    output: AnyMessage | None = None

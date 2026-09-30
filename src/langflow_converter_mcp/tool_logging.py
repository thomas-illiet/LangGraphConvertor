"""Console logging for MCP tool call lifecycle events."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.context import HandlerResult, ServerRequestContext

LOGGER = logging.getLogger("langflow_converter_mcp.tools")


class ToolCallLoggingMiddleware:
    """Log every MCP tool invocation without exposing arguments or results."""

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: Callable[[ServerRequestContext[Any, Any]], Awaitable[HandlerResult]],
    ) -> HandlerResult:
        """Log the start and outcome of one tools/call request."""
        if ctx.method != "tools/call":
            return await call_next(ctx)

        tool_name = self._tool_name(ctx.params)
        call_id = uuid.uuid4().hex[:8]
        started_at = time.perf_counter()
        LOGGER.info("MCP tool call started: tool=%s call_id=%s", tool_name, call_id)
        try:
            result = await call_next(ctx)
        except BaseException as exc:
            duration_ms = (time.perf_counter() - started_at) * 1000
            LOGGER.error(
                "MCP tool call failed: tool=%s call_id=%s duration_ms=%.1f error_type=%s",
                tool_name,
                call_id,
                duration_ms,
                type(exc).__name__,
            )
            raise

        duration_ms = (time.perf_counter() - started_at) * 1000
        LOGGER.info(
            "MCP tool call completed: tool=%s call_id=%s duration_ms=%.1f",
            tool_name,
            call_id,
            duration_ms,
        )
        return result

    @staticmethod
    def _tool_name(params: object) -> str:
        """Extract only the public tool name from unvalidated request parameters."""
        if isinstance(params, dict):
            name = params.get("name")
            if isinstance(name, str) and name:
                return name
        return "<unknown>"

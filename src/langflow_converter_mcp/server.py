"""Compose the Langflow Converter MCP server from tools and resources."""

from __future__ import annotations

from pathlib import Path

from mcp.server import MCPServer

from langflow_converter_mcp.resources import register_resources
from langflow_converter_mcp.security import Workspace
from langflow_converter_mcp.service import ConversionService
from langflow_converter_mcp.tools import register_tools


def create_server(workspace_root: Path) -> MCPServer:
    """Create an MCP server restricted to the supplied workspace root."""
    workspace = Workspace(workspace_root)
    service = ConversionService(workspace)
    server = MCPServer(
        "langflow-converter",
        description="Strict Langflow analysis and LangGraph validation for OpenCode.",
        instructions=(
            "Inspect a Langflow export before writing code. Stop on critical diagnostics. "
            "Build and validate DSL 2.0, consult the graph plan, and load only its pinned "
            "dsl:// component definitions. Generate from recipes, ports, state, invariants, and "
            "tests; never generate from extensions.source_config. Then validate the generated "
            "project. Never weaken checks to obtain acceptance."
        ),
        version="0.1.0",
    )

    register_tools(server, service)
    register_resources(server, service)
    return server

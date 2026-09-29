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
            "Require explicit workspace-relative source and output paths; never search outside "
            "the workspace or on the internet. Inspect the Langflow export before writing code "
            "and stop on critical or major diagnostics. Build and validate DSL 2.0, request the "
            "graph plan, and resolve every definition named by the plan with resolve_component. "
            "Generate only from resolved recipes, ports, state, invariants, and tests; never use "
            "extensions.source_config. Create the uv lockfile, then inspect the project, validate "
            "the graph, run quality and contract checks, and create the final report. Differential "
            "HTTP testing is explicit-only. Never weaken checks to obtain acceptance."
        ),
        version="0.1.0",
    )

    register_tools(server, service)
    register_resources(server, service)
    return server

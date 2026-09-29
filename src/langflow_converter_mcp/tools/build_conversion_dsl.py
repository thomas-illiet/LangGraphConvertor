"""Expose the durable DSL creation MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import ToolResult
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register durable DSL creation on the supplied MCP server."""

    @server.tool(structured_output=True)
    def build_conversion_dsl(conversion_id: str, output_path: str) -> ToolResult:
        """Persist the canonical YAML DSL for a previously inspected conversion."""
        return service.build_conversion_dsl(conversion_id, output_path)

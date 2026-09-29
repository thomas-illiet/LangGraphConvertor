"""Expose the conversion DSL validation MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import ToolResult
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register conversion DSL validation on the supplied MCP server."""

    @server.tool(structured_output=True)
    def validate_conversion_dsl(dsl_path: str) -> ToolResult:
        """Validate and load a workspace-relative conversion DSL."""
        return service.validate_conversion_dsl(dsl_path)

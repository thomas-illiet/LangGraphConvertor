"""Expose the unsupported feature reporting MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import ToolResult
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register unsupported feature reporting on the supplied MCP server."""

    @server.tool(structured_output=True)
    def list_unsupported_features(conversion_id: str) -> ToolResult:
        """List all critical or major blockers discovered for a conversion."""
        return service.list_unsupported_features(conversion_id)

"""Expose the component contract lookup MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import ToolResult
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register component contract lookup on the supplied MCP server."""

    @server.tool(structured_output=True)
    def resolve_component(component_type: str, conversion_id: str | None = None) -> ToolResult:
        """Return a component contract and optionally record it for a conversion."""
        return service.resolve_component(component_type, conversion_id)

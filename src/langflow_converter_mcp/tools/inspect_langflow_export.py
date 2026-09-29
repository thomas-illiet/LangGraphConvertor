"""Expose the Langflow export inspection MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import ToolResult
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register export inspection on the supplied MCP server."""

    @server.tool(structured_output=True)
    def inspect_langflow_export(source_path: str) -> ToolResult:
        """Inspect one workspace-relative Langflow JSON export and start a conversion."""
        return service.inspect_langflow_export(source_path)

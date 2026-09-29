"""Expose the generated project inspection MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import ToolResult
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register generated project inspection on the supplied MCP server."""

    @server.tool(structured_output=True)
    def inspect_generated_project(project_path: str, conversion_id: str) -> ToolResult:
        """Check the required structure of an OpenCode-generated project."""
        return service.inspect_generated_project(project_path, conversion_id)

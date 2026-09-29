"""Expose the LangGraph planning MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import ToolResult
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register LangGraph planning on the supplied MCP server."""

    @server.tool(structured_output=True)
    def plan_langgraph(conversion_id: str) -> ToolResult:
        """Return expected resources, state channels, nodes, and execution layers."""
        return service.plan_langgraph(conversion_id)

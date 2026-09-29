"""Expose the generated LangGraph import validation MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import ToolResult
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register generated graph import validation on the supplied MCP server."""

    @server.tool(structured_output=True)
    async def validate_graph_contract(
        project_path: str, conversion_id: str, timeout_seconds: float = 30
    ) -> ToolResult:
        """Import graphs declared in langgraph.json in an isolated subprocess."""
        return await service.validate_graph_contract(project_path, conversion_id, timeout_seconds)

"""Expose the Langflow-to-LangGraph differential test MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import DifferentialCase, ToolResult
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register differential HTTP testing on the supplied MCP server."""

    @server.tool(structured_output=True)
    async def run_differential_tests(
        conversion_id: str,
        langflow_url: str,
        langgraph_url: str,
        cases: list[DifferentialCase],
        timeout_seconds: float = 30,
    ) -> ToolResult:
        """Compare normalized HTTP results for explicitly allowlisted endpoints."""
        return await service.run_differential_tests(
            conversion_id,
            langflow_url,
            langgraph_url,
            cases,
            timeout_seconds,
        )

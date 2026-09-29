"""Expose the generated project contract test MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import ToolResult
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register generated project contract testing on the supplied MCP server."""

    @server.tool(structured_output=True)
    async def run_contract_tests(
        project_path: str, conversion_id: str, timeout_seconds: float = 120
    ) -> ToolResult:
        """Run tests marked contract in the generated project."""
        return await service.run_contract_tests(project_path, conversion_id, timeout_seconds)

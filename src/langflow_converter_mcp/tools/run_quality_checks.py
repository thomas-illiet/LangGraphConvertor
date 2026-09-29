"""Expose the generated project quality gate MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import ToolResult
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register the deterministic project quality gate on the supplied MCP server."""

    @server.tool(structured_output=True)
    async def run_quality_checks(
        project_path: str, conversion_id: str, timeout_seconds: float = 120
    ) -> ToolResult:
        """Run the fixed Ruff, ty, and pytest quality gate without a shell."""
        return await service.run_quality_checks(project_path, conversion_id, timeout_seconds)

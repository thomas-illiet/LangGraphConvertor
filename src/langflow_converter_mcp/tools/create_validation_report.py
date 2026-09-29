"""Expose the authoritative validation report MCP tool."""

from mcp.server import MCPServer

from langflow_converter_mcp.models import ValidationReport
from langflow_converter_mcp.service import ConversionService


def register(server: MCPServer, service: ConversionService) -> None:
    """Register acceptance report creation on the supplied MCP server."""

    @server.tool(structured_output=True)
    def create_validation_report(conversion_id: str) -> ValidationReport:
        """Create the authoritative acceptance report for a conversion."""
        return service.create_validation_report(conversion_id)

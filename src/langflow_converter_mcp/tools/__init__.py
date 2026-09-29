"""Register every MCP tool while keeping one public tool per module."""

from __future__ import annotations

from collections.abc import Callable

from mcp.server import MCPServer

from langflow_converter_mcp.service import ConversionService
from langflow_converter_mcp.tools.build_conversion_dsl import register as register_build_dsl
from langflow_converter_mcp.tools.create_validation_report import (
    register as register_validation_report,
)
from langflow_converter_mcp.tools.inspect_generated_project import (
    register as register_project_inspection,
)
from langflow_converter_mcp.tools.inspect_langflow_export import (
    register as register_export_inspection,
)
from langflow_converter_mcp.tools.list_unsupported_features import (
    register as register_unsupported_features,
)
from langflow_converter_mcp.tools.plan_langgraph import register as register_graph_plan
from langflow_converter_mcp.tools.resolve_component import register as register_component
from langflow_converter_mcp.tools.run_contract_tests import register as register_contract_tests
from langflow_converter_mcp.tools.run_differential_tests import (
    register as register_differential_tests,
)
from langflow_converter_mcp.tools.run_quality_checks import register as register_quality_checks
from langflow_converter_mcp.tools.validate_conversion_dsl import (
    register as register_dsl_validation,
)
from langflow_converter_mcp.tools.validate_graph_contract import (
    register as register_graph_validation,
)

ToolRegistrar = Callable[[MCPServer, ConversionService], None]

_REGISTRARS: tuple[ToolRegistrar, ...] = (
    register_export_inspection,
    register_build_dsl,
    register_dsl_validation,
    register_component,
    register_graph_plan,
    register_unsupported_features,
    register_project_inspection,
    register_graph_validation,
    register_quality_checks,
    register_contract_tests,
    register_differential_tests,
    register_validation_report,
)


def register_tools(server: MCPServer, service: ConversionService) -> None:
    """Register the complete, stable tool inventory on an MCP server."""
    for register in _REGISTRARS:
        register(server, service)

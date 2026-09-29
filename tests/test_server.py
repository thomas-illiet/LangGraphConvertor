"""Test MCP registration and transport integration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from mcp import Client, StdioServerParameters

from langflow_converter_mcp.server import create_server


@pytest.mark.asyncio
async def test_mcp_inventory(tmp_path: Path) -> None:
    """The server exposes the stable tool and resource inventory."""
    server = create_server(tmp_path)

    tools = {tool.name for tool in await server.list_tools()}
    resources = {str(resource.uri) for resource in await server.list_resources()}
    templates = {template.uri_template for template in await server.list_resource_templates()}

    assert {
        "inspect_langflow_export",
        "build_conversion_dsl",
        "validate_conversion_dsl",
        "resolve_component",
        "plan_langgraph",
        "list_unsupported_features",
        "inspect_generated_project",
        "validate_graph_contract",
        "run_quality_checks",
        "run_contract_tests",
        "run_differential_tests",
        "create_validation_report",
    } <= tools
    assert "dsl://schema/current" in resources
    assert "dsl://components" in resources
    assert "catalog://components" in resources
    assert "dsl://components/{component_type}" in templates
    assert "dsl://components/{component_type}/schema" in templates
    assert "catalog://components/{component_type}" in templates
    assert "conversion://{conversion_id}/report" in templates


@pytest.mark.asyncio
async def test_component_definition_resources_are_readable(tmp_path: Path) -> None:
    """Canonical and legacy resource URIs expose the same validated definition."""
    server = create_server(tmp_path)

    canonical = list(await server.read_resource("dsl://components/OpenAIModel"))
    legacy = list(await server.read_resource("catalog://components/OpenAIModel"))
    schema = list(await server.read_resource("dsl://components/OpenAIModel/schema"))

    canonical_payload = yaml.safe_load(canonical[0].content)
    assert canonical_payload["definition"]["type"] == "OpenAIModel"
    assert '"OpenAIModelConfig"' in schema[0].content
    assert '"OpenAIModel"' in legacy[0].content


def test_http_app_is_local_and_buildable(tmp_path: Path) -> None:
    """The Streamable HTTP application can be constructed for localhost."""
    app = create_server(tmp_path).streamable_http_app(host="127.0.0.1")
    assert app is not None


@pytest.mark.asyncio
async def test_stdio_round_trip(tmp_path: Path, flow_file: Path) -> None:
    """A real stdio MCP client can invoke export inspection end to end."""
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "langflow_converter_mcp.cli",
            "--workspace",
            str(tmp_path),
            "--transport",
            "stdio",
        ],
    )
    async with Client(parameters) as client:
        result = await client.call_tool("inspect_langflow_export", {"source_path": flow_file.name})

    assert not result.is_error
    assert result.structured_content
    assert result.structured_content["status"] == "ok"
    assert result.structured_content["data"]["component_count"] == 2

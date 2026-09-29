"""Register read-only MCP resources and resource templates."""

from __future__ import annotations

from typing import Any

import yaml
from mcp.server import MCPServer

from langflow_converter_mcp.service import ConversionService


def register_resources(server: MCPServer, service: ConversionService) -> None:
    """Expose schemas, catalog entries, plans, DSL documents, and reports."""

    @server.resource("dsl://schema/current", mime_type="application/schema+json")
    def dsl_schema() -> dict[str, Any]:
        """Return the current JSON Schema for the durable conversion DSL."""
        return service.schema_resource()

    @server.resource("dsl://components", mime_type="application/json")
    def component_definitions() -> dict[str, object]:
        """Return the lightweight index of packaged DSL 2.0 definitions."""
        return service.catalog_resource()

    @server.resource("dsl://components/{component_type}", mime_type="application/yaml")
    def component_definition(component_type: str) -> str:
        """Return one complete packaged component definition as YAML."""
        payload = service.component_resource(component_type)
        if payload is None:
            return "error: unsupported_component\n"
        return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)

    @server.resource(
        "dsl://components/{component_type}/schema", mime_type="application/schema+json"
    )
    def component_config_schema(component_type: str) -> dict[str, Any]:
        """Return JSON Schema for one definition's normalized config object."""
        return service.component_schema_resource(component_type) or {
            "error": "unsupported_component"
        }

    @server.resource("catalog://components", mime_type="application/json")
    def component_catalog() -> dict[str, object]:
        """Alias the legacy catalog index to the DSL 2.0 definition index."""
        return service.catalog_resource()

    @server.resource("catalog://components/{component_type}", mime_type="application/json")
    def component_contract(component_type: str) -> dict[str, object]:
        """Alias a legacy catalog contract to the complete DSL 2.0 definition."""
        return service.component_resource(component_type) or {"error": "unsupported_component"}

    @server.resource("conversion://{conversion_id}/dsl", mime_type="application/yaml")
    def conversion_dsl(conversion_id: str) -> str:
        """Return the canonical DSL for an active in-memory conversion."""
        dsl = service.dsl_by_id.get(conversion_id)
        if dsl is None:
            return "error: unknown_conversion\n"
        return yaml.safe_dump(dsl.model_dump(mode="json", exclude_none=True), sort_keys=False)

    @server.resource("conversion://{conversion_id}/plan", mime_type="application/json")
    def conversion_plan(conversion_id: str) -> dict[str, object]:
        """Return the expected LangGraph plan for an active conversion."""
        plan = service.plan_by_id.get(conversion_id)
        return plan.model_dump(mode="json") if plan else {"error": "unknown_conversion"}

    @server.resource("conversion://{conversion_id}/report", mime_type="application/json")
    def conversion_report(conversion_id: str) -> dict[str, object]:
        """Return the latest acceptance report for an active conversion."""
        report = service.reports_by_id.get(conversion_id)
        return report.model_dump(mode="json") if report else {"error": "report_not_created"}

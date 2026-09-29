"""Test transport-independent conversion and validation orchestration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from langflow_converter_mcp.models import Status
from langflow_converter_mcp.security import Workspace
from langflow_converter_mcp.service import ConversionService


def test_conversion_lifecycle(tmp_path: Path, flow_file: Path) -> None:
    """Inspection, DSL persistence, validation, and planning form one session."""
    service = ConversionService(Workspace(tmp_path))

    inspected = service.inspect_langflow_export(flow_file.name)
    assert inspected.status is Status.OK
    assert inspected.conversion_id

    built = service.build_conversion_dsl(inspected.conversion_id, "contract/workflow.yaml")
    assert built.status is Status.OK
    assert (tmp_path / "contract/workflow.yaml").is_file()

    validated = service.validate_conversion_dsl("contract/workflow.yaml")
    assert validated.status is Status.OK
    assert service.plan_langgraph(inspected.conversion_id).status is Status.OK
    assert service.list_unsupported_features(inspected.conversion_id).data == {
        "unsupported_count": 0
    }


def test_resolve_component_returns_complete_pinned_definition(tmp_path: Path) -> None:
    """Component resolution returns the full recipe plus immutable MCP identity."""
    service = ConversionService(Workspace(tmp_path))

    result = service.resolve_component("ChatOpenAI")

    assert result.status is Status.OK
    assert result.data["definition"]["type"] == "OpenAIModel"
    assert result.data["definition"]["recipe"]["mode"] == "hybrid"
    assert len(result.data["sha256"]) == 64
    assert result.data["uri"] == "dsl://components/OpenAIModel"


def test_project_inspection_and_report(tmp_path: Path, flow_file: Path) -> None:
    """Missing generated-project artifacts produce a rejected report."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id
    project = tmp_path / "generated"
    project.mkdir()

    result = service.inspect_generated_project("generated", conversion_id)
    report = service.create_validation_report(conversion_id)

    assert result.status is Status.ERROR
    assert not report.accepted
    assert report.major_count >= 1


def test_rerun_replaces_resolved_project_findings(tmp_path: Path, flow_file: Path) -> None:
    """A repaired project replaces obsolete findings from an earlier cycle."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id
    project = tmp_path / "generated"
    project.mkdir()
    assert service.inspect_generated_project("generated", conversion_id).status is Status.ERROR

    for relative in ("pyproject.toml", "uv.lock", "langgraph.json", ".env.example"):
        (project / relative).write_text("{}", encoding="utf-8")
    (project / "src").mkdir()
    (project / "tests").mkdir()

    assert service.inspect_generated_project("generated", conversion_id).status is Status.OK
    report = service.create_validation_report(conversion_id)
    assert report.major_count == 0


@pytest.mark.asyncio
async def test_graph_contract_import(tmp_path: Path, flow_file: Path) -> None:
    """Graph contract validation imports and recognizes an invocable graph."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id
    project = tmp_path / "generated"
    package = project / "src/app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "class Graph:\n    def invoke(self, value):\n        return value\ngraph = Graph()\n",
        encoding="utf-8",
    )
    (project / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": "app:graph"}}), encoding="utf-8"
    )

    result = await service.validate_graph_contract("generated", conversion_id)

    assert result.status is Status.OK, result.model_dump()

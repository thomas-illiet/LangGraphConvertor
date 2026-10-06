"""Test transport-independent conversion and validation orchestration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from langflow_converter_mcp.models import CheckResult, Status
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
    assert built.data["dsl"]["dsl_version"] == "2.0"
    assert len(built.data["dsl"]["components"]) == 2
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


def test_modified_canonical_dsl_is_rejected(tmp_path: Path, flow_file: Path) -> None:
    """Validation rejects changes to the MCP-produced DSL for an active conversion."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id
    service.build_conversion_dsl(conversion_id, "generated/workflow.yaml")
    workflow = tmp_path / "generated/workflow.yaml"
    payload = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    payload["components"][0]["config"]["sender_name"] = "Tampered"
    workflow.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = service.validate_conversion_dsl("generated/workflow.yaml")

    assert result.status is Status.ERROR
    assert any(item.code == "canonical_dsl_modified" for item in result.diagnostics)


def test_build_conversion_dsl_rejects_a_directory_output_path(
    tmp_path: Path, flow_file: Path
) -> None:
    """DSL persistence requires an explicit YAML filename and creates no ambiguous file."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id

    result = service.build_conversion_dsl(conversion_id, "generated/project")

    assert result.status is Status.ERROR
    assert result.diagnostics[0].code == "invalid_dsl_output_path"
    assert not (tmp_path / "generated/project").exists()


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
    (project / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": "app.graph:graph"}}), encoding="utf-8"
    )
    service.build_conversion_dsl(conversion_id, "generated/workflow.yaml")
    (project / "src").mkdir()
    (project / "tests").mkdir()

    assert service.inspect_generated_project("generated", conversion_id).status is Status.OK
    report = service.create_validation_report(conversion_id)
    assert not any(item.code == "missing_project_file" for item in report.diagnostics)
    assert not report.accepted


def test_project_inspection_rejects_a_tampered_dsl_copy(tmp_path: Path, flow_file: Path) -> None:
    """The project gate compares workflow.yaml with the authoritative conversion DSL."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id
    project = tmp_path / "generated"
    project.mkdir()
    for relative in ("pyproject.toml", "uv.lock", "langgraph.json", ".env.example"):
        (project / relative).write_text("{}", encoding="utf-8")
    service.build_conversion_dsl(conversion_id, "generated/workflow.yaml")
    payload = yaml.safe_load((project / "workflow.yaml").read_text(encoding="utf-8"))
    payload["components"][0]["config"]["sender_name"] = "Tampered"
    (project / "workflow.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )
    (project / "src").mkdir()
    (project / "tests").mkdir()

    result = service.inspect_generated_project("generated", conversion_id)

    assert result.status is Status.ERROR
    assert any(item.code == "generated_dsl_mismatch" for item in result.diagnostics)


def test_project_inspection_rejects_duplicate_source_packages(
    tmp_path: Path, flow_file: Path
) -> None:
    """The project gate rejects the same package at the root and under src/."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id
    project = tmp_path / "generated"
    project.mkdir()
    for relative in ("pyproject.toml", "uv.lock", ".env.example"):
        (project / relative).write_text("{}", encoding="utf-8")
    (project / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": "app.graph:graph"}}), encoding="utf-8"
    )
    service.build_conversion_dsl(conversion_id, "generated/workflow.yaml")
    for package in (project / "src/app", project / "app"):
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
    (project / "tests").mkdir()

    result = service.inspect_generated_project("generated", conversion_id)

    assert result.status is Status.ERROR
    assert any(item.code == "duplicate_source_package" for item in result.diagnostics)


def test_project_inspection_rejects_src_prefixed_graph_modules(
    tmp_path: Path, flow_file: Path
) -> None:
    """The project gate explains the correct import target for a src layout."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id
    project = tmp_path / "generated"
    project.mkdir()
    for relative in ("pyproject.toml", "uv.lock", ".env.example"):
        (project / relative).write_text("{}", encoding="utf-8")
    (project / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": "src.app.graph:graph"}}), encoding="utf-8"
    )
    service.build_conversion_dsl(conversion_id, "generated/workflow.yaml")
    package = project / "src/app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (project / "tests").mkdir()

    result = service.inspect_generated_project("generated", conversion_id)

    assert result.status is Status.ERROR
    assert any(item.code == "invalid_graph_module_path" for item in result.diagnostics)


def test_project_inspection_requires_empty_environment_examples(
    tmp_path: Path, supported_flow: dict[str, Any]
) -> None:
    """Generated projects declare every provider variable without committing values."""
    node = supported_flow["data"]["nodes"][0]
    node["data"]["type"] = "OpenAIModel"
    node["data"]["node"]["template"] = {"model_name": {"value": "test-model"}}
    supported_flow["data"]["edges"] = []
    flow = tmp_path / "provider.json"
    flow.write_text(json.dumps(supported_flow), encoding="utf-8")
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow.name).conversion_id
    assert conversion_id
    project = tmp_path / "generated"
    project.mkdir()
    for relative in ("pyproject.toml", "uv.lock"):
        (project / relative).write_text("{}", encoding="utf-8")
    (project / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": "app.graph:graph"}}), encoding="utf-8"
    )
    service.build_conversion_dsl(conversion_id, "generated/workflow.yaml")
    (project / "src").mkdir()
    (project / "tests").mkdir()

    (project / ".env.example").write_text("OPENAI_API_KEY=committed\n", encoding="utf-8")
    invalid = service.inspect_generated_project("generated", conversion_id)

    assert invalid.status is Status.ERROR
    assert {item.code for item in invalid.diagnostics} == {
        "environment_example_value",
        "missing_environment_example",
    }

    (project / ".env.example").write_text("OPENAI_BASE_URL=\nOPENAI_API_KEY=\n", encoding="utf-8")
    valid = service.inspect_generated_project("generated", conversion_id)

    assert valid.status is Status.OK
    assert valid.diagnostics == []


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
    (project / "pyproject.toml").write_text(
        '[project]\nname = "generated-test"\nversion = "0.1.0"\nrequires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["uv", "lock", "--directory", str(project), "--offline"],
        check=True,
        capture_output=True,
        text=True,
    )

    result = await service.validate_graph_contract("generated", conversion_id)

    assert result.status is Status.OK, result.model_dump()


@pytest.mark.asyncio
async def test_quality_checks_reject_tools_missing_from_project_environment(
    tmp_path: Path, flow_file: Path
) -> None:
    """Project-local quality gates never fall back to executables from the server PATH."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id
    (tmp_path / "generated").mkdir()

    result = await service.run_quality_checks("generated", conversion_id)

    assert result.status is Status.ERROR
    checks = result.data["checks"]
    project_checks = [check for check in checks if check["name"] != "type-check"]
    assert all(check["return_code"] == 127 for check in project_checks)
    assert all(
        "Required project-local tool is missing" in check["output"] for check in project_checks
    )
    type_check = next(check for check in checks if check["name"] == "type-check")
    assert "Required project-local tool is missing" not in type_check["output"]


@pytest.mark.asyncio
async def test_contract_tests_reject_project_without_local_pytest(
    tmp_path: Path, flow_file: Path
) -> None:
    """The contract gate requires pytest from the generated project's own environment."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id
    (tmp_path / "generated").mkdir()

    result = await service.run_contract_tests("generated", conversion_id)

    assert result.status is Status.ERROR
    check = result.data["check"]
    assert check["return_code"] == 127
    assert "Required project-local tool is missing" in check["output"]


def test_validation_report_requires_every_mandatory_stage(tmp_path: Path, flow_file: Path) -> None:
    """Acceptance fails closed until lifecycle stages and checks are all recorded."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id

    incomplete = service.create_validation_report(conversion_id)

    assert not incomplete.accepted
    missing = next(
        item for item in incomplete.diagnostics if item.code == "missing_validation_stage"
    )
    assert "build_conversion_dsl" in (missing.evidence or "")
    assert "project-structure" in (missing.evidence or "")


def test_validation_report_accepts_only_a_complete_successful_run(
    tmp_path: Path, flow_file: Path
) -> None:
    """A complete ordered lifecycle with every successful check can be accepted."""
    service = ConversionService(Workspace(tmp_path))
    conversion_id = service.inspect_langflow_export(flow_file.name).conversion_id
    assert conversion_id
    service.build_conversion_dsl(conversion_id, "generated/workflow.yaml")
    service.validate_conversion_dsl("generated/workflow.yaml")
    service.plan_langgraph(conversion_id)
    for component_type in ("ChatInput", "ChatOutput", "OpenAIModel"):
        service.resolve_component(component_type, conversion_id)
    required_checks = (
        "project-structure",
        "graph-contract",
        "ruff-format",
        "ruff-check",
        "type-check",
        "tests",
        "contract-tests",
    )
    service.checks_by_id[conversion_id] = [
        CheckResult(name=name, status=Status.OK, return_code=0) for name in required_checks
    ]

    report = service.create_validation_report(conversion_id)

    assert report.accepted
    assert report.critical_count == 0
    assert report.major_count == 0

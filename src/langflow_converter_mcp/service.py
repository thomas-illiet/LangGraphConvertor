"""Transport-independent converter and validation service."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import yaml

from langflow_converter_mcp.component_definitions import get_registry
from langflow_converter_mcp.models import (
    CheckResult,
    ConversionDSL,
    Diagnostic,
    DifferentialCase,
    DifferentialOutcome,
    GraphPlan,
    Severity,
    Status,
    ToolResult,
    ValidationReport,
)
from langflow_converter_mcp.parser import (
    FlowParseError,
    parse_export,
    validate_dsl_payload,
    validate_dsl_semantics,
)
from langflow_converter_mcp.planner import build_plan
from langflow_converter_mcp.security import SecurityError, Workspace, validate_endpoint

_MAX_OUTPUT = 64 * 1024
_REQUIRED_PROJECT_FILES = (
    "pyproject.toml",
    "uv.lock",
    "langgraph.json",
    ".env.example",
    "workflow.yaml",
)
_REQUIRED_ACCEPTANCE_CHECKS = frozenset(
    {
        "project-structure",
        "graph-contract",
        "ruff-format",
        "ruff-check",
        "type-check",
        "tests",
        "contract-tests",
    }
)
_IGNORED_RESPONSE_KEYS = {"id", "run_id", "thread_id", "timestamp", "created_at", "updated_at"}


def _unique_diagnostics(items: Sequence[Diagnostic]) -> list[Diagnostic]:
    seen: set[tuple[str, str | None, str | None]] = set()
    result: list[Diagnostic] = []
    for item in items:
        key = (item.code, item.component_id, item.path)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


class ConversionService:
    """Owns conversion sessions while keeping protocol concerns out of the core."""

    def __init__(self, workspace: Workspace) -> None:
        """Initialize isolated in-memory state for one workspace-bound server."""
        self.workspace = workspace
        self.registry = get_registry()
        self.dsl_by_id: dict[str, ConversionDSL] = {}
        self.plan_by_id: dict[str, GraphPlan] = {}
        self.diagnostics_by_id: dict[str, list[Diagnostic]] = {}
        self.checks_by_id: dict[str, list[CheckResult]] = {}
        self.reports_by_id: dict[str, ValidationReport] = {}
        self.built_dsl_paths: dict[str, Path] = {}
        self.validated_dsl_ids: set[str] = set()
        self.planned_conversion_ids: set[str] = set()
        self.resolved_component_types_by_id: dict[str, set[str]] = {}

    @staticmethod
    def _status(diagnostics: Sequence[Diagnostic]) -> Status:
        if any(item.severity in {Severity.CRITICAL, Severity.MAJOR} for item in diagnostics):
            return Status.ERROR
        return Status.WARNING if diagnostics else Status.OK

    @staticmethod
    def _error(exc: Exception, code: str = "operation_failed") -> ToolResult:
        return ToolResult(
            status=Status.ERROR,
            diagnostics=[Diagnostic(code=code, severity=Severity.CRITICAL, message=str(exc))],
        )

    def _replace_diagnostics(
        self, conversion_id: str, codes: set[str], diagnostics: list[Diagnostic]
    ) -> None:
        retained = [
            item for item in self.diagnostics_by_id.get(conversion_id, []) if item.code not in codes
        ]
        self.diagnostics_by_id[conversion_id] = [*retained, *diagnostics]

    def _replace_checks(self, conversion_id: str, checks: list[CheckResult]) -> None:
        names = {check.name for check in checks}
        retained = [
            item for item in self.checks_by_id.get(conversion_id, []) if item.name not in names
        ]
        self.checks_by_id[conversion_id] = [*retained, *checks]

    def inspect_langflow_export(self, source_path: str) -> ToolResult:
        """Parse an export, calculate its plan, and start a conversion session."""
        try:
            dsl, diagnostics = parse_export(self.workspace.read_text(source_path))
        except (SecurityError, FlowParseError) as exc:
            return self._error(exc, "invalid_export")
        conversion_id = dsl.flow.source_sha256[:16]
        diagnostics.extend(validate_dsl_semantics(dsl))
        plan, plan_diagnostics = build_plan(dsl)
        diagnostics.extend(plan_diagnostics)
        diagnostics = _unique_diagnostics(diagnostics)
        self.dsl_by_id[conversion_id] = dsl
        self.plan_by_id[conversion_id] = plan
        self.diagnostics_by_id[conversion_id] = diagnostics
        return ToolResult(
            status=self._status(diagnostics),
            conversion_id=conversion_id,
            diagnostics=diagnostics,
            data={
                "flow": dsl.flow.model_dump(mode="json"),
                "component_count": len(dsl.components),
                "connection_count": len(dsl.connections),
                "capabilities": dsl.capabilities.model_dump(mode="json"),
                "definitions": plan.model_dump(mode="json")["definitions"],
                "unknown_fields": [
                    {
                        "component_id": component.id,
                        "fields": sorted(component.extensions.source_config),
                    }
                    for component in dsl.components
                    if component.extensions.source_config
                ],
                "supported": self._status(diagnostics) is not Status.ERROR,
            },
        )

    def build_conversion_dsl(self, conversion_id: str, output_path: str) -> ToolResult:
        """Persist a session's canonical DSL within the workspace."""
        dsl = self.dsl_by_id.get(conversion_id)
        if dsl is None:
            return self._error(
                ValueError("Unknown conversion_id; inspect the export first"), "unknown_conversion"
            )
        if Path(output_path).suffix.lower() not in {".yaml", ".yml"}:
            return self._error(
                ValueError(
                    "output_path must name a YAML file such as "
                    "generated/<project>/workflow.yaml, not a directory"
                ),
                "invalid_dsl_output_path",
            )
        content = yaml.safe_dump(
            dsl.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True
        )
        try:
            written = self.workspace.write_text(output_path, content)
        except SecurityError as exc:
            return self._error(exc, "unsafe_output_path")
        self.built_dsl_paths[conversion_id] = written
        diagnostics = self.diagnostics_by_id.get(conversion_id, [])
        return ToolResult(
            status=self._status(diagnostics),
            conversion_id=conversion_id,
            diagnostics=diagnostics,
            data={
                "path": str(written.relative_to(self.workspace.root)),
                "sha256": dsl.flow.source_sha256,
                "dsl": dsl.model_dump(mode="json", exclude_none=True),
            },
        )

    def validate_conversion_dsl(self, dsl_path: str) -> ToolResult:
        """Load a YAML DSL and apply schema, semantic, and graph validation."""
        try:
            payload = yaml.safe_load(self.workspace.read_text(dsl_path))
        except (SecurityError, yaml.YAMLError) as exc:
            return self._error(exc, "invalid_dsl")
        dsl, diagnostics = validate_dsl_payload(payload)
        if dsl is None:
            return ToolResult(status=Status.ERROR, diagnostics=diagnostics)
        conversion_id = dsl.flow.source_sha256[:16]
        authoritative = self.dsl_by_id.get(conversion_id)
        if authoritative is not None and dsl != authoritative:
            diagnostics.append(
                Diagnostic(
                    code="canonical_dsl_modified",
                    severity=Severity.CRITICAL,
                    message="The MCP-produced DSL was modified after export inspection.",
                    recommendation="Rebuild the DSL from the original inspected conversion.",
                )
            )
        diagnostics.extend(validate_dsl_semantics(dsl))
        plan, plan_diagnostics = build_plan(dsl)
        diagnostics.extend(plan_diagnostics)
        if authoritative is None:
            self.dsl_by_id[conversion_id] = dsl
            self.plan_by_id[conversion_id] = plan
        self.diagnostics_by_id[conversion_id] = diagnostics
        if self._status(diagnostics) is not Status.ERROR:
            self.validated_dsl_ids.add(conversion_id)
        return ToolResult(
            status=self._status(diagnostics),
            conversion_id=conversion_id,
            diagnostics=diagnostics,
            data={
                "valid": self._status(diagnostics) is not Status.ERROR,
                "plan_available": True,
            },
        )

    def resolve_component(
        self, component_type: str, conversion_id: str | None = None
    ) -> ToolResult:
        """Return the versioned contract for a supported component alias."""
        payload = self.registry.payload(component_type)
        if payload is None:
            return self._error(
                ValueError(f"Unsupported component type: {component_type}"),
                "unsupported_component",
            )
        if conversion_id is not None:
            plan = self.plan_by_id.get(conversion_id)
            if plan is None:
                return self._error(ValueError("Unknown conversion_id"), "unknown_conversion")
            canonical_type = payload["definition"]["type"]
            required_types = {definition.type for definition in plan.definitions}
            if canonical_type not in required_types:
                return self._error(
                    ValueError(
                        f"Component type {canonical_type!r} is not required by this conversion"
                    ),
                    "unexpected_component_resolution",
                )
            self.resolved_component_types_by_id.setdefault(conversion_id, set()).add(canonical_type)
        return ToolResult(status=Status.OK, conversion_id=conversion_id, data=payload)

    def plan_langgraph(self, conversion_id: str) -> ToolResult:
        """Return the deterministic LangGraph plan for a conversion session."""
        plan = self.plan_by_id.get(conversion_id)
        if plan is None:
            return self._error(ValueError("Unknown conversion_id"), "unknown_conversion")
        self.planned_conversion_ids.add(conversion_id)
        diagnostics = self.diagnostics_by_id.get(conversion_id, [])
        return ToolResult(
            status=self._status(diagnostics),
            conversion_id=conversion_id,
            diagnostics=diagnostics,
            data={"plan": plan.model_dump(mode="json")},
        )

    def list_unsupported_features(self, conversion_id: str) -> ToolResult:
        """Return only blocking compatibility diagnostics for a conversion."""
        diagnostics = [
            item
            for item in self.diagnostics_by_id.get(conversion_id, [])
            if item.severity in {Severity.CRITICAL, Severity.MAJOR}
        ]
        return ToolResult(
            status=self._status(diagnostics),
            conversion_id=conversion_id,
            diagnostics=diagnostics,
            data={"unsupported_count": len(diagnostics)},
        )

    def inspect_generated_project(self, project_path: str, conversion_id: str) -> ToolResult:
        """Check that a generated project contains every required artifact."""
        try:
            project = self.workspace.resolve(project_path)
        except SecurityError as exc:
            return self._error(exc, "unsafe_project_path")
        diagnostics: list[Diagnostic] = []
        if not project.is_dir():
            return self._error(
                ValueError("Generated project path must be a directory"), "invalid_project"
            )
        for relative in _REQUIRED_PROJECT_FILES:
            if not (project / relative).is_file():
                diagnostics.append(
                    Diagnostic(
                        code="missing_project_file",
                        severity=Severity.MAJOR,
                        message=f"Required generated-project file is missing: {relative}",
                        path=relative,
                    )
                )
        workflow_path = project / "workflow.yaml"
        if workflow_path.is_file():
            try:
                payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
                project_dsl, dsl_diagnostics = validate_dsl_payload(payload)
            except (OSError, yaml.YAMLError) as exc:
                project_dsl = None
                dsl_error = str(exc)
            else:
                dsl_error = ", ".join(item.code for item in dsl_diagnostics)
            authoritative = self.dsl_by_id.get(conversion_id)
            if project_dsl is None or authoritative is None or project_dsl != authoritative:
                diagnostics.append(
                    Diagnostic(
                        code="generated_dsl_mismatch",
                        severity=Severity.CRITICAL,
                        message="Generated workflow.yaml is not the canonical MCP-produced DSL.",
                        evidence=dsl_error or None,
                        path="workflow.yaml",
                        recommendation="Rebuild workflow.yaml with build_conversion_dsl.",
                    )
                )
        if not (project / "src").is_dir():
            diagnostics.append(
                Diagnostic(
                    code="missing_source_directory",
                    severity=Severity.MAJOR,
                    message="Generated project must contain src/.",
                    path="src",
                )
            )
        else:
            source_packages = {
                child.name
                for child in (project / "src").iterdir()
                if child.is_dir() and (child / "__init__.py").is_file()
            }
            duplicate_packages = sorted(
                name
                for name in source_packages
                if (project / name).is_dir() and (project / name / "__init__.py").is_file()
            )
            for package_name in duplicate_packages:
                diagnostics.append(
                    Diagnostic(
                        code="duplicate_source_package",
                        severity=Severity.MAJOR,
                        message=(
                            f"Package {package_name!r} exists both at the project root and under "
                            "src/."
                        ),
                        path=package_name,
                        recommendation=(
                            f"Keep only src/{package_name}/ and use {package_name}.graph:graph "
                            "in langgraph.json."
                        ),
                    )
                )
        graph_config_path = project / "langgraph.json"
        if graph_config_path.is_file():
            try:
                graph_config = json.loads(graph_config_path.read_text(encoding="utf-8"))
                graph_targets = graph_config.get("graphs")
                if not isinstance(graph_targets, dict) or not graph_targets:
                    raise ValueError("graphs must be a non-empty object")
                invalid_targets = [
                    target
                    for target in graph_targets.values()
                    if not isinstance(target, str)
                    or ":" not in target
                    or target.split(":", 1)[0].startswith("src.")
                    or "/" in target.split(":", 1)[0]
                    or "\\" in target.split(":", 1)[0]
                ]
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                invalid_targets = [str(exc)]
            if invalid_targets:
                diagnostics.append(
                    Diagnostic(
                        code="invalid_graph_module_path",
                        severity=Severity.MAJOR,
                        message=(
                            "langgraph.json must use importable src-layout module targets without "
                            "a src. prefix."
                        ),
                        evidence=", ".join(str(item) for item in invalid_targets),
                        path="langgraph.json",
                        recommendation="Use <package>.graph:graph for src/<package>/graph.py.",
                    )
                )
        if not (project / "tests").is_dir():
            diagnostics.append(
                Diagnostic(
                    code="missing_tests_directory",
                    severity=Severity.MAJOR,
                    message="Generated project must contain tests/.",
                    path="tests",
                )
            )
        self._replace_diagnostics(
            conversion_id,
            {
                "missing_project_file",
                "missing_source_directory",
                "missing_tests_directory",
                "generated_dsl_mismatch",
                "duplicate_source_package",
                "invalid_graph_module_path",
            },
            diagnostics,
        )
        check = CheckResult(
            name="project-structure",
            status=self._status(diagnostics),
            return_code=0 if not diagnostics else 1,
            output=(
                "Required generated-project structure is present."
                if not diagnostics
                else "\n".join(item.message for item in diagnostics)
            ),
        )
        self._replace_checks(conversion_id, [check])
        return ToolResult(
            status=self._status(diagnostics),
            conversion_id=conversion_id,
            diagnostics=diagnostics,
            data={"project": str(project.relative_to(self.workspace.root))},
        )

    async def _run(self, name: str, argv: list[str], cwd: Path, timeout: float) -> CheckResult:
        started = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "NO_COLOR": "1"},
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
            output = stdout.decode(errors="replace")[-_MAX_OUTPUT:]
            return CheckResult(
                name=name,
                status=Status.OK if process.returncode == 0 else Status.ERROR,
                return_code=process.returncode,
                output=output,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except TimeoutError:
            return CheckResult(
                name=name,
                status=Status.ERROR,
                output=f"Timed out after {timeout} seconds",
                duration_ms=int((time.monotonic() - started) * 1000),
            )

    async def run_quality_checks(
        self, project_path: str, conversion_id: str, timeout_seconds: float = 120
    ) -> ToolResult:
        """Run the fixed format, lint, type, and test command allowlist."""
        try:
            project = self.workspace.resolve(project_path)
        except SecurityError as exc:
            return self._error(exc, "unsafe_project_path")
        commands = (
            ("ruff-format", ["uv", "run", "--frozen", "ruff", "format", "--check", "."]),
            ("ruff-check", ["uv", "run", "--frozen", "ruff", "check", "."]),
            ("type-check", ["uv", "run", "--frozen", "ty", "check", "src"]),
            ("tests", ["uv", "run", "--frozen", "pytest", "-q"]),
        )
        checks = [await self._run(name, argv, project, timeout_seconds) for name, argv in commands]
        self._replace_checks(conversion_id, checks)
        diagnostics = [
            Diagnostic(
                code="quality_check_failed",
                severity=Severity.MAJOR,
                message=f"Quality check failed: {check.name}",
                evidence=check.output[-2000:],
            )
            for check in checks
            if check.status is Status.ERROR
        ]
        self._replace_diagnostics(conversion_id, {"quality_check_failed"}, diagnostics)
        return ToolResult(
            status=self._status(diagnostics),
            conversion_id=conversion_id,
            diagnostics=diagnostics,
            data={"checks": [item.model_dump(mode="json") for item in checks]},
        )

    async def run_contract_tests(
        self, project_path: str, conversion_id: str, timeout_seconds: float = 120
    ) -> ToolResult:
        """Run generated-project tests explicitly marked as contract tests."""
        try:
            project = self.workspace.resolve(project_path)
        except SecurityError as exc:
            return self._error(exc, "unsafe_project_path")
        check = await self._run(
            "contract-tests",
            ["uv", "run", "--frozen", "pytest", "-q", "-m", "contract"],
            project,
            timeout_seconds,
        )
        self._replace_checks(conversion_id, [check])
        diagnostics = []
        if check.status is Status.ERROR:
            diagnostics.append(
                Diagnostic(
                    code="contract_tests_failed",
                    severity=Severity.MAJOR,
                    message="Generated project contract tests failed or are missing.",
                    evidence=check.output[-2000:],
                )
            )
        self._replace_diagnostics(conversion_id, {"contract_tests_failed"}, diagnostics)
        return ToolResult(
            status=self._status(diagnostics),
            conversion_id=conversion_id,
            diagnostics=diagnostics,
            data={"check": check.model_dump(mode="json")},
        )

    async def validate_graph_contract(
        self, project_path: str, conversion_id: str, timeout_seconds: float = 30
    ) -> ToolResult:
        """Import every declared graph and verify that it exposes invocation."""
        try:
            project = self.workspace.resolve(project_path)
            config_path = project / "langgraph.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            graphs = config.get("graphs")
            if not isinstance(graphs, dict) or not graphs:
                raise ValueError("langgraph.json must declare at least one graph")
        except (SecurityError, OSError, json.JSONDecodeError, ValueError) as exc:
            return self._error(exc, "invalid_langgraph_config")
        script = (
            "import importlib, json, pathlib, sys; "
            "root=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(root/'src')); "
            "spec=json.loads((root/'langgraph.json').read_text()); result={}; "
            "\nfor name,target in spec['graphs'].items():\n"
            " module,attr=target.split(':',1); "
            "value=getattr(importlib.import_module(module),attr); "
            " result[name]={'type':type(value).__name__,'invocable':hasattr(value,'invoke')};\n"
            "print(json.dumps(result,sort_keys=True))"
        )
        check = await self._run(
            "graph-contract",
            ["uv", "run", "--frozen", "python", "-I", "-c", script, str(project)],
            project,
            timeout_seconds,
        )
        diagnostics = []
        if check.status is Status.ERROR:
            diagnostics.append(
                Diagnostic(
                    code="graph_import_failed",
                    severity=Severity.CRITICAL,
                    message="The declared LangGraph graph cannot be imported.",
                    evidence=check.output[-2000:],
                )
            )
        self._replace_checks(conversion_id, [check])
        self._replace_diagnostics(conversion_id, {"graph_import_failed"}, diagnostics)
        return ToolResult(
            status=self._status(diagnostics),
            conversion_id=conversion_id,
            diagnostics=diagnostics,
            data={"check": check.model_dump(mode="json")},
        )

    @staticmethod
    def _normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: ConversionService._normalize(item)
                for key, item in sorted(value.items())
                if key not in _IGNORED_RESPONSE_KEYS
            }
        if isinstance(value, list):
            return [ConversionService._normalize(item) for item in value]
        return value

    async def run_differential_tests(
        self,
        conversion_id: str,
        langflow_url: str,
        langgraph_url: str,
        cases: list[DifferentialCase],
        timeout_seconds: float = 30,
    ) -> ToolResult:
        """Replay cases against two allowlisted endpoints and compare responses."""
        try:
            validate_endpoint(langflow_url)
            validate_endpoint(langgraph_url)
        except SecurityError as exc:
            return self._error(exc, "endpoint_not_allowed")
        outcomes: list[DifferentialOutcome] = []
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
            for case in cases:
                try:
                    left, right = await asyncio.gather(
                        client.post(langflow_url, json=case.input),
                        client.post(langgraph_url, json=case.input),
                    )
                    left_value = self._normalize(left.json()) if left.is_success else left.text
                    right_value = self._normalize(right.json()) if right.is_success else right.text
                    equivalent = left.status_code == right.status_code and left_value == right_value
                    evidence = (
                        "responses match"
                        if equivalent
                        else json.dumps(
                            {"langflow": left_value, "langgraph": right_value}, default=str
                        )[-4000:]
                    )
                    outcomes.append(
                        DifferentialOutcome(
                            name=case.name,
                            equivalent=equivalent,
                            langflow_status=left.status_code,
                            langgraph_status=right.status_code,
                            evidence=evidence,
                        )
                    )
                except (httpx.HTTPError, ValueError) as exc:
                    outcomes.append(
                        DifferentialOutcome(name=case.name, equivalent=False, evidence=str(exc))
                    )
        diagnostics = [
            Diagnostic(
                code="differential_mismatch",
                severity=Severity.CRITICAL,
                message=f"Differential case failed: {outcome.name}",
                evidence=outcome.evidence,
            )
            for outcome in outcomes
            if not outcome.equivalent
        ]
        self._replace_diagnostics(conversion_id, {"differential_mismatch"}, diagnostics)
        return ToolResult(
            status=self._status(diagnostics),
            conversion_id=conversion_id,
            diagnostics=diagnostics,
            data={"outcomes": [item.model_dump(mode="json") for item in outcomes]},
        )

    def create_validation_report(self, conversion_id: str) -> ValidationReport:
        """Create and retain the authoritative acceptance decision."""
        checks = self.checks_by_id.get(conversion_id, [])
        check_names = {check.name for check in checks}
        missing_stages: list[str] = []
        if conversion_id not in self.built_dsl_paths:
            missing_stages.append("build_conversion_dsl")
        if conversion_id not in self.validated_dsl_ids:
            missing_stages.append("validate_conversion_dsl")
        if conversion_id not in self.planned_conversion_ids:
            missing_stages.append("plan_langgraph")
        plan = self.plan_by_id.get(conversion_id)
        if plan is not None:
            unresolved = sorted(
                definition.type
                for definition in plan.definitions
                if definition.type
                not in self.resolved_component_types_by_id.get(conversion_id, set())
            )
            missing_stages.extend(f"resolve_component:{item}" for item in unresolved)
        missing_stages.extend(sorted(_REQUIRED_ACCEPTANCE_CHECKS - check_names))
        lifecycle_diagnostics: list[Diagnostic] = []
        if conversion_id not in self.dsl_by_id:
            lifecycle_diagnostics.append(
                Diagnostic(
                    code="unknown_conversion",
                    severity=Severity.CRITICAL,
                    message="Cannot create an acceptance report for an unknown conversion.",
                )
            )
        if missing_stages:
            lifecycle_diagnostics.append(
                Diagnostic(
                    code="missing_validation_stage",
                    severity=Severity.MAJOR,
                    message="Mandatory conversion or acceptance stages have not completed.",
                    evidence=", ".join(missing_stages),
                    recommendation="Run every mandatory MCP stage before requesting acceptance.",
                )
            )
        self._replace_diagnostics(
            conversion_id,
            {"unknown_conversion", "missing_validation_stage"},
            lifecycle_diagnostics,
        )
        diagnostics = self.diagnostics_by_id.get(conversion_id, [])
        critical = sum(item.severity is Severity.CRITICAL for item in diagnostics)
        major = sum(item.severity is Severity.MAJOR for item in diagnostics)
        accepted = critical == 0 and major == 0 and all(item.status is Status.OK for item in checks)
        report = ValidationReport(
            conversion_id=conversion_id,
            accepted=accepted,
            diagnostics=diagnostics,
            checks=checks,
            critical_count=critical,
            major_count=major,
        )
        self.reports_by_id[conversion_id] = report
        return report

    def schema_resource(self) -> dict[str, Any]:
        """Return the generated JSON Schema for the current DSL version."""
        return ConversionDSL.model_json_schema()

    def catalog_resource(self) -> dict[str, object]:
        """Return the lightweight DSL 2.0 component definition index."""
        return {"dsl_version": "2.0", "components": self.registry.index()}

    def component_resource(self, component_type: str) -> dict[str, Any] | None:
        """Return one complete validated component definition and its identity."""
        return self.registry.payload(component_type)

    def component_schema_resource(self, component_type: str) -> dict[str, Any] | None:
        """Return JSON Schema for one component's normalized configuration."""
        return self.registry.config_schema(component_type)

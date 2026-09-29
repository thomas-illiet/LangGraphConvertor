"""Strict Langflow 1.12.x parser and component-definition-driven DSL normalizer."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from pydantic import ValidationError

from langflow_converter_mcp.component_definitions import FieldType, get_registry
from langflow_converter_mcp.models import (
    Component,
    ComponentExtensions,
    Connection,
    ConversionDSL,
    Diagnostic,
    FlowCapabilities,
    FlowMetadata,
    Port,
    Severity,
    StateChannel,
)

_CUSTOM_TYPES = {"customcomponent", "component"}
_SUBFLOW_TYPES = {"runflow", "subflow"}
_SUPPORTED_LANGFLOW_PREFIX = "1.12."


class FlowParseError(ValueError):
    """The source is not a supported mono-flow Langflow export."""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _node_type(node: dict[str, Any]) -> str:
    data = _as_dict(node.get("data"))
    spec = _as_dict(data.get("node"))
    candidates = (
        data.get("type"),
        spec.get("name"),
        spec.get("display_name"),
        str(node.get("id", "")).split("-", maxsplit=1)[0],
    )
    return next((str(item) for item in candidates if item), "Unknown")


def _definition_ports(component_type: str, *, output: bool) -> list[Port]:
    definition = get_registry().resolve(component_type)
    if definition is None:
        return []
    ports = definition.outputs if output else definition.inputs
    return [
        Port(
            name=port.name,
            types=port.types,
            required=port.required,
            multiple=port.multiple,
        )
        for port in ports
    ]


def _raw_connection(edge: dict[str, Any]) -> tuple[str, str, str, str, list[str]]:
    data = _as_dict(edge.get("data"))
    source_handle = _as_dict(data.get("sourceHandle"))
    target_handle = _as_dict(data.get("targetHandle"))
    return (
        str(edge.get("source") or source_handle.get("id") or ""),
        str(source_handle.get("name") or "output"),
        str(edge.get("target") or target_handle.get("id") or ""),
        str(target_handle.get("fieldName") or "input"),
        [str(item) for item in _as_list(source_handle.get("output_types"))],
    )


def _source_version_diagnostic(version: str, component_id: str) -> Diagnostic | None:
    if version.startswith(_SUPPORTED_LANGFLOW_PREFIX):
        return None
    return Diagnostic(
        code="unsupported_langflow_version",
        severity=Severity.CRITICAL,
        message=f"Langflow version {version!r} is not in the supported 1.12.x series.",
        component_id=component_id,
        recommendation="Export the flow from a compatible Langflow 1.12.x instance.",
    )


def parse_export(text: str) -> tuple[ConversionDSL, list[Diagnostic]]:
    """Parse one Langflow 1.12.x JSON export into DSL 2.0 and diagnostics."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FlowParseError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(payload, dict):
        raise FlowParseError("The export root must be an object")
    data = _as_dict(payload.get("data"))
    nodes = _as_list(data.get("nodes"))
    edges = _as_list(data.get("edges"))
    if not nodes:
        raise FlowParseError("Expected a mono-flow export with data.nodes")

    registry = get_registry()
    digest = hashlib.sha256(text.encode()).hexdigest()
    diagnostics: list[Diagnostic] = []
    components: list[Component] = []
    required_environment: set[str] = set()
    versions: set[str] = set()

    for index, raw_node in enumerate(nodes):
        if not isinstance(raw_node, dict):
            diagnostics.append(
                Diagnostic(
                    code="invalid_node",
                    severity=Severity.CRITICAL,
                    message="Node must be an object.",
                    path=f"data.nodes[{index}]",
                )
            )
            continue
        node_data = _as_dict(raw_node.get("data"))
        node_spec = _as_dict(node_data.get("node"))
        template = _as_dict(node_spec.get("template"))
        component_id = str(raw_node.get("id") or node_data.get("id") or f"node-{index}")
        raw_type = _node_type(raw_node)
        definition = registry.resolve(raw_type)
        metadata = _as_dict(node_spec.get("metadata"))
        version = str(node_spec.get("lf_version") or payload.get("version") or "unknown")
        versions.add(version)
        version_diagnostic = _source_version_diagnostic(version, component_id)
        if version_diagnostic:
            diagnostics.append(version_diagnostic)

        if raw_type.casefold() in _SUBFLOW_TYPES:
            code = "subflow_unsupported"
            message = "Nested Run Flow components are not supported in V1."
        elif raw_type.casefold() in _CUSTOM_TYPES or str(metadata.get("module", "")).startswith(
            "custom"
        ):
            code = "custom_component_unsupported"
            message = "Arbitrary custom components are not supported in V1."
        elif definition is None:
            code = "unsupported_component"
            message = f"No packaged component definition exists for {raw_type!r}."
        else:
            code = ""
            message = ""
        if code:
            diagnostics.append(
                Diagnostic(
                    code=code,
                    severity=Severity.CRITICAL,
                    message=message,
                    component_id=component_id,
                    recommendation="Add a packaged, versioned definition before generating code.",
                )
            )
            continue
        assert definition is not None

        config, extensions, environment, config_diagnostics = registry.normalize_config(
            definition.type, template, component_id
        )
        diagnostics.extend(config_diagnostics)
        required_environment.update(environment)
        components.append(
            Component(
                id=component_id,
                type=definition.type,
                definition=registry.reference(definition.type),
                display_name=str(node_spec.get("display_name") or definition.type),
                category=definition.category,
                config=config,
                extensions=ComponentExtensions(source_config=extensions),
                inputs=_definition_ports(definition.type, output=False),
                outputs=_definition_ports(definition.type, output=True),
            )
        )

    by_id = {component.id: component for component in components}
    connections: list[Connection] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        source, source_port, target, target_port, edge_types = _raw_connection(edge)
        source_component = by_id.get(source)
        target_component = by_id.get(target)
        if source_component is None or target_component is None:
            diagnostics.append(
                Diagnostic(
                    code="dangling_connection",
                    severity=Severity.CRITICAL,
                    message="Connection references a missing or unsupported component.",
                    path=f"data.edges[{index}]",
                    evidence=f"{source} -> {target}",
                )
            )
            continue
        source_port = registry.normalize_port(source_component.type, source_port, output=True)
        target_port = registry.normalize_port(target_component.type, target_port, output=False)
        declared_source = next(
            (port for port in source_component.outputs if port.name == source_port), None
        )
        connections.append(
            Connection(
                source=source,
                source_port=source_port,
                target=target,
                target_port=target_port,
                types=declared_source.types if declared_source else edge_types,
            )
        )

    consumers: dict[tuple[str, str], list[str]] = defaultdict(list)
    for edge in connections:
        consumers[(edge.source, edge.source_port)].append(edge.target)
    state = [
        StateChannel(
            name=f"{source}.{port}",
            value_types=next(
                (
                    edge.types
                    for edge in connections
                    if edge.source == source and edge.source_port == port
                ),
                [],
            ),
            producer=source,
            consumers=targets,
        )
        for (source, port), targets in sorted(consumers.items())
    ]
    types = {component.type for component in components}
    capabilities: set[str] = set()
    for component in components:
        definition = registry.resolve(component.type)
        if definition is not None:
            capabilities.update(definition.capabilities)
    flow = FlowMetadata(
        id=str(payload.get("id") or digest[:16]),
        name=str(payload.get("name") or "unnamed-flow"),
        langflow_version=next(iter(versions)) if len(versions) == 1 else None,
        source_sha256=digest,
    )
    dsl = ConversionDSL(
        flow=flow,
        components=components,
        connections=connections,
        state=state,
        capabilities=FlowCapabilities(
            streaming="streaming" in capabilities,
            memory="memory" in capabilities or "MessageHistory" in types,
            tools="tools" in capabilities
            or bool(types & {"Agent", "Calculator", "CurrentDate", "HTTPTool", "PythonTool"}),
            rag="rag" in capabilities,
        ),
        required_environment=sorted(required_environment),
    )
    return dsl, diagnostics


def validate_dsl_payload(payload: Any) -> tuple[ConversionDSL | None, list[Diagnostic]]:
    """Validate untrusted YAML against DSL 2.0 and reject legacy versions explicitly."""
    if isinstance(payload, dict) and payload.get("dsl_version") != "2.0":
        return None, [
            Diagnostic(
                code="unsupported_dsl_version",
                severity=Severity.CRITICAL,
                message=f"DSL version {payload.get('dsl_version')!r} is not supported.",
                path="dsl_version",
                recommendation="Recreate the DSL 2.0 from the original Langflow export.",
            )
        ]
    try:
        return ConversionDSL.model_validate(payload), []
    except ValidationError as exc:
        diagnostics = [
            Diagnostic(
                code="invalid_dsl",
                severity=Severity.CRITICAL,
                message=error["msg"],
                path=".".join(str(item) for item in error["loc"]),
            )
            for error in exc.errors()
        ]
        return None, diagnostics


def validate_dsl_semantics(dsl: ConversionDSL) -> list[Diagnostic]:
    """Validate definition pins, normalized config, references, and typed ports."""
    registry = get_registry()
    diagnostics: list[Diagnostic] = []
    components = {component.id: component for component in dsl.components}
    if len(components) != len(dsl.components):
        diagnostics.append(
            Diagnostic(
                code="duplicate_component_id",
                severity=Severity.CRITICAL,
                message="Component identifiers must be unique.",
            )
        )
    for component in dsl.components:
        definition = registry.resolve(component.type)
        if definition is None:
            diagnostics.append(
                Diagnostic(
                    code="unsupported_component",
                    severity=Severity.CRITICAL,
                    message=f"No packaged definition exists for {component.type!r}.",
                    component_id=component.id,
                )
            )
            continue
        expected = registry.reference(component.type)
        if component.definition != expected:
            diagnostics.append(
                Diagnostic(
                    code="component_definition_mismatch",
                    severity=Severity.CRITICAL,
                    message="Component definition version, URI, or SHA-256 does not match.",
                    component_id=component.id,
                    evidence=f"expected {expected.model_dump(mode='json')}",
                    recommendation="Recreate the DSL from the source export.",
                )
            )
        diagnostics.extend(
            registry.validate_component_config(component.type, component.config, component.id)
        )
        if component.inputs != _definition_ports(component.type, output=False) or (
            component.outputs != _definition_ports(component.type, output=True)
        ):
            diagnostics.append(
                Diagnostic(
                    code="component_ports_mismatch",
                    severity=Severity.CRITICAL,
                    message="Component ports differ from the pinned definition.",
                    component_id=component.id,
                )
            )
        secret_fields = {
            field.name for field in definition.config if field.type is FieldType.SECRET
        }
        for key in secret_fields:
            value = component.config.get(key)
            if value is not None and not (
                isinstance(value, str) and value.startswith("${") and value.endswith("}")
            ):
                diagnostics.append(
                    Diagnostic(
                        code="dsl_secret_value",
                        severity=Severity.CRITICAL,
                        message=f"Secret DSL field {key!r} must reference an environment variable.",
                        component_id=component.id,
                    )
                )
    for index, edge in enumerate(dsl.connections):
        source = components.get(edge.source)
        target = components.get(edge.target)
        if source is None or target is None:
            diagnostics.append(
                Diagnostic(
                    code="dangling_connection",
                    severity=Severity.CRITICAL,
                    message="Connection references a missing component.",
                    path=f"connections.{index}",
                )
            )
            continue
        source_port = next((port for port in source.outputs if port.name == edge.source_port), None)
        target_port = next((port for port in target.inputs if port.name == edge.target_port), None)
        if source_port is None or target_port is None:
            diagnostics.append(
                Diagnostic(
                    code="unknown_connection_port",
                    severity=Severity.CRITICAL,
                    message="Connection references a port absent from its component definition.",
                    path=f"connections.{index}",
                )
            )
            continue
        source_types = set(source_port.types)
        target_types = set(target_port.types)
        if source_types and target_types and source_types.isdisjoint(target_types):
            diagnostics.append(
                Diagnostic(
                    code="incompatible_ports",
                    severity=Severity.CRITICAL,
                    message="Connected source and target ports have incompatible types.",
                    path=f"connections.{index}",
                    evidence=f"{sorted(source_types)} -> {sorted(target_types)}",
                )
            )
    return diagnostics

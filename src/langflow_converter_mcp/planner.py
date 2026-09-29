"""LangGraph-oriented execution planning from the canonical DSL."""

from __future__ import annotations

from collections import defaultdict

from langflow_converter_mcp.component_definitions import get_registry
from langflow_converter_mcp.models import (
    ConversionDSL,
    Diagnostic,
    GenerationDefinition,
    GraphPlan,
    Severity,
)


def build_plan(dsl: ConversionDSL) -> tuple[GraphPlan, list[Diagnostic]]:
    """Build deterministic LangGraph execution layers from a validated DSL."""
    registry = get_registry()
    connected_outputs = {(edge.source, edge.source_port) for edge in dsl.connections}

    def is_executable(component_id: str, component_type: str, category: str) -> bool:
        """Resolve hybrid execution roles from a component's declarative recipe."""
        if category in {"input", "output", "executable", "control"}:
            return True
        definition = registry.resolve(component_type)
        return bool(
            definition
            and definition.recipe.mode == "hybrid"
            and any(
                source == component_id and port != "model" for source, port in connected_outputs
            )
        )

    executable = {
        component.id
        for component in dsl.components
        if is_executable(component.id, component.type, component.category)
    }
    resources = sorted(
        component.id for component in dsl.components if component.category == "resource"
    )
    predecessors: dict[str, set[str]] = {node: set() for node in executable}
    successors: dict[str, set[str]] = defaultdict(set)
    for edge in dsl.connections:
        if edge.source in executable and edge.target in executable:
            predecessors[edge.target].add(edge.source)
            successors[edge.source].add(edge.target)

    remaining = {node: set(values) for node, values in predecessors.items()}
    layers: list[list[str]] = []
    completed: set[str] = set()
    while remaining:
        ready = sorted(node for node, deps in remaining.items() if deps <= completed)
        if not ready:
            break
        layers.append(ready)
        completed.update(ready)
        for node in ready:
            remaining.pop(node)

    diagnostics: list[Diagnostic] = []
    if remaining:
        diagnostics.append(
            Diagnostic(
                code="unbounded_cycle",
                severity=Severity.CRITICAL,
                message=(
                    "The execution graph contains a cycle without a catalogued "
                    "termination contract."
                ),
                evidence=", ".join(sorted(remaining)),
                recommendation=(
                    "Model the loop as an explicit conditional node with an iteration limit."
                ),
            )
        )
    by_id = {component.id: component for component in dsl.components}
    entrypoints = sorted(
        node for node in executable if by_id[node].category == "input" or not predecessors.get(node)
    )
    outputs = sorted(
        node for node in executable if by_id[node].category == "output" or not successors[node]
    )
    plan = GraphPlan(
        conversion_id=dsl.flow.source_sha256[:16],
        resources=resources,
        dependencies=sorted(
            {
                dependency
                for component in dsl.components
                for definition in [registry.resolve(component.type)]
                if definition is not None
                for dependency in definition.dependencies
            }
        ),
        nodes=sorted(executable),
        entrypoints=entrypoints,
        outputs=outputs,
        execution_layers=layers,
        state_channels=dsl.state,
        conditional_nodes=sorted(
            component.id for component in dsl.components if component.category == "control"
        ),
        definitions=[
            GenerationDefinition(
                type=component.type,
                version=component.definition.version,
                sha256=component.definition.sha256,
                uri=component.definition.uri,
            )
            for component in sorted(
                {item.type: item for item in dsl.components}.values(), key=lambda item: item.type
            )
        ],
    )
    return plan, diagnostics

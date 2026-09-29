"""Typed contracts shared by the converter core and MCP boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["input", "output", "resource", "executable", "control"]


class Severity(StrEnum):
    """Classify how strongly a diagnostic affects acceptance."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"


class Status(StrEnum):
    """Represent the normalized status returned by MCP operations."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class Diagnostic(BaseModel):
    """Describe one actionable validation or compatibility finding."""

    code: str
    severity: Severity
    message: str
    evidence: str | None = None
    component_id: str | None = None
    path: str | None = None
    recommendation: str | None = None


class Port(BaseModel):
    """Describe a typed input or output port on a normalized component."""

    name: str
    types: list[str] = Field(default_factory=list)
    required: bool = False
    multiple: bool = False


class ComponentDefinitionReference(BaseModel):
    """Pin a component instance to one immutable packaged definition."""

    model_config = ConfigDict(extra="forbid")

    version: str
    sha256: str
    uri: str


class ComponentExtensions(BaseModel):
    """Retain non-generative source values that the definition does not recognize."""

    model_config = ConfigDict(extra="forbid")

    source_config: dict[str, Any] = Field(default_factory=dict)


class Component(BaseModel):
    """Represent one normalized Langflow component in the durable DSL."""

    id: str
    type: str
    definition: ComponentDefinitionReference
    display_name: str
    category: Category
    config: dict[str, Any] = Field(default_factory=dict)
    extensions: ComponentExtensions = Field(default_factory=ComponentExtensions)
    inputs: list[Port] = Field(default_factory=list)
    outputs: list[Port] = Field(default_factory=list)


class Connection(BaseModel):
    """Connect one normalized component output port to an input port."""

    source: str
    source_port: str
    target: str
    target_port: str
    types: list[str] = Field(default_factory=list)


class FlowMetadata(BaseModel):
    """Record stable source metadata for a converted Langflow flow."""

    id: str
    name: str
    langflow_version: str | None = None
    source_sha256: str


class FlowCapabilities(BaseModel):
    """Summarize runtime capabilities detected in a flow."""

    streaming: bool = False
    memory: bool = False
    tools: bool = False
    rag: bool = False


class StateChannel(BaseModel):
    """Describe one namespaced LangGraph state channel."""

    name: str
    value_types: list[str] = Field(default_factory=list)
    producer: str
    consumers: list[str] = Field(default_factory=list)


class EquivalenceCriteria(BaseModel):
    """Select observable behaviors required for differential equivalence."""

    compare_messages: bool = True
    compare_json: bool = True
    compare_tool_calls: bool = True
    compare_stream_events: bool = True


class ConversionDSL(BaseModel):
    """Define the versioned, durable contract between Langflow and LangGraph."""

    model_config = ConfigDict(extra="forbid")

    dsl_version: Literal["2.0"] = "2.0"
    flow: FlowMetadata
    components: list[Component]
    connections: list[Connection]
    state: list[StateChannel]
    capabilities: FlowCapabilities
    required_environment: list[str] = Field(default_factory=list)
    equivalence: EquivalenceCriteria = Field(default_factory=EquivalenceCriteria)


class GenerationDefinition(BaseModel):
    """Tell OpenCode which exact definition resource a plan requires."""

    type: str
    version: str
    sha256: str
    uri: str


class GraphPlan(BaseModel):
    """Describe the LangGraph resources, nodes, and execution layers to build."""

    conversion_id: str
    resources: list[str]
    dependencies: list[str]
    nodes: list[str]
    entrypoints: list[str]
    outputs: list[str]
    execution_layers: list[list[str]]
    state_channels: list[StateChannel]
    conditional_nodes: list[str] = Field(default_factory=list)
    definitions: list[GenerationDefinition] = Field(default_factory=list)


class ToolResult(BaseModel):
    """Provide a consistent structured result for MCP tools."""

    status: Status
    conversion_id: str | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class CheckResult(BaseModel):
    """Capture one deterministic subprocess quality check."""

    name: str
    status: Status
    return_code: int | None = None
    output: str = ""
    duration_ms: int = 0


class ValidationReport(BaseModel):
    """Aggregate authoritative diagnostics and checks into an acceptance decision."""

    conversion_id: str
    accepted: bool
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    critical_count: int = 0
    major_count: int = 0


class DifferentialCase(BaseModel):
    """Describe one request replayed against Langflow and LangGraph."""

    name: str
    input: dict[str, Any]


class DifferentialOutcome(BaseModel):
    """Record the normalized comparison result for a differential case."""

    name: str
    equivalent: bool
    langflow_status: int | None = None
    langgraph_status: int | None = None
    evidence: str = ""

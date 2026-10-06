"""Load and validate immutable, package-owned component DSL definitions."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from langflow_converter_mcp.models import (
    Category,
    ComponentDefinitionReference,
    Diagnostic,
    Severity,
)


class DefinitionError(RuntimeError):
    """Indicate that packaged component definitions are invalid or ambiguous."""


class FieldType(StrEnum):
    """List configuration value types supported by the declarative DSL."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"
    JSON = "json"
    PATH = "path"
    SECRET = "secret"


class ConfigurationField(BaseModel):
    """Define one normalized, typed component configuration field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    source_keys: tuple[str, ...] = ()
    type: FieldType
    description: str
    required: bool = False
    default: Any = None
    options: tuple[Any, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    environment: str | None = None
    overridable: bool = False

    @model_validator(mode="after")
    def validate_contract(self) -> ConfigurationField:
        """Ensure enum and secret fields carry the metadata they require."""
        if self.type is FieldType.ENUM and not self.options:
            raise ValueError("enum fields require non-empty options")
        if self.type is FieldType.SECRET and not self.environment:
            raise ValueError("secret fields require an environment variable")
        return self


class DefinitionPort(BaseModel):
    """Define a stable logical component port and its Langflow source aliases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    source_names: tuple[str, ...] = ()
    types: tuple[str, ...]
    description: str
    required: bool = False
    multiple: bool = False


class StateContract(BaseModel):
    """Describe one logical state value read or written by generated code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    types: tuple[str, ...]
    reducer: str | None = None
    persisted: bool = True


class PythonRecipe(BaseModel):
    """Provide declarative implementation guidance without executable templates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["input", "output", "factory", "node", "router", "hybrid"]
    async_supported: bool = True
    streaming: bool = False
    imports: tuple[str, ...] = ()
    construction: tuple[str, ...]
    invocation: str
    error_handling: tuple[str, ...]


class DefinitionTest(BaseModel):
    """Specify one behavioral test OpenCode must generate for a component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    scenario: str
    expected: str


class ComponentDefinition(BaseModel):
    """Define the complete generation contract for one canonical component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    definition_version: str
    type: str
    aliases: tuple[str, ...]
    langflow_series: Literal["1.12.x"]
    category: Category
    description: str
    langgraph_role: str
    capabilities: tuple[str, ...] = ()
    config: tuple[ConfigurationField, ...] = ()
    inputs: tuple[DefinitionPort, ...] = ()
    outputs: tuple[DefinitionPort, ...] = ()
    state_reads: tuple[StateContract, ...] = ()
    state_writes: tuple[StateContract, ...] = ()
    dependencies: tuple[str, ...] = ()
    recipe: PythonRecipe
    invariants: tuple[str, ...]
    tests: tuple[DefinitionTest, ...]
    ignored_source_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_unique_names(self) -> ComponentDefinition:
        """Reject duplicate fields and ports inside one definition."""
        for label, values in (
            ("config", [field.name for field in self.config]),
            ("inputs", [port.name for port in self.inputs]),
            ("outputs", [port.name for port in self.outputs]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} names")
        return self


class ComponentDefinitionRegistry:
    """Provide immutable lookup, validation, and schemas for packaged definitions."""

    def __init__(self) -> None:
        """Load every packaged YAML definition and reject registry ambiguity."""
        loaded: dict[str, ComponentDefinition] = {}
        aliases: dict[str, str] = {}
        digests: dict[str, str] = {}
        definitions = files("langflow_converter_mcp.components.definitions")
        for resource in sorted(definitions.iterdir(), key=lambda item: item.name):
            if not resource.name.endswith(".yaml"):
                continue
            raw = resource.read_text(encoding="utf-8")
            try:
                payload = yaml.safe_load(raw)
                definition = ComponentDefinition.model_validate(payload)
            except (yaml.YAMLError, ValueError) as exc:
                raise DefinitionError(f"Invalid definition {resource.name}: {exc}") from exc
            if definition.type in loaded:
                raise DefinitionError(f"Duplicate component type: {definition.type}")
            canonical = self._canonical_bytes(definition)
            loaded[definition.type] = definition
            digests[definition.type] = hashlib.sha256(canonical).hexdigest()
            for alias in {definition.type, *definition.aliases}:
                key = alias.casefold()
                if key in aliases:
                    raise DefinitionError(f"Duplicate component alias: {alias}")
                aliases[key] = definition.type
        if len(loaded) != 20:
            raise DefinitionError(f"Expected 20 component definitions, found {len(loaded)}")
        self._definitions = MappingProxyType(loaded)
        self._aliases = MappingProxyType(aliases)
        self._digests = MappingProxyType(digests)

    @staticmethod
    def _canonical_bytes(definition: ComponentDefinition) -> bytes:
        payload = definition.model_dump(mode="json", exclude_none=True)
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    def resolve(self, component_type: str) -> ComponentDefinition | None:
        """Resolve a canonical type or alias to its immutable definition."""
        canonical = self._aliases.get(component_type.casefold())
        return self._definitions.get(canonical) if canonical else None

    def digest(self, component_type: str) -> str:
        """Return the canonical SHA-256 digest for a supported definition."""
        definition = self.resolve(component_type)
        if definition is None:
            raise KeyError(component_type)
        return self._digests[definition.type]

    def reference(self, component_type: str) -> ComponentDefinitionReference:
        """Build a pinned workflow reference for a supported definition."""
        definition = self.resolve(component_type)
        if definition is None:
            raise KeyError(component_type)
        return ComponentDefinitionReference(
            version=definition.definition_version,
            sha256=self.digest(definition.type),
            uri=f"dsl://components/{definition.type}",
        )

    def index(self) -> list[dict[str, Any]]:
        """Return a lightweight, stable index suitable for MCP discovery."""
        return [
            {
                "type": definition.type,
                "definition_version": definition.definition_version,
                "category": definition.category,
                "description": definition.description,
                "uri": f"dsl://components/{definition.type}",
                "schema_uri": f"dsl://components/{definition.type}/schema",
                "sha256": self._digests[definition.type],
            }
            for definition in self._definitions.values()
        ]

    def payload(self, component_type: str) -> dict[str, Any] | None:
        """Serialize one complete component definition with identity metadata."""
        definition = self.resolve(component_type)
        if definition is None:
            return None
        return {
            "definition": definition.model_dump(mode="json", exclude_none=True),
            "sha256": self._digests[definition.type],
            "uri": f"dsl://components/{definition.type}",
        }

    def config_schema(self, component_type: str) -> dict[str, Any] | None:
        """Build JSON Schema for a definition's normalized configuration object."""
        definition = self.resolve(component_type)
        if definition is None:
            return None
        properties: dict[str, Any] = {}
        required: list[str] = []
        type_map = {
            FieldType.STRING: "string",
            FieldType.INTEGER: "integer",
            FieldType.NUMBER: "number",
            FieldType.BOOLEAN: "boolean",
            FieldType.ENUM: "string",
            FieldType.JSON: ["object", "array", "string", "number", "boolean", "null"],
            FieldType.PATH: "string",
            FieldType.SECRET: "string",
        }
        for field in definition.config:
            schema: dict[str, Any] = {
                "type": type_map[field.type],
                "description": field.description,
            }
            if field.options:
                schema["enum"] = field.options
            if field.minimum is not None:
                schema["minimum"] = field.minimum
            if field.maximum is not None:
                schema["maximum"] = field.maximum
            if field.default is not None:
                schema["default"] = field.default
            properties[field.name] = schema
            if field.required:
                required.append(field.name)
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"{definition.type}Config",
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    def normalize_port(self, component_type: str, port_name: str, *, output: bool) -> str:
        """Map a Langflow port alias to the stable definition port name."""
        definition = self.resolve(component_type)
        if definition is None:
            return port_name
        ports = definition.outputs if output else definition.inputs
        for port in ports:
            if port_name.casefold() in {
                candidate.casefold() for candidate in {port.name, *port.source_names}
            }:
                return port.name
        return port_name

    def validate_component_config(
        self, component_type: str, config: dict[str, Any], component_id: str
    ) -> list[Diagnostic]:
        """Validate already-normalized DSL configuration against one definition."""
        definition = self.resolve(component_type)
        if definition is None:
            return []
        diagnostics: list[Diagnostic] = []
        fields = {field.name: field for field in definition.config}
        for key, value in config.items():
            field = fields.get(key)
            if field is None:
                diagnostics.append(
                    Diagnostic(
                        code="unknown_dsl_config_field",
                        severity=Severity.CRITICAL,
                        message=f"DSL config field {key!r} is not declared by {definition.type}.",
                        component_id=component_id,
                    )
                )
                continue
            _, field_diagnostics = self._validate_value(field, value, component_id)
            diagnostics.extend(field_diagnostics)
        for field in definition.config:
            if field.required and field.name not in config:
                diagnostics.append(
                    Diagnostic(
                        code="missing_component_field",
                        severity=Severity.MAJOR,
                        message=f"Required field {field.name!r} is missing.",
                        component_id=component_id,
                    )
                )
        return diagnostics

    def normalize_config(
        self, component_type: str, template: dict[str, Any], component_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], list[str], list[Diagnostic]]:
        """Normalize known values and isolate unknown source fields with warnings."""
        definition = self.resolve(component_type)
        if definition is None:
            return {}, {}, [], []
        config: dict[str, Any] = {}
        extensions: dict[str, Any] = {}
        environment: set[str] = set()
        diagnostics: list[Diagnostic] = []
        by_source = {
            source_key: field
            for field in definition.config
            for source_key in {field.name, *field.source_keys}
        }
        port_fields = {
            source_name
            for port in definition.inputs
            for source_name in {port.name, *port.source_names}
        }
        seen: set[str] = set()
        for key, raw in template.items():
            if key.startswith("_") or not isinstance(raw, dict) or "value" not in raw:
                continue
            value = raw.get("value")
            if value == "__UNDEFINED__" or key in port_fields:
                continue
            field = by_source.get(key)
            if field is None:
                if key not in definition.ignored_source_fields:
                    extensions[key] = value
                    diagnostics.append(
                        Diagnostic(
                            code="unknown_component_field",
                            severity=Severity.MINOR,
                            message=f"Source field {key!r} is not declared by {definition.type}.",
                            component_id=component_id,
                            recommendation="Do not use extensions.source_config for generation.",
                        )
                    )
                continue
            seen.add(field.name)
            normalized, field_diagnostics = self._validate_value(field, value, component_id)
            diagnostics.extend(field_diagnostics)
            if normalized is not None:
                config[field.name] = normalized
            if field.environment:
                environment.add(field.environment)
        for field in definition.config:
            if field.environment:
                environment.add(field.environment)
            if field.name in seen:
                continue
            if field.environment:
                config[field.name] = f"${{{field.environment}}}"
            elif field.default is not None:
                config[field.name] = field.default
            elif field.required:
                diagnostics.append(
                    Diagnostic(
                        code="missing_component_field",
                        severity=Severity.MAJOR,
                        message=f"Required field {field.name!r} is missing.",
                        component_id=component_id,
                    )
                )
        return config, extensions, sorted(environment), diagnostics

    @staticmethod
    def _validate_value(
        field: ConfigurationField, value: Any, component_id: str
    ) -> tuple[Any, list[Diagnostic]]:
        diagnostics: list[Diagnostic] = []
        if field.type is FieldType.SECRET:
            placeholder = f"${{{field.environment}}}"
            if value not in (None, "", placeholder):
                diagnostics.append(
                    Diagnostic(
                        code="embedded_secret",
                        severity=Severity.CRITICAL,
                        message=f"Secret field {field.name!r} contains an exported value.",
                        component_id=component_id,
                        recommendation=f"Provide {field.environment} at runtime.",
                    )
                )
            return placeholder, diagnostics
        valid = {
            FieldType.STRING: isinstance(value, str),
            FieldType.PATH: isinstance(value, str),
            FieldType.INTEGER: isinstance(value, int) and not isinstance(value, bool),
            FieldType.NUMBER: isinstance(value, int | float) and not isinstance(value, bool),
            FieldType.BOOLEAN: isinstance(value, bool),
            FieldType.ENUM: value in field.options,
            FieldType.JSON: True,
        }.get(field.type, False)
        if not valid:
            diagnostics.append(
                Diagnostic(
                    code="invalid_component_field",
                    severity=Severity.MAJOR,
                    message=f"Field {field.name!r} has an invalid {field.type} value.",
                    component_id=component_id,
                    evidence=repr(value),
                )
            )
            return None, diagnostics
        if isinstance(value, int | float) and not isinstance(value, bool):
            if field.minimum is not None and value < field.minimum:
                valid = False
            if field.maximum is not None and value > field.maximum:
                valid = False
            if not valid:
                diagnostics.append(
                    Diagnostic(
                        code="component_field_out_of_range",
                        severity=Severity.MAJOR,
                        message=f"Field {field.name!r} is outside its allowed range.",
                        component_id=component_id,
                        evidence=repr(value),
                    )
                )
                return None, diagnostics
        if field.environment:
            return f"${{{field.environment}}}", diagnostics
        return value, diagnostics


@lru_cache(maxsize=1)
def get_registry() -> ComponentDefinitionRegistry:
    """Return the process-wide immutable packaged definition registry."""
    return ComponentDefinitionRegistry()

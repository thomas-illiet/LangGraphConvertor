"""Test Langflow parsing, DSL normalization, and semantic validation."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from langflow_converter_mcp.models import Severity
from langflow_converter_mcp.parser import (
    parse_export,
    validate_dsl_payload,
    validate_dsl_semantics,
)
from langflow_converter_mcp.planner import build_plan


def test_parse_supported_flow(supported_flow: dict[str, Any]) -> None:
    """A supported flow produces a clean DSL and ordered execution plan."""
    dsl, diagnostics = parse_export(json.dumps(supported_flow))

    assert diagnostics == []
    assert dsl.flow.id == "flow-1"
    assert [item.type for item in dsl.components] == ["ChatInput", "ChatOutput"]
    assert dsl.dsl_version == "2.0"
    assert all(len(item.definition.sha256) == 64 for item in dsl.components)
    assert dsl.state[0].name == "ChatInput-a.message"

    plan, plan_diagnostics = build_plan(dsl)
    assert plan_diagnostics == []
    assert plan.execution_layers == [["ChatInput-a"], ["ChatOutput-b"]]
    assert plan.entrypoints == ["ChatInput-a"]
    assert plan.outputs == ["ChatOutput-b"]


def test_unknown_component_fails_closed(supported_flow: dict[str, Any]) -> None:
    """An unknown integration produces a blocking compatibility finding."""
    supported_flow["data"]["nodes"][0]["data"]["type"] = "MysterySaaS"
    _, diagnostics = parse_export(json.dumps(supported_flow))

    assert any(item.code == "unsupported_component" for item in diagnostics)
    assert all(item.severity is Severity.CRITICAL for item in diagnostics)


def test_embedded_secret_is_replaced_and_blocked(supported_flow: dict[str, Any]) -> None:
    """Exported secrets are removed from the DSL and block conversion."""
    node = supported_flow["data"]["nodes"][0]
    node["data"]["type"] = "OpenAIModel"
    template = node["data"]["node"]["template"]
    template["model_name"] = {"value": "test-model"}
    template["api_key"] = {"value": "should-not-survive"}

    dsl, diagnostics = parse_export(json.dumps(supported_flow))

    assert dsl.components[0].config["api_key"].startswith("${")
    assert "should-not-survive" not in dsl.model_dump_json()
    assert diagnostics[0].code == "embedded_secret"


def test_openai_model_uses_only_runtime_provider_configuration(
    supported_flow: dict[str, Any],
) -> None:
    """A source endpoint is replaced by mandatory runtime provider placeholders."""
    node = supported_flow["data"]["nodes"][0]
    node["data"]["type"] = "OpenAIModel"
    template = node["data"]["node"]["template"]
    template["model_name"] = {"value": "test-model"}
    template["openai_api_base"] = {"value": "https://source.invalid/v1"}

    dsl, diagnostics = parse_export(json.dumps(supported_flow))

    config = dsl.components[0].config
    assert config["model"] == "test-model"
    assert config["base_url"] == "${OPENAI_BASE_URL}"
    assert config["api_key"] == "${OPENAI_API_KEY}"
    assert dsl.required_environment == ["OPENAI_API_KEY", "OPENAI_BASE_URL"]
    assert "source.invalid" not in dsl.model_dump_json()
    assert diagnostics == []


def test_openai_embeddings_share_runtime_provider_configuration(
    supported_flow: dict[str, Any],
) -> None:
    """Embedding configuration uses the same mandatory endpoint and token variables."""
    flow = deepcopy(supported_flow)
    node = flow["data"]["nodes"][0]
    node["data"]["type"] = "OpenAIEmbeddings"
    node["data"]["node"]["template"] = {"model_name": {"value": "embed-model"}}
    flow["data"]["edges"] = []

    dsl, diagnostics = parse_export(json.dumps(flow))

    assert dsl.components[0].config["base_url"] == "${OPENAI_BASE_URL}"
    assert dsl.components[0].config["api_key"] == "${OPENAI_API_KEY}"
    assert dsl.required_environment == ["OPENAI_API_KEY", "OPENAI_BASE_URL"]
    assert diagnostics == []


def test_semantic_validation_rejects_tampered_ports(
    supported_flow: dict[str, Any],
) -> None:
    """Ports altered after normalization fail definition pin validation."""
    dsl, _ = parse_export(json.dumps(supported_flow))
    dsl.components[1].inputs[0].types = ["JSON"]

    diagnostics = validate_dsl_semantics(dsl)

    assert {item.code for item in diagnostics} >= {"component_ports_mismatch", "incompatible_ports"}


def test_unknown_field_isolated_as_non_generative_extension(
    supported_flow: dict[str, Any],
) -> None:
    """Unknown exported fields warn and remain outside normalized config."""
    template = supported_flow["data"]["nodes"][0]["data"]["node"]["template"]
    template["future_option"] = {"value": "opaque"}

    dsl, diagnostics = parse_export(json.dumps(supported_flow))

    component = dsl.components[0]
    assert "future_option" not in component.config
    assert component.extensions.source_config == {"future_option": "opaque"}
    assert [item.code for item in diagnostics] == ["unknown_component_field"]


def test_dsl_1_is_explicitly_rejected() -> None:
    """Legacy DSL files fail with the documented breaking-version error."""
    dsl, diagnostics = validate_dsl_payload({"dsl_version": "1.0"})

    assert dsl is None
    assert [item.code for item in diagnostics] == ["unsupported_dsl_version"]


def test_tampered_definition_digest_is_blocking(supported_flow: dict[str, Any]) -> None:
    """A modified component-definition pin invalidates the workflow DSL."""
    dsl, _ = parse_export(json.dumps(supported_flow))
    dsl.components[0].definition.sha256 = "0" * 64

    diagnostics = validate_dsl_semantics(dsl)

    assert "component_definition_mismatch" in {item.code for item in diagnostics}

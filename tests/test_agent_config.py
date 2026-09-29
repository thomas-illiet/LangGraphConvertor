"""Test the constrained OpenCode conversion-agent contract."""

from __future__ import annotations

from pathlib import Path

import yaml


def _agent_document() -> tuple[dict[str, object], str]:
    """Load the project conversion agent frontmatter and prompt body."""
    path = Path(__file__).parents[1] / ".opencode/agents/langflow-to-langgraph.md"
    document = path.read_text(encoding="utf-8")
    _, frontmatter, prompt = document.split("---", maxsplit=2)
    parsed = yaml.safe_load(frontmatter)
    assert isinstance(parsed, dict)
    return parsed, prompt


def test_conversion_agent_is_confined_to_the_workspace() -> None:
    """The conversion agent cannot explore external locations, the web, or subagents."""
    frontmatter, prompt = _agent_document()
    permissions = frontmatter["permission"]
    normalized_prompt = " ".join(prompt.split())

    assert isinstance(permissions, dict)
    assert permissions["external_directory"] == "deny"
    assert permissions["webfetch"] == "deny"
    assert permissions["websearch"] == "deny"
    assert permissions["task"] == "deny"
    assert permissions["skill"] == "deny"
    assert permissions["question"] == "allow"
    assert permissions["bash"] == {"*": "deny", "uv lock --directory *": "allow"}
    assert "Do not search the filesystem to infer either path." in normalized_prompt


def test_conversion_agent_declares_the_deterministic_tool_order() -> None:
    """The prompt orders every mandatory MCP operation before local acceptance."""
    _, prompt = _agent_document()
    tools = (
        "langflow-converter_inspect_langflow_export",
        "langflow-converter_build_conversion_dsl",
        "langflow-converter_validate_conversion_dsl",
        "langflow-converter_plan_langgraph",
        "langflow-converter_resolve_component",
        "langflow-converter_inspect_generated_project",
        "langflow-converter_validate_graph_contract",
        "langflow-converter_run_quality_checks",
        "langflow-converter_run_contract_tests",
        "langflow-converter_create_validation_report",
    )

    positions = [prompt.index(f"`{tool}`") for tool in tools]
    assert positions == sorted(positions)
    assert "Do not call `langflow-converter_run_differential_tests`" in prompt


def test_project_does_not_force_the_conversion_agent_as_default() -> None:
    """Interactive users must continue to select the conversion agent manually."""
    config_path = Path(__file__).parents[1] / "opencode.jsonc"
    config = config_path.read_text(encoding="utf-8")

    assert '"default_agent"' not in config

"""Test the constrained OpenCode conversion-agent contract."""

from __future__ import annotations

import json
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
    assert frontmatter["temperature"] == 0
    assert frontmatter["steps"] == 80
    assert frontmatter["options"] == {"reasoningEffort": "none"}
    assert permissions["*"] == "deny"
    assert permissions["edit"] == "allow"
    assert permissions["question"] == "allow"
    assert permissions["bash"] == {"*": "deny", "uv lock --directory *": "allow"}
    assert permissions["langflow-converter_*"] == "allow"
    assert "Do not search the filesystem to infer either path." in normalized_prompt
    assert "do not retry with alternate relative or absolute paths" in normalized_prompt
    assert (
        "Filesystem discovery and reading tools are intentionally unavailable." in normalized_prompt
    )
    assert "A denied tool is a hard boundary" in normalized_prompt
    assert normalized_prompt.startswith("/no_think")
    assert "call the file-writing tool immediately for exactly one file" in normalized_prompt
    assert "Do not draft multiple files" in normalized_prompt
    assert "`<generated-project-directory>/workflow.yaml`" in normalized_prompt
    assert "Use exactly one source layout: `src/<package_name>/`." in normalized_prompt
    assert "never prefix the module with `src.`" in normalized_prompt


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


def test_local_mcp_uses_the_opencode_workspace_as_its_cwd() -> None:
    """The relative MCP security root is resolved from the OpenCode workspace."""
    config_path = Path(__file__).parents[1] / "opencode.jsonc"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    local = config["mcp"]["langflow-converter"]
    assert local["cwd"] == "."
    workspace_index = local["command"].index("--workspace") + 1
    assert local["command"][workspace_index] == "."

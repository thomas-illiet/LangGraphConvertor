# Repository agent guide

## Purpose

This repository provides deterministic MCP guardrails for an OpenCode agent that converts one
Langflow JSON flow into a Python LangGraph project. The MCP server analyzes and validates; it must
not generate the application code itself.

## Architecture

- `src/langflow_converter_mcp/tools/` contains exactly one public MCP tool per file. New tools must
  be registered in `tools/__init__.py` without changing existing tool names or schemas silently.
- `resources.py` contains read-only MCP resources and templates.
- `service.py` owns transport-independent orchestration and validation.
- `components/definitions/` contains the 20 package-owned YAML generation contracts. Workspace
  overrides are forbidden.
- `component_definitions.py`, `parser.py`, and `planner.py` own deterministic domain behavior.
- `security.py` owns workspace and endpoint boundaries. Do not bypass it from a tool.
- `server.py` only composes the service, tools, and resources.

## Non-negotiable behavior

- Fail closed for unknown components, embedded secrets, incompatible ports, dangling edges, and
  unbounded cycles.
- Generate only DSL 2.0. Reject DSL 1.0 explicitly and never use `extensions.source_config` as a
  code-generation input.
- Resolve every caller-provided path below the configured workspace, including symlinks.
- Never run caller-provided shell text. Subprocess commands must be fixed argument vectors.
- Keep HTTP bound to `127.0.0.1` unless a separately reviewed authentication design is added.
- A rerun of a validation gate replaces its earlier result so OpenCode can converge after a fix.
- Critical and major findings always block acceptance.
- Never weaken, remove, or hide a validation in order to make a generated project pass.

## Python conventions

- Support Python 3.12 or newer and manage dependencies with `uv` and `uv.lock`.
- Use Pydantic models for MCP input and structured output contracts.
- Add module, class, public function, and public method docstrings to all Python code, including
  tests. Ruff enforces this rule.
- Keep transport details out of the conversion core.
- Prefer explicit typed results over exceptions at the MCP boundary.

## Required validation

Run all commands before handing work back:

```console
uv run ruff format --check .
uv run ruff check .
uv run ty check src
uv run pytest
uv build --offline
```

When changing MCP registration or configuration, also verify `opencode mcp list` and perform at
least one stdio round trip. For HTTP changes, perform the same tool call through the local
Streamable HTTP transport.

## Scope discipline

- Preserve the mono-flow V1 boundary unless expansion is explicitly requested.
- Do not introduce support claims without fixtures and contract tests.
- Do not commit credentials, generated projects, build artifacts, or local OpenCode state.

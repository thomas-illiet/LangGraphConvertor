# Langflow Converter MCP

Guardrails and domain tools for an OpenCode agent that converts one Langflow JSON flow into a
tested Python LangGraph project.

The MCP server does **not** generate application code. It parses the Langflow export, persists a
durable YAML contract, exposes component and graph-planning knowledge, and owns acceptance checks.
OpenCode writes the generated project and fixes blocking findings for at most three cycles.

## Repository structure

- `src/langflow_converter_mcp/tools/`: one module per public MCP tool.
- `src/langflow_converter_mcp/resources.py`: read-only MCP resources and templates.
- `src/langflow_converter_mcp/service.py`: transport-independent orchestration.
- `components/definitions/`: 20 autonomous, package-owned YAML generation contracts.
- `component_definitions.py`, `parser.py`, and `planner.py`: deterministic conversion knowledge.
- `security.py`: filesystem and endpoint boundaries.
- `AGENTS.md`: mandatory engineering and validation rules for coding agents.

All Python modules, classes, public functions, and public methods must carry docstrings. Ruff
enforces this requirement for production code and tests.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- OpenCode with a fully configured model provider
- A Langflow instance for differential acceptance tests

## Setup

```console
uv sync --all-groups --frozen
uv run pytest
```

The checked-in `opencode.jsonc` enables the local stdio MCP. Start OpenCode at the repository root
and select the `langflow-to-langgraph` agent, or run it non-interactively:

```console
opencode run --agent langflow-to-langgraph \
  "Convert examples/basic-chat.json into generated/basic-chat. Use workflow.yaml as the DSL."
```

The agent must stop if the MCP reports a critical or major diagnostic.

## DSL 2.0 component contracts

Every normalized workflow component pins a packaged definition by semantic definition version,
MCP URI, and canonical SHA-256. The definition describes typed configuration, port cardinality,
state reads and writes, reducers, dependencies, imports, construction and invocation recipes,
error behavior, invariants, and required tests. OpenCode can therefore generate a project from the
DSL and MCP resources without a hidden Python component catalog.

The authoritative resources are:

- `dsl://components`: lightweight index of the 20 supported definitions.
- `dsl://components/{type}`: complete YAML generation contract.
- `dsl://components/{type}/schema`: closed JSON Schema for normalized configuration.
- `dsl://schema/current`: workflow DSL 2.0 JSON Schema.

Legacy `catalog://components` resources remain read-only aliases. DSL 1.0 is intentionally rejected
with `unsupported_dsl_version`; recreate it from the original Langflow export. Unknown source fields
are retained only in `extensions.source_config`, produce a warning, and must never drive generation.

## Transports

OpenCode starts stdio automatically from `opencode.jsonc`. To expose the same server over local
Streamable HTTP:

```console
uv run --frozen langflow-converter-mcp --workspace . --transport http --port 8765
```

The HTTP listener is hard-coded to `127.0.0.1`. Enable `langflow-converter-http` and disable the
stdio entry in `opencode.jsonc` when using it.

## OpenCode provider

An OpenAI-compatible endpoint needs a complete OpenCode provider declaration: provider ID,
compatible package, base URL, API-key environment reference, and model map. A base URL alone is
not sufficient. Keep provider credentials outside this repository and inject configuration into
the OpenCode process.

## Security boundary

- Every file path is resolved below `--workspace`, including symlinks.
- Input and output files are capped at 5 MiB.
- Quality checks use a fixed argument vector and never a shell.
- Differential endpoints default to `localhost`, `127.0.0.1`, and `::1`. Extend the explicit
  `LFCM_ALLOWED_ENDPOINT_HOSTS` comma-separated allowlist for a remote Langflow instance.
- HTTP redirects are disabled during differential checks.
- Tool output is capped before it is returned to the model.

Importing a generated graph executes generated Python in a subprocess. It is a validation boundary,
not an operating-system sandbox; run the converter in a disposable container for untrusted exports.

## V1 component scope

The versioned definitions include chat/text input and output, prompts, OpenAI-compatible chat and
embeddings, agents and common tools, message history, text/PDF loading, splitting, Chroma,
retrieval, parsing, simple type conversion, and explicit conditional routing. Custom components,
nested flows, unknown SaaS integrations, non-1.12.x exports, and implicit loops fail closed.

## Development

```console
uv run ruff format --check .
uv run ruff check .
uv run ty check src
uv run pytest
```

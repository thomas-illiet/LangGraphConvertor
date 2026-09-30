# basic-chat

LangGraph conversion of the `examples/basic-chat.json` Langflow flow.

## Layout

- `workflow.yaml` - canonical DSL 2.0 produced by the langflow-converter MCP
- `langgraph.json` - LangGraph platform configuration (graph entry point)
- `src/basic_chat/` - the generated package (single `src/` layout)
  - `graph.py` - compiled `StateGraph` exposed as `basic_chat.graph:graph`
  - `state.py` - typed `BasicChatState` with an `add_messages` reducer channel
  - `models.py` - `ChatOpenAI` factory for the OpenAIModel component
  - `nodes.py` - ChatInput / OpenAIModel / ChatOutput node adapters
- `tests/` - unit tests and `@pytest.mark.contract` contract tests
- `.env.example` - required environment variables (`OPENAI_API_KEY`)

## Running

```console
uv sync
uv run pytest
```

The graph is importable as `basic_chat.graph:graph`.

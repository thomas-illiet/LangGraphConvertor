# local-rag

LangGraph conversion of the `local-rag` Langflow export (Langflow 1.12.0).

The flow loads a local knowledge file, splits it into chunks, embeds it with an
OpenAI-compatible model, indexes it into a local Chroma collection, retrieves the
top-k chunks for a query, converts the result to JSON, and returns it as the
structured output.

Run the compiled graph with the LangGraph server declared in `langgraph.json`.

# Design evolution and as-built architecture

## Current v1.0.0 source of truth

The implemented portfolio path is:

~~~text
Browser
  -> React / Vite / TypeScript
  -> Nginx same-origin proxy
  -> FastAPI
  -> SQLite
  -> finite LangGraph Agent
  -> project-owned Legal Retrieval and Legal Calculator MCP stdio children
  -> citation and semantic guardrail
  -> public verified response
~~~

The production retrieval configuration is R2_H2_C10_O5_L512_B1: BGE-M3 dense retrieval, Qdrant,
Underthesea plus BM25S lexical retrieval, project-owned RRF, and bge-reranker-v2-m3. Docker evidence
is CPU-only. React is the only implemented frontend, and MCP transport remains stdio inside the API
container.

Use README.md, handover.md, docs/architecture/repository_structure.md, and the current release
documents as the as-built reference.

## Historical documents

Several weekly documents deliberately preserve the plan, scope, or non-goals that existed at their
milestone:

- References to Streamlit describe an earlier direction that React replaced.
- References to Streamable HTTP or network MCP describe deferred proposals. They do not describe the
  v1.0.0 production transport.
- The Week 9 ADR describes the Agent boundary before the Week 10 claim guardrail and Week 11 browser
  delivery were added.
- Historical evidence and review packets remain immutable. New documentation may explain their
  context, but must not rewrite their hashes, metrics, labels, or conclusions.

These documents remain useful for provenance and architecture decisions. They must not be read as a
request to reintroduce Streamlit, network MCP, or a different deployment model.

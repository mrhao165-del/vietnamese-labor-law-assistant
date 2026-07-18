---
name: mcp-component-builder
description: Build or review a real stdio MCP component that adapts an existing Vietnamese Labor Law AI Assistant core capability using the Week 7 and Week 8 patterns. Use for scoped MCP tools, schemas, servers, clients, and protocol verification. Do not use for placeholder MCP features, new legal business logic in adapters, or arbitrary file, shell, or network access.
---

# MCP Component Builder

Read Week 7 and Week 8 documentation before changing an MCP component. Build only an adapter around an
existing framework-neutral core capability.

1. Put rules and reusable contracts in an appropriate `src/...` area; limit MCP code to transport,
   Pydantic validation, public mapping, and error translation.
2. Use official `mcp` SDK stdio, exact static tool allowlists, versioned Pydantic envelopes, and stable
   public error codes.
3. Add a reusable production stdio client, unit tests, official-SDK protocol test, and Inspector CLI
   verification of the production server.
4. Log diagnostics only server-side/stderr. Never return traceback, absolute path, secret, or raw backend
   payload on protocol stdout.
5. Reject caller-selected paths, shells, subprocesses, URLs, network fetches, vectors, and dynamic tool
   registration. Do not add LLM reasoning to the deterministic calculator.

If no existing core capability supports a tool, stop for an architectural decision rather than scaffolding.

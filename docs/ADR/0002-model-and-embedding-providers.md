# ADR-0002: Model and embedding providers

- **Status:** Accepted
- **Date:** 2026-10-28

## Context

The spec requires a narrow `ModelClient` interface, real provider SDKs behind it, deterministic stubs for CI, and a configurable, version-pinned embedding backend whose vector dimension is not hard-coded.

## Decision

- **Chat/tool model:** Anthropic Claude via the official `anthropic` Python SDK (owner choice). Default model `claude-opus-5-5` at effort `medium` (both configurable: `LLM_MODEL`, `LLM_EFFORT`; `claude-sonnet-5-5` is the cheaper option). Requests use the manual tool loop with `strict` tool schemas, `tool_choice: auto` (forced tool choice is rejected by current models), top-level prompt caching, and the server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`) unless `LLM_REFUSAL_FALLBACK=false`. Usage (input/output tokens) comes from the provider response; cost is estimated from a configurable price table and labelled as an estimate.
- **Stub model:** `StubModelClient` replays scripted tool decisions. Used by unit/integration tests and CI. It is never selectable in `public_demo` mode.
- **Embeddings:** Anthropic has no embedding endpoint, so embeddings use `fastembed` (ONNX Runtime, CPU) with `BAAI/bge-small-en-v1.5` by default. Benefits: no API key, no source code sent to a third party during indexing, deterministic output for a pinned model version.
- **Test embedder:** `hashing` — a deterministic feature-hashing embedder for tests where downloading a model is undesirable. Results produced with it are not used in published retrieval metrics.
- Each `repo_snapshot` stores `embed_model` and `embed_dim`. The `source_chunks.embedding` column is an unconstrained `vector`; queries filter by snapshot so dimensions never mix. An HNSW index can be added per dimension when data volume warrants (§7.2).

## Consequences

- Indexing works offline after the first model download (cached in a volume).
- Switching embedding model requires re-indexing into a new snapshot; old snapshots remain queryable with their own model.

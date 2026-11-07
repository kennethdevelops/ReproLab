# ADR-0003: Chunking and vector index

- **Status:** Accepted
- **Date:** 2026-11-06

## Context

The implementation plan calls for syntax-aware chunking via Tree-sitter for TS/JS/Python, with a line-window fallback and heading-aware Markdown. Citations must be checkable: every chunk has to map to exact 1-based line ranges of the original file. The project is a portfolio-scale system indexing small repositories (the demo store has well under a thousand chunks).

## Decision

- **Chunker:** a line-preserving boundary chunker (`indexing/chunker.py`, version `boundary-lines-v1`). Top-level declarations are detected per language with anchored regexes (TS/JS, Python, C#, SQL); leading comments and decorators stay with their declaration; declarations longer than 80 lines are split into overlapping windows (10-line overlap); Markdown splits at headings. Chunk content is always exactly the recorded lines.
- Tree-sitter is not used. It adds native grammar packages per language for a gain (nested-scope precision) that does not change retrieval quality measurably at this repository size. The `CHUNKER_VERSION` is stored on each snapshot, so a Tree-sitter chunker can be added later and re-indexing creates a new snapshot without mixing chunk styles.
- **Vector index:** no ANN (HNSW) index. The `embedding` column has no fixed dimension because it depends on the configured embedding model, and pgvector indexes need one. Every vector query is filtered by snapshot, so it is an exact scan over a few hundred rows, which is fast and gives exact recall.
- **Lexical ranking:** PostgreSQL full-text search (`ts_rank_cd`, GIN index) plus literal matching of identifier-like query tokens. A chunk whose symbol equals the identifier, or whose file path contains it, gets a boost so the defining code outranks call sites.

## Consequences

- Regex boundaries can misdetect unusual formatting (for example, a declaration inside a template string at column 0). The failure mode is a less tidy chunk boundary, never a wrong line range.
- Indexing large repositories would need an HNSW index per embedding dimension (a partial index per model, or a fixed-dimension column) before vector search stays fast.

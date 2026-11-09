"""Scoped repository retrieval.

Every function takes one snapshot and filters by it; callers resolve the snapshot from the
project, so no query can mix projects or snapshots.

Hybrid fusion is Reciprocal Rank Fusion: ``score(d) = sum_s w_s / (k + rank_s(d))`` over the
lexical and vector rankings, with ``k = settings.retrieval_rrf_k`` (60) and equal weights (1.0).
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import Select, String, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from reprolab.db.models import RepoSnapshot, RetrievalEvent, SourceChunk, SourceDocument
from reprolab.indexing.embeddings import Embedder

Strategy = Literal["lexical", "vector", "hybrid"]
RRF_WEIGHTS = {"lexical": 1.0, "vector": 1.0}
EXCERPT_LINES = 40
MAX_READ_LINES = 200

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*|\d+")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*(?:[A-Z_.][\w$]+)+|/[\w/.-]+")
_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class RetrievalError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Hit:
    chunk_id: uuid.UUID
    path: str
    kind: str
    start_line: int
    end_line: int
    symbol: str | None
    excerpt: str
    score: float
    ranks: dict[str, int] = field(default_factory=dict)
    citation_url: str | None = None


@dataclass
class SearchResult:
    snapshot_id: uuid.UUID
    commit_sha: str
    strategy: str
    query: str
    hits: list[Hit]
    timing_ms: int
    candidates: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def tsquery_terms(query: str) -> list[str]:
    words = set()
    for w in _WORD.findall(query):
        words.add(w.lower())
        words.update(p.lower() for p in _SPLIT.split(w))
    return sorted(w for w in words if len(w) > 1)[:40]


def literal_terms(query: str) -> list[str]:
    """Identifier-, route- or path-like tokens to match literally (e.g. `restoreCoupon`)."""
    return [t for t in _IDENT.findall(query) if len(t) >= 4][:5]


def _scoped(stmt: Select[Any], snapshot_id: uuid.UUID, kinds: list[str] | None) -> Select[Any]:
    stmt = stmt.where(SourceChunk.snapshot_id == snapshot_id)
    if kinds:
        stmt = stmt.where(SourceDocument.kind.in_(kinds))
    return stmt


def lexical_ranking(
    db: Session, snapshot_id: uuid.UUID, query: str, limit: int, kinds: list[str] | None = None
) -> list[tuple[uuid.UUID, float]]:
    terms = tsquery_terms(query)
    literals = literal_terms(query)
    if not terms and not literals:
        return []
    # Terms are restricted to [a-z0-9], so joining them into tsquery syntax is injection-safe;
    # the string is still passed as a bound parameter.
    score: Any = literal(0.0)
    matches: list[Any] = []
    if terms:
        tsq = func.to_tsquery("english", " | ".join(terms))
        score = func.ts_rank_cd(SourceChunk.search_vector, tsq, 1)
        matches.append(SourceChunk.search_vector.op("@@")(tsq))
    for lit in literals:
        found = func.strpos(SourceChunk.content, cast(literal(lit), String)) > 0
        score = score + case((found, 1.0), else_=0.0)
        # The defining chunk/file should outrank call sites: boost symbol and path matches.
        score = score + case((SourceChunk.symbol == lit, 2.0), else_=0.0)
        in_path = func.strpos(SourceDocument.path, cast(literal(lit), String)) > 0
        score = score + case((in_path, 1.0), else_=0.0)
        matches.append(found)
    score = score.label("score")
    stmt = select(SourceChunk.id, score).join(
        SourceDocument, SourceDocument.id == SourceChunk.document_id
    )
    stmt = (
        _scoped(stmt, snapshot_id, kinds)
        .where(or_(*matches))
        .order_by(score.desc(), SourceChunk.id)
        .limit(limit)
    )
    return [(cid, float(s)) for cid, s in db.execute(stmt)]


def vector_ranking(
    db: Session,
    snapshot: RepoSnapshot,
    query: str,
    embedder: Embedder,
    limit: int,
    kinds: list[str] | None = None,
) -> list[tuple[uuid.UUID, float]]:
    if embedder.model_id != snapshot.embed_model or embedder.dim != snapshot.embed_dim:
        raise RetrievalError("EMBEDDING_MISMATCH", f"Snapshot was embedded with {snapshot.embed_model}; configured embedder is {embedder.model_id}.")  # fmt: skip
    qvec = embedder.embed_query(query)
    distance = SourceChunk.embedding.cosine_distance(qvec).label("distance")
    stmt = select(SourceChunk.id, distance).join(
        SourceDocument, SourceDocument.id == SourceChunk.document_id
    )
    stmt = _scoped(stmt, snapshot.id, kinds).where(SourceChunk.embedding.is_not(None))
    stmt = stmt.order_by(distance, SourceChunk.id).limit(limit)
    return [(cid, 1.0 - float(d)) for cid, d in db.execute(stmt)]


def rrf(
    rankings: dict[str, list[tuple[uuid.UUID, float]]], k: int
) -> list[tuple[uuid.UUID, float, dict[str, int]]]:
    scores: dict[uuid.UUID, float] = {}
    ranks: dict[uuid.UUID, dict[str, int]] = {}
    for name, ranking in rankings.items():
        weight = RRF_WEIGHTS.get(name, 1.0)
        for position, (cid, _score) in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + weight / (k + position)
            ranks.setdefault(cid, {})[name] = position
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return [(cid, s, ranks[cid]) for cid, s in ordered]


def search(
    db: Session,
    snapshot: RepoSnapshot,
    query: str,
    strategy: Strategy,
    embedder: Embedder | None,
    top_k: int = 6,
    candidates: int = 30,
    rrf_k: int = 60,
    kinds: list[str] | None = None,
    investigation_id: uuid.UUID | None = None,
) -> SearchResult:
    if snapshot.status != "ready":
        raise RetrievalError("SNAPSHOT_NOT_READY", "The repository index is not ready.")
    query = query.strip()[:500]
    if not query:
        raise RetrievalError("EMPTY_QUERY", "Query must not be empty.")
    started = time.perf_counter()
    rankings: dict[str, list[tuple[uuid.UUID, float]]] = {}
    if strategy in ("lexical", "hybrid"):
        rankings["lexical"] = lexical_ranking(db, snapshot.id, query, candidates, kinds)
    if strategy in ("vector", "hybrid"):
        if embedder is None:
            raise RetrievalError("EMBEDDER_UNAVAILABLE", "No embedding model is configured.")
        rankings["vector"] = vector_ranking(db, snapshot, query, embedder, candidates, kinds)

    if strategy == "hybrid":
        fused = rrf(rankings, rrf_k)[:top_k]
    else:
        ranking = rankings[strategy][:top_k]
        fused = [(cid, s, {strategy: i}) for i, (cid, s) in enumerate(ranking, start=1)]

    ids = [cid for cid, _, _ in fused]
    rows = {
        c.id: (c, d)
        for c, d in db.execute(
            select(SourceChunk, SourceDocument)
            .join(SourceDocument, SourceDocument.id == SourceChunk.document_id)
            .where(SourceChunk.snapshot_id == snapshot.id, SourceChunk.id.in_(ids))
        ).all()
    }
    hits = []
    for cid, score, ranks in fused:
        chunk, doc = rows[cid]
        excerpt = "\n".join(chunk.content.splitlines()[:EXCERPT_LINES])
        url = None
        if snapshot.citation_base_url:
            url = f"{snapshot.citation_base_url}{doc.path}#L{chunk.start_line}-L{chunk.end_line}"
        hits.append(Hit(cid, doc.path, doc.kind, chunk.start_line, chunk.end_line, chunk.symbol,
                        excerpt, round(score, 6), ranks, url))  # fmt: skip
    timing = int((time.perf_counter() - started) * 1000)
    db.add(RetrievalEvent(
        investigation_id=investigation_id, snapshot_id=snapshot.id, query=query, mode=strategy,
        chunk_ids=[str(i) for i in ids],
        rankings={name: [[str(cid), round(s, 6)] for cid, s in r] for name, r in rankings.items()},
        timing_ms=timing,
    ))  # fmt: skip
    candidates_out = {
        name: [
            {"chunk_id": str(cid), "rank": i, "score": round(s, 6)}
            for i, (cid, s) in enumerate(r, 1)
        ]
        for name, r in rankings.items()
    }
    return SearchResult(
        snapshot.id, snapshot.commit_sha, strategy, query, hits, timing, candidates_out
    )


@dataclass
class SourceExcerpt:
    path: str
    start_line: int
    end_line: int
    total_lines: int
    content: str
    commit_sha: str


def read_source(
    db: Session, snapshot: RepoSnapshot, path: str, start_line: int, end_line: int
) -> SourceExcerpt:
    """Bounded read of an indexed document. Unindexed paths do not exist from the caller's view."""
    doc = db.scalars(
        select(SourceDocument).where(
            SourceDocument.snapshot_id == snapshot.id, SourceDocument.path == path
        )
    ).first()
    if doc is None:
        raise RetrievalError("SOURCE_NOT_FOUND", "No indexed file at that path in this snapshot.")
    lines = doc.content.splitlines()
    start = max(1, start_line)
    end = min(len(lines), end_line, start + MAX_READ_LINES - 1)
    if start > len(lines) or end < start:
        raise RetrievalError("INVALID_RANGE", f"{path} has {len(lines)} lines.")
    return SourceExcerpt(
        path, start, end, len(lines), "\n".join(lines[start - 1 : end]), snapshot.commit_sha
    )


def current_snapshot(db: Session, project_id: uuid.UUID) -> RepoSnapshot | None:
    return db.scalars(
        select(RepoSnapshot)
        .where(RepoSnapshot.project_id == project_id, RepoSnapshot.status == "ready")
        .order_by(RepoSnapshot.indexed_at.desc())
        .limit(1)
    ).first()

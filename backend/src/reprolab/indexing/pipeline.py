"""Indexing job: snapshot source -> documents -> chunks -> embeddings -> ready.

Documents and chunks are written in a single transaction together with the ``ready`` status, so
a half-indexed snapshot is never visible. Progress is reported in separate short transactions.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from reprolab.config.settings import Settings, get_settings
from reprolab.db.enums import IndexStatus
from reprolab.db.models import Project, RepoSnapshot, SourceChunk, SourceDocument
from reprolab.db.session import session_scope
from reprolab.indexing.chunker import CHUNKER_VERSION, Chunk, chunk_text, search_text
from reprolab.indexing.embeddings import Embedder, get_embedder
from reprolab.indexing.paths import (
    classify,
    language_for,
    looks_binary_or_generated,
    refusal_reason,
)
from reprolab.indexing.sources import (
    LocalSnapshotSource,
    ResolvedSnapshot,
    SnapshotSource,
    SourceError,
)

log = logging.getLogger(__name__)

EMBED_BATCH = 64
LOCAL_PREFIX = "local://"


def source_for_project(project: Project, settings: Settings) -> SnapshotSource:
    """Snapshot source configured by the operator for a project. Anonymous users never choose."""
    url = project.repo_url
    if not url:
        raise SourceError("NO_REPOSITORY", "This project has no repository configured.")
    if url.startswith(LOCAL_PREFIX):
        return LocalSnapshotSource(settings.snapshots_dir, url[len(LOCAL_PREFIX) :],
                                   settings.max_index_file_bytes, settings.max_index_files)  # fmt: skip
    from reprolab.github.client import GitHubSource

    token = settings.github_token.get_secret_value() if settings.github_token else None
    return GitHubSource(url, settings.github_api_url, token, settings.max_index_files,
                        settings.max_index_file_bytes)  # fmt: skip


@dataclass
class PreparedDocument:
    path: str
    kind: str
    language: str
    content: str
    chunks: list[Chunk]


def prepare_documents(
    source: SnapshotSource, snapshot: ResolvedSnapshot, settings: Settings
) -> list[PreparedDocument]:
    docs: list[PreparedDocument] = []
    total_chunks = 0
    for f in source.files(snapshot):
        # Defence in depth: re-check rules even though sources already filter.
        if refusal_reason(f.path, len(f.text.encode("utf-8")), settings.max_index_file_bytes):
            snapshot.excluded["refused_by_pipeline"] = snapshot.excluded.get("refused_by_pipeline", 0) + 1  # fmt: skip
            continue
        if looks_binary_or_generated(f.text):
            snapshot.excluded["binary_or_generated"] = snapshot.excluded.get("binary_or_generated", 0) + 1  # fmt: skip
            continue
        language = language_for(f.path) or "text"
        chunks = chunk_text(f.text, language)
        if total_chunks + len(chunks) > settings.max_index_chunks:
            snapshot.excluded["chunk_quota"] = snapshot.excluded.get("chunk_quota", 0) + 1
            continue
        total_chunks += len(chunks)
        docs.append(PreparedDocument(f.path, classify(f.path), language, f.text, chunks))
    return docs


def verify_citations(docs: list[PreparedDocument]) -> None:
    """Every chunk must be exactly its cited lines of the stored document."""
    for doc in docs:
        lines = doc.content.splitlines()
        for c in doc.chunks:
            if "\n".join(lines[c.start_line - 1 : c.end_line]) != c.content:
                raise SourceError("CITATION_MISMATCH", f"Chunk lines do not match {doc.path}:{c.start_line}-{c.end_line}.")  # fmt: skip


def _update(snapshot_id: uuid.UUID, **fields: Any) -> None:
    with session_scope() as db:
        snap = db.get(RepoSnapshot, snapshot_id)
        assert snap is not None
        for k, v in fields.items():
            setattr(snap, k, v)


def _reusable_embeddings(
    project_id: uuid.UUID, embed_model: str, hashes: set[str]
) -> dict[str, list[float]]:
    if not hashes:
        return {}
    with session_scope() as db:
        rows = db.execute(
            select(SourceChunk.content_hash, SourceChunk.embedding)
            .join(RepoSnapshot, RepoSnapshot.id == SourceChunk.snapshot_id)
            .where(
                RepoSnapshot.project_id == project_id,
                RepoSnapshot.embed_model == embed_model,
                RepoSnapshot.status == IndexStatus.READY.value,
                SourceChunk.content_hash.in_(hashes),
                SourceChunk.embedding.is_not(None),
            )
        ).all()
        return {h: list(e) for h, e in rows if e is not None}


def index_snapshot(
    snapshot_id: uuid.UUID,
    source_factory: Callable[[Project, Settings], SnapshotSource] = source_for_project,
    embedder: Embedder | None = None,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    with session_scope() as db:
        snap = db.get(RepoSnapshot, snapshot_id)
        if snap is None:
            return "missing"
        if snap.status in (IndexStatus.READY.value, IndexStatus.CANCELLED.value):
            return snap.status
        project = db.get(Project, snap.project_id)
        assert project is not None
        db.expunge(project)
        resolved = ResolvedSnapshot(
            snap.commit_sha, snap.ref, snap.source_kind, snap.citation_base_url
        )
        snap.status = IndexStatus.FETCHING.value
        snap.error = None
        embed_model = snap.embed_model

    try:
        embedder = embedder or get_embedder(settings)
        if embedder.model_id != embed_model:
            raise SourceError("EMBEDDING_MISMATCH", f"Configured embedder {embedder.model_id} differs from {embed_model}.")  # fmt: skip
        source = source_factory(project, settings)
        docs = prepare_documents(source, resolved, settings)
        _update(snapshot_id, status=IndexStatus.PARSING.value,
                progress={"documents": len(docs), "chunks": sum(len(d.chunks) for d in docs),
                          "excluded": resolved.excluded})  # fmt: skip
        verify_citations(docs)

        _update(snapshot_id, status=IndexStatus.EMBEDDING.value)
        all_chunks = [c for d in docs for c in d.chunks]
        reused = _reusable_embeddings(project.id, embed_model, {c.content_hash for c in all_chunks})
        to_embed = [c for c in all_chunks if c.content_hash not in reused]
        vectors: dict[str, list[float]] = dict(reused)
        for i in range(0, len(to_embed), EMBED_BATCH):
            batch = to_embed[i : i + EMBED_BATCH]
            texts = [f"{c.symbol or ''}\n{c.content}" for c in batch]
            for c, v in zip(batch, embedder.embed_documents(texts), strict=True):
                vectors[c.content_hash] = v
        dims = {len(v) for v in vectors.values()}
        if len(dims) > 1 or (dims and dims != {embedder.dim}):
            raise SourceError("EMBEDDING_DIMENSION", "Embedding dimensions are inconsistent.")

        with session_scope() as db:
            for d in docs:
                doc = SourceDocument(snapshot_id=snapshot_id, path=d.path, kind=d.kind,
                                     language=d.language, content=d.content,
                                     content_sha=hashlib.sha256(d.content.encode("utf-8")).hexdigest(),
                                     line_count=len(d.content.splitlines()), meta={})  # fmt: skip
                db.add(doc)
                db.flush()
                for c in d.chunks:
                    db.add(SourceChunk(document_id=doc.id, snapshot_id=snapshot_id,
                                       start_line=c.start_line, end_line=c.end_line, symbol=c.symbol,
                                       content=c.content, content_hash=c.content_hash,
                                       search_text=search_text(d.path, c.symbol, c.content),
                                       embedding=vectors[c.content_hash]))  # fmt: skip
            snap = db.get(RepoSnapshot, snapshot_id)
            assert snap is not None
            snap.status = IndexStatus.READY.value
            snap.embed_dim = embedder.dim
            snap.indexed_at = datetime.now(UTC)
            snap.progress = {"documents": len(docs), "chunks": len(all_chunks),
                             "embedded": len(to_embed), "reused_embeddings": len(all_chunks) - len(to_embed),
                             "excluded": resolved.excluded, "chunker": CHUNKER_VERSION}  # fmt: skip
        return IndexStatus.READY.value
    except SourceError as exc:
        _update(snapshot_id, status=IndexStatus.FAILED.value, error=f"{exc.code}: {exc}")
        return IndexStatus.FAILED.value
    except Exception as exc:
        log.exception("indexing_crashed")
        _update(snapshot_id, status=IndexStatus.FAILED.value, error=f"Internal error ({type(exc).__name__}).")  # fmt: skip
        return IndexStatus.FAILED.value

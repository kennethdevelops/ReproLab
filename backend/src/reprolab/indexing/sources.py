"""Snapshot sources: where indexable files come from.

* ``LocalSnapshotSource`` reads an operator-exported snapshot directory
  (``<snapshots_dir>/<name>/<commit_sha>/``) created by ``local_snapshot export``. Projects refer
  to it as ``local://<name>``; anonymous callers can never supply a path.
* ``GitHubSource`` (``reprolab.github.client``) reads a public repository at a pinned SHA.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from reprolab.indexing.paths import normalise_path, refusal_reason

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
MANIFEST = "manifest.json"


class SourceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SourceFile:
    path: str
    text: str


@dataclass
class ResolvedSnapshot:
    commit_sha: str
    ref: str | None
    source_kind: str
    # Canonical URL prefix for citations at this commit, e.g. a GitHub blob URL. None for local.
    blob_url_prefix: str | None = None
    excluded: dict[str, int] = field(default_factory=dict)


class SnapshotSource(Protocol):
    def resolve(self, ref: str | None) -> ResolvedSnapshot: ...

    def files(self, snapshot: ResolvedSnapshot) -> Iterator[SourceFile]: ...


class LocalSnapshotSource:
    def __init__(self, snapshots_dir: Path, name: str, max_file_bytes: int, max_files: int) -> None:
        if not NAME_RE.match(name):
            raise SourceError("INVALID_SOURCE", "Invalid local snapshot name.")
        self.base = (snapshots_dir / name).resolve()
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files

    def resolve(self, ref: str | None) -> ResolvedSnapshot:
        if ref is None:
            current = self.base / "CURRENT"
            if not current.is_file():
                raise SourceError("SNAPSHOT_NOT_FOUND", "No exported local snapshot found.")
            ref = current.read_text(encoding="utf-8").strip()
        if not SHA_RE.match(ref):
            raise SourceError("INVALID_REF", "Local snapshots are addressed by full commit SHA.")
        manifest_path = self.base / ref / MANIFEST
        if not manifest_path.is_file():
            raise SourceError("SNAPSHOT_NOT_FOUND", f"Snapshot {ref[:12]} has not been exported.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("commit_sha") != ref:
            raise SourceError("SNAPSHOT_CORRUPT", "Snapshot manifest does not match its directory.")
        return ResolvedSnapshot(ref, manifest.get("ref"), "local_snapshot")

    def files(self, snapshot: ResolvedSnapshot) -> Iterator[SourceFile]:
        root = (self.base / snapshot.commit_sha / "files").resolve()
        manifest = json.loads((self.base / snapshot.commit_sha / MANIFEST).read_text("utf-8"))
        count = 0
        for rel in manifest["files"]:
            norm = normalise_path(rel)
            target = (root / rel).resolve() if norm else None
            if norm is None or target is None or not target.is_relative_to(root):
                snapshot.excluded["invalid_path"] = snapshot.excluded.get("invalid_path", 0) + 1
                continue
            if target.is_symlink() or not target.is_file():
                snapshot.excluded["missing"] = snapshot.excluded.get("missing", 0) + 1
                continue
            reason = refusal_reason(norm, target.stat().st_size, self.max_file_bytes)
            if reason is None and count >= self.max_files:
                reason = "file_quota"
            if reason:
                snapshot.excluded[reason] = snapshot.excluded.get(reason, 0) + 1
                continue
            count += 1
            yield SourceFile(norm, target.read_text(encoding="utf-8", errors="replace"))

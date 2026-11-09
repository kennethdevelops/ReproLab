"""Private artifact storage on the local filesystem, addressed by opaque keys (spec §17.4).

Keys are generated server-side (``<investigation_id>/<uuid>.<ext>``); no user input ever becomes
part of a path, and reads re-check that the resolved path stays under the root.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

ALLOWED_EXTENSIONS = {"png": "image/png", "zip": "application/zip", "json": "application/json",
                      "txt": "text/plain; charset=utf-8", "md": "text/markdown; charset=utf-8",
                      "ts": "text/plain; charset=utf-8"}  # fmt: skip
MAX_ARTIFACT_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class StoredArtifact:
    storage_key: str
    sha256: str
    size: int
    mime_type: str


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def new_key(self, investigation_id: uuid.UUID, ext: str) -> str:
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"unsupported artifact type {ext}")
        return f"{investigation_id}/{uuid.uuid4().hex}.{ext}"

    def path_for(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("artifact key escapes storage root")
        return path

    def put_bytes(self, investigation_id: uuid.UUID, ext: str, data: bytes) -> StoredArtifact:
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ValueError("artifact exceeds maximum size")
        key = self.new_key(investigation_id, ext)
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredArtifact(
            key, hashlib.sha256(data).hexdigest(), len(data), ALLOWED_EXTENSIONS[ext]
        )

    def adopt_file(self, investigation_id: uuid.UUID, ext: str, source: Path) -> StoredArtifact:
        """Move a file produced elsewhere (e.g. a Playwright trace) into the store."""
        data = source.read_bytes()
        stored = self.put_bytes(investigation_id, ext, data)
        source.unlink(missing_ok=True)
        return stored

    def scratch_path(self, investigation_id: uuid.UUID, name: str) -> Path:
        path = self.root / str(investigation_id) / "tmp" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

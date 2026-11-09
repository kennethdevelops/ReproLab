"""Read-only public GitHub source at a pinned commit.

Only ``https://github.com/<owner>/<repo>`` URLs are accepted. The ref is resolved to a full SHA
through the REST API; the tree is listed once, filtered by ``indexing.paths`` and quotas, and
blobs are fetched from the API by SHA. Repository content is treated as text only.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Iterator
from urllib.parse import urlsplit

import httpx

from reprolab.indexing.paths import refusal_reason
from reprolab.indexing.sources import SHA_RE, ResolvedSnapshot, SourceError, SourceFile

_SEGMENT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})$")
_REF = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def parse_repo_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) for a canonical public GitHub URL, else raise SourceError."""
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or parts.netloc.lower() != "github.com":
        raise SourceError("UNSUPPORTED_REPOSITORY", "Only https://github.com/<owner>/<repo> URLs are supported.")  # fmt: skip
    if parts.query or parts.fragment or parts.username or parts.password or parts.port:
        raise SourceError("UNSUPPORTED_REPOSITORY", "Repository URL must not contain a query, fragment or credentials.")  # fmt: skip
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) != 2:
        raise SourceError("UNSUPPORTED_REPOSITORY", "Repository URL must be exactly https://github.com/<owner>/<repo>.")  # fmt: skip
    owner, repo = segments
    repo = repo.removesuffix(".git")
    if not (_SEGMENT.match(owner) and _SEGMENT.match(repo)) or ".." in owner + repo:
        raise SourceError("UNSUPPORTED_REPOSITORY", "Invalid owner or repository name.")
    return owner, repo


class GitHubSource:
    def __init__(
        self,
        repo_url: str,
        api_url: str = "https://api.github.com",
        token: str | None = None,
        max_files: int = 2000,
        max_file_bytes: int = 200_000,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.owner, self.repo = parse_repo_url(repo_url)
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "ReproLab-indexer"}  # fmt: skip
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(base_url=api_url, headers=headers, timeout=20.0,
                                   transport=transport, follow_redirects=False)  # fmt: skip
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes

    def _get(self, path: str) -> dict:  # type: ignore[type-arg]
        response = self.client.get(path)
        if response.status_code == 404:
            raise SourceError("REPOSITORY_NOT_FOUND", "Repository or ref not found (private repositories are not supported).")  # fmt: skip
        if (
            response.status_code in (403, 429)
            and response.headers.get("x-ratelimit-remaining") == "0"
        ):
            raise SourceError("GITHUB_RATE_LIMITED", "GitHub API rate limit reached; try later or configure GITHUB_TOKEN.")  # fmt: skip
        if response.status_code != 200:
            raise SourceError("GITHUB_ERROR", f"GitHub API returned HTTP {response.status_code}.")
        data = response.json()
        if not isinstance(data, dict):
            raise SourceError("GITHUB_ERROR", "Unexpected GitHub API response.")
        return data

    def resolve(self, ref: str | None) -> ResolvedSnapshot:
        base = f"/repos/{self.owner}/{self.repo}"
        if ref is None:
            ref = str(self._get(base).get("default_branch") or "main")
        if not _REF.match(ref) or ".." in ref:
            raise SourceError("INVALID_REF", "Invalid ref.")
        sha = str(self._get(f"{base}/commits/{ref}").get("sha", ""))
        if not SHA_RE.match(sha):
            raise SourceError("GITHUB_ERROR", "Could not resolve ref to a commit SHA.")
        prefix = f"https://github.com/{self.owner}/{self.repo}/blob/{sha}/"
        return ResolvedSnapshot(sha, ref, "github", blob_url_prefix=prefix)

    def files(self, snapshot: ResolvedSnapshot) -> Iterator[SourceFile]:
        base = f"/repos/{self.owner}/{self.repo}"
        tree = self._get(f"{base}/git/trees/{snapshot.commit_sha}?recursive=1")
        if tree.get("truncated"):
            snapshot.excluded["tree_truncated"] = 1
        count = 0
        for entry in tree.get("tree", []):
            if entry.get("type") != "blob":
                continue
            path = str(entry.get("path", ""))
            reason = "symlink" if entry.get("mode") == "120000" else None
            reason = reason or refusal_reason(
                path, int(entry.get("size") or 0), self.max_file_bytes
            )
            if reason is None and count >= self.max_files:
                reason = "file_quota"
            if reason:
                snapshot.excluded[reason] = snapshot.excluded.get(reason, 0) + 1
                continue
            blob = self._get(f"{base}/git/blobs/{entry['sha']}")
            if blob.get("encoding") != "base64":
                snapshot.excluded["unsupported_encoding"] = snapshot.excluded.get("unsupported_encoding", 0) + 1  # fmt: skip
                continue
            raw = base64.b64decode(str(blob.get("content", "")))
            count += 1
            yield SourceFile(path, raw.decode("utf-8", errors="replace"))

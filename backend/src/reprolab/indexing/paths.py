"""Path, type and size rules for what may be indexed.

These checks run in the exporter, the GitHub adapter and again in the indexing pipeline, so a
snapshot directory that somehow contains a forbidden file still never reaches the index.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

# Any path segment matching one of these is refused, whatever the source.
FORBIDDEN_SEGMENTS = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        ".next",
        "coverage",
        "__pycache__",
        ".venv",
        "venv",
        # Benchmark answer keys and fixture variants (never visible to the agent).
        "ground-truth",
        "fixtures",
        "oracles",
    }
)

FORBIDDEN_NAME_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^\.env",
        r"\.(pem|key|p12|pfx|crt|der|kdbx)$",
        r"^id_(rsa|ed25519|ecdsa)",
        r"secret",
        r"credential",
        r"\.min\.(js|css)$",
        r"\.map$",
        r"^(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|uv\.lock|poetry\.lock)$",
    )
]

LANGUAGE_BY_SUFFIX = {
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".py": "python",
    ".cs": "csharp",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
    ".md": "markdown",
    ".txt": "text",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}

PROSE_LANGUAGES = {"markdown", "text"}
CONFIG_LANGUAGES = {"json", "yaml", "toml"}


def normalise_path(path: str) -> str | None:
    """Canonical relative POSIX path, or None for absolute/escaping/odd paths."""
    if not path or "\\" in path or "\x00" in path or any(ord(c) < 32 for c in path):
        return None
    p = PurePosixPath(path)
    if p.is_absolute() or any(part in ("..", ".", "") for part in p.parts):
        return None
    return p.as_posix()


def refusal_reason(path: str, size: int | None = None, max_bytes: int = 200_000) -> str | None:
    """Why ``path`` must not be indexed, or None when it is allowed."""
    norm = normalise_path(path)
    if norm is None:
        return "invalid_path"
    parts = PurePosixPath(norm).parts
    if any(part.lower() in FORBIDDEN_SEGMENTS for part in parts[:-1]):
        return "excluded_directory"
    name = parts[-1]
    if any(rx.search(name) for rx in FORBIDDEN_NAME_PATTERNS):
        return "excluded_file"
    if language_for(norm) is None:
        return "unsupported_type"
    if size is not None and size > max_bytes:
        return "too_large"
    return None


def language_for(path: str) -> str | None:
    return LANGUAGE_BY_SUFFIX.get(PurePosixPath(path).suffix.lower())


def classify(path: str) -> str:
    """Document kind: source | test | documentation | configuration."""
    lower = path.lower()
    language = language_for(path)
    if language in PROSE_LANGUAGES:
        return "documentation"
    if re.search(
        r"(^|/)(tests?|__tests__|spec)/|\.(test|spec)\.[a-z]+$|(^|/)test_[^/]+\.py$", lower
    ):
        return "test"
    if language in CONFIG_LANGUAGES:
        return "configuration"
    return "source"


def looks_binary_or_generated(text: str) -> bool:
    if "\x00" in text:
        return True
    lines = text.splitlines() or [""]
    # Minified/generated: very long average line length.
    return len(text) > 2000 and len(text) / len(lines) > 400

"""Redaction of secrets and personal data before anything is persisted or shown."""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_HEADERS = frozenset(
    {"authorization", "cookie", "set-cookie", "proxy-authorization", "x-api-key", "x-admin-token"}
)
SENSITIVE_KEYS = re.compile(r"(pass(word)?|secret|token|api[_-]?key|authorization|cookie)", re.I)

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{8,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._\-~+/]+=*", re.I), "Bearer [REDACTED]"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
        "[REDACTED_JWT]",
    ),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
]


def redact_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        k: ("[REDACTED]" if k.lower() in SENSITIVE_HEADERS else redact_text(v))
        for k, v in headers.items()
    }


def redact_value(value: Any) -> Any:
    """Recursively redact a JSON-like value."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if SENSITIVE_KEYS.search(str(k)) else redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 15] + "…[truncated]"

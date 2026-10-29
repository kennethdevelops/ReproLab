"""Browser navigation policy (spec §12.2). Enforced in code on every request, not in prompts.

A request is allowed only when its exact origin (scheme, host, port) is in the investigation's
allowlist. Independently of the allowlist, cloud metadata and link-local destinations are always
refused, and non-HTTP schemes never reach the network.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})
# Schemes Chromium uses internally for the page itself; these never leave the browser.
INTERNAL_SCHEMES = frozenset({"about", "blob"})
MAX_URL_LENGTH = 2048

Resolver = Callable[[str], list[str]]


class PolicyViolation(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def normalise_origin(url: str) -> str:
    """Return ``scheme://host[:port]`` with default ports removed and the host lower-cased."""
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES or not parts.hostname:
        raise PolicyViolation("INVALID_ORIGIN", f"Not an http(s) origin: {url!r}")
    host = parts.hostname.lower()
    port = parts.port
    default = 443 if parts.scheme == "https" else 80
    netloc = host if port in (None, default) else f"{host}:{port}"
    if ":" in host and not host.startswith("["):  # IPv6 literal
        netloc = f"[{host}]" if port in (None, default) else f"[{host}]:{port}"
    return f"{parts.scheme}://{netloc}"


def _default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({str(info[4][0]) for info in infos})


def _is_always_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # Link-local covers 169.254.169.254 (AWS/GCP/Azure metadata) and fe80::/10.
    return ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved


def _is_internal_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip.is_private or ip.is_loopback or _is_always_forbidden_ip(ip)


@dataclass
class OriginPolicy:
    """Allowlist of exact origins for one investigation.

    ``allow_internal_ips``: operator-configured origins (the demo target on the Docker network,
    explicitly listed local dev servers) legitimately resolve to private addresses. When False
    (hosted mode for non-operator origins), any private/loopback resolution is refused, which
    also defends against DNS rebinding of an allowlisted public hostname.
    """

    allowed_origins: frozenset[str]
    allow_internal_ips: bool = True
    resolver: Resolver = field(default=_default_resolver, repr=False)

    @classmethod
    def from_origins(cls, origins: Iterable[str], **kwargs: object) -> OriginPolicy:
        return cls(allowed_origins=frozenset(normalise_origin(o) for o in origins), **kwargs)  # type: ignore[arg-type]

    def check_url(self, url: str) -> str:
        """Validate an absolute URL; returns the normalised origin or raises PolicyViolation."""
        if len(url) > MAX_URL_LENGTH:
            raise PolicyViolation("URL_TOO_LONG", "URL exceeds the maximum length.")
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme in INTERNAL_SCHEMES:
            return scheme
        if scheme not in ALLOWED_SCHEMES:
            raise PolicyViolation(
                "SCHEME_NOT_ALLOWED", f"Scheme {scheme or '(none)'!r} is not allowed."
            )
        if parts.username or parts.password:
            raise PolicyViolation(
                "CREDENTIALS_IN_URL", "URLs with embedded credentials are refused."
            )
        origin = normalise_origin(url)
        if origin not in self.allowed_origins:
            raise PolicyViolation("TARGET_NOT_ALLOWED", f"Origin {origin} is not authorised.")
        self._check_resolution(parts.hostname or "")
        return origin

    def _check_resolution(self, host: str) -> None:
        try:
            literal = ipaddress.ip_address(host.strip("[]"))
            addresses = [literal]
        except ValueError:
            try:
                addresses = [ipaddress.ip_address(a) for a in self.resolver(host)]
            except (OSError, ValueError) as exc:
                raise PolicyViolation("DNS_FAILURE", f"Could not resolve {host}.") from exc
        if not addresses:
            raise PolicyViolation("DNS_FAILURE", f"Could not resolve {host}.")
        for ip in addresses:
            if _is_always_forbidden_ip(ip):
                raise PolicyViolation(
                    "FORBIDDEN_ADDRESS", f"{host} resolves to a forbidden address."
                )
            if not self.allow_internal_ips and _is_internal_ip(ip):
                raise PolicyViolation(
                    "INTERNAL_ADDRESS", f"{host} resolves to an internal address."
                )

    def resolve_navigation(self, base_origin: str, path_or_url: str) -> str:
        """Turn a model-supplied relative path (or absolute URL) into a checked absolute URL."""
        candidate = path_or_url.strip()
        if not candidate:
            raise PolicyViolation("INVALID_PATH", "Empty path.")
        if candidate.startswith("//"):
            raise PolicyViolation("INVALID_PATH", "Protocol-relative URLs are refused.")
        url = urljoin(base_origin + "/", candidate) if "://" not in candidate else candidate
        self.check_url(url)
        return url

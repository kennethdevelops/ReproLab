from __future__ import annotations

import pytest

from reprolab.browser.policy import OriginPolicy, PolicyViolation, normalise_origin


def policy(allow_internal: bool = True, resolves_to: str = "10.0.0.5") -> OriginPolicy:
    return OriginPolicy.from_origins(
        ["http://demo-target:4173"],
        allow_internal_ips=allow_internal,
        resolver=lambda host: [resolves_to],
    )


def code(p: OriginPolicy, url: str) -> str:
    with pytest.raises(PolicyViolation) as exc:
        p.check_url(url)
    return exc.value.code


def test_allowlisted_origin_passes() -> None:
    assert policy().check_url("http://demo-target:4173/checkout?x=1") == "http://demo-target:4173"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://demo-target:4174/", "TARGET_NOT_ALLOWED"),
        ("https://demo-target:4173/", "TARGET_NOT_ALLOWED"),
        ("http://evil.test/", "TARGET_NOT_ALLOWED"),
        ("file:///etc/passwd", "SCHEME_NOT_ALLOWED"),
        ("javascript:alert(1)", "SCHEME_NOT_ALLOWED"),
        ("data:text/html,<h1>x</h1>", "SCHEME_NOT_ALLOWED"),
        ("chrome://settings", "SCHEME_NOT_ALLOWED"),
        ("http://user:pw@demo-target:4173/", "CREDENTIALS_IN_URL"),
        ("http://169.254.169.254/latest/meta-data", "TARGET_NOT_ALLOWED"),
        ("http://demo-target:4173/" + "a" * 3000, "URL_TOO_LONG"),
    ],
)
def test_disallowed_urls(url: str, expected: str) -> None:
    assert code(policy(), url) == expected


def test_metadata_address_refused_even_when_allowlisted() -> None:
    p = OriginPolicy.from_origins(["http://169.254.169.254"], resolver=lambda h: [])
    assert code(p, "http://169.254.169.254/latest") == "FORBIDDEN_ADDRESS"


def test_dns_rebinding_to_metadata_is_refused() -> None:
    assert (
        code(policy(resolves_to="169.254.169.254"), "http://demo-target:4173/")
        == "FORBIDDEN_ADDRESS"
    )


def test_hosted_mode_refuses_internal_resolution() -> None:
    p = policy(allow_internal=False, resolves_to="127.0.0.1")
    assert code(p, "http://demo-target:4173/") == "INTERNAL_ADDRESS"
    assert policy(allow_internal=False, resolves_to="93.184.216.34").check_url(
        "http://demo-target:4173/"
    )


def test_relative_navigation_and_protocol_relative() -> None:
    p = policy()
    assert (
        p.resolve_navigation("http://demo-target:4173", "/shop") == "http://demo-target:4173/shop"
    )
    assert (
        p.resolve_navigation("http://demo-target:4173", "checkout")
        == "http://demo-target:4173/checkout"
    )
    with pytest.raises(PolicyViolation):
        p.resolve_navigation("http://demo-target:4173", "//evil.test/x")
    tricky = p.resolve_navigation("http://demo-target:4173", "/../../@evil.test")
    assert normalise_origin(tricky) == "http://demo-target:4173"


def test_origin_normalisation() -> None:
    assert normalise_origin("HTTP://Demo-Target:80/x") == "http://demo-target"
    assert normalise_origin("https://a.test:443") == "https://a.test"
    assert normalise_origin("http://[::1]:8080/") == "http://[::1]:8080"

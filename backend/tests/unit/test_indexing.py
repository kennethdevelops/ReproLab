from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path

import httpx
import pytest

from reprolab.github.client import GitHubSource, parse_repo_url
from reprolab.indexing.chunker import MAX_LINES, chunk_text, search_text
from reprolab.indexing.embeddings import HashingEmbedder
from reprolab.indexing.local_snapshot import export_snapshot
from reprolab.indexing.paths import classify, refusal_reason
from reprolab.indexing.sources import LocalSnapshotSource, SourceError
from reprolab.retrieval.search import literal_terms, rrf, tsquery_terms

REPO = Path(__file__).resolve().parents[3]
DEMO_SRC = REPO / "demo-target" / "src"


def _assert_provenance(text: str, language: str) -> list:  # type: ignore[type-arg]
    lines = text.splitlines()
    chunks = chunk_text(text, language)
    for c in chunks:
        assert 1 <= c.start_line <= c.end_line <= len(lines)
        assert c.content == "\n".join(lines[c.start_line - 1 : c.end_line])
        assert c.end_line - c.start_line + 1 <= MAX_LINES
    return chunks


@pytest.mark.parametrize("path", sorted(DEMO_SRC.rglob("*.ts*")), ids=lambda p: p.name)
def test_chunks_are_exact_line_ranges_of_demo_sources(path: Path) -> None:
    _assert_provenance(path.read_text(encoding="utf-8"), "tsx")


def test_declarations_become_symbols_and_long_code_is_windowed() -> None:
    chunks = _assert_provenance(
        (DEMO_SRC / "checkout" / "useCoupon.ts").read_text("utf-8"), "typescript"
    )
    assert "useCoupon" in {c.symbol for c in chunks}
    long = "\n".join(f"  x{i} = {i}" for i in range(200))
    windows = _assert_provenance("function big() {\n" + long + "\n}", "javascript")
    assert len(windows) >= 3 and windows[1].start_line < windows[0].end_line  # overlap


def test_markdown_splits_on_headings_outside_code_fences() -> None:
    md = (
        "# Title\n\n"
        + "intro\n" * 8
        + "\n## Setup\n\n"
        + "text\n" * 8
        + "```\n# not a heading\n```\n\n## Usage\n"
        + "u\n" * 8
    )
    chunks = _assert_provenance(md, "markdown")
    assert {"Setup", "Usage"} <= {c.symbol for c in chunks}
    assert "not a heading" not in {c.symbol for c in chunks}


def test_search_text_splits_identifiers() -> None:
    text = search_text("src/cart/useCartTotals.ts", "useCartTotals", "const subtotalCents = 1")
    assert {"cart", "totals", "subtotal", "cents"} <= set(text.split())


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("fixtures/fixed/src/checkout/useCoupon.ts", "excluded_directory"),
        ("benchmarks/ground-truth/fixtures.v1.json", "excluded_directory"),
        ("fixtures/oracles/D01.oracle.ts", "excluded_directory"),
        ("node_modules/react/index.js", "excluded_directory"),
        (".env", "excluded_file"),
        (".env.production", "excluded_file"),
        ("config/secrets.json", "excluded_file"),
        ("deploy/server.pem", "excluded_file"),
        ("package-lock.json", "excluded_file"),
        ("assets/app.min.js", "excluded_file"),
        ("../etc/passwd.txt", "invalid_path"),
        ("/abs/file.ts", "invalid_path"),
        ("src\\win.ts", "invalid_path"),
        ("logo.png", "unsupported_type"),
    ],
)
def test_path_refusals(path: str, reason: str) -> None:
    assert refusal_reason(path) == reason


def test_allowed_paths_and_kinds() -> None:
    assert refusal_reason("src/cart/useCartTotals.ts") is None
    assert refusal_reason("src/big.ts", size=10**6) == "too_large"
    assert classify("src/cart/useCartTotals.ts") == "source"
    assert classify("tests/server.test.mjs") == "test"
    assert classify("docs/ARCHITECTURE.md") == "documentation"
    assert classify("package.json") == "configuration"


def test_hashing_embedder_is_deterministic_and_normalised() -> None:
    e = HashingEmbedder()
    a, b = e.embed_documents(["coupon applied", "coupon applied"])
    assert a == b and abs(sum(x * x for x in a) - 1.0) < 1e-9
    assert e.embed_query("coupon") != e.embed_query("pagination")


def test_rrf_rewards_agreement() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fused = rrf({"lexical": [(a, 1.0), (b, 0.5)], "vector": [(b, 0.9), (c, 0.8)]}, k=60)
    assert [cid for cid, _, _ in fused][0] == b
    assert fused[0][2] == {"lexical": 2, "vector": 1}


def test_query_terms_are_sanitised() -> None:
    assert tsquery_terms("x'; DROP TABLE source_chunks; -- | !coupon") == sorted(
        {"drop", "table", "source", "chunks", "coupon"}
    )
    assert "restoreCoupon" in literal_terms("console says restoreCoupon is undefined")
    assert "/checkout" in literal_terms("refresh /checkout")


def test_export_snapshot_contains_committed_source_but_no_answer_keys(tmp_path: Path) -> None:
    sha, written, excluded = export_snapshot(REPO, "demo-target", "demo-target", tmp_path)
    assert len(sha) == 40
    assert "src/checkout/useCoupon.ts" in written
    assert not any(p.startswith("fixtures/") or "oracle" in p.split("/")[0] for p in written)
    assert not (tmp_path / "demo-target" / sha / "files" / "fixtures").exists()
    assert excluded.get("excluded_directory", 0) >= 1
    source = LocalSnapshotSource(tmp_path, "demo-target", 200_000, 2000)
    snap = source.resolve(None)
    assert snap.commit_sha == sha
    assert {f.path for f in source.files(snap)} == set(written)


def test_local_source_rejects_tampered_manifest(tmp_path: Path) -> None:
    sha = "a" * 40
    root = tmp_path / "demo" / sha
    (root / "files" / "fixtures").mkdir(parents=True)
    (root / "files" / "fixtures" / "answer.ts").write_text("secret answer")
    (root / "files" / "ok.ts").write_text("export const ok = 1")
    manifest = {"commit_sha": sha, "files": ["ok.ts", "fixtures/answer.ts", "../../escape.ts"]}
    (root / "manifest.json").write_text(json.dumps(manifest))
    source = LocalSnapshotSource(tmp_path, "demo", 200_000, 2000)
    snap = source.resolve(sha)
    assert [f.path for f in source.files(snap)] == ["ok.ts"]
    assert snap.excluded == {"excluded_directory": 1, "invalid_path": 1}
    with pytest.raises(SourceError):
        source.resolve("main")
    with pytest.raises(SourceError):
        LocalSnapshotSource(tmp_path, "../etc", 1, 1)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/o/r",
        "https://gitlab.com/o/r",
        "https://github.com/o",
        "https://github.com/o/r/tree/main",
        "https://github.com/o/r?x=1",
        "https://user:pw@github.com/o/r",
        "https://github.com/../r",
    ],
)
def test_github_url_validation(url: str) -> None:
    with pytest.raises(SourceError):
        parse_repo_url(url)


def test_github_source_resolves_sha_and_filters_tree() -> None:
    sha = "b" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/acme/shop":
            return httpx.Response(200, json={"default_branch": "main"})
        if path == "/repos/acme/shop/commits/main":
            return httpx.Response(200, json={"sha": sha})
        if path == f"/repos/acme/shop/git/trees/{sha}":
            return httpx.Response(200, json={"truncated": False, "tree": [
                {"type": "blob", "path": "src/app.ts", "sha": "1", "size": 20, "mode": "100644"},
                {"type": "blob", "path": ".env", "sha": "2", "size": 5, "mode": "100644"},
                {"type": "blob", "path": "node_modules/x.js", "sha": "3", "size": 5, "mode": "100644"},
                {"type": "blob", "path": "link.ts", "sha": "4", "size": 5, "mode": "120000"},
                {"type": "tree", "path": "src", "sha": "5"},
            ]})  # fmt: skip
        if path == "/repos/acme/shop/git/blobs/1":
            content = base64.b64encode(b"export const app = 1\n").decode()
            return httpx.Response(200, json={"encoding": "base64", "content": content})
        return httpx.Response(404)

    source = GitHubSource(
        "https://github.com/acme/shop.git", transport=httpx.MockTransport(handler)
    )
    snap = source.resolve(None)
    assert (
        snap.commit_sha == sha
        and snap.blob_url_prefix == f"https://github.com/acme/shop/blob/{sha}/"
    )
    files = list(source.files(snap))
    assert [(f.path, f.text) for f in files] == [("src/app.ts", "export const app = 1\n")]
    assert snap.excluded == {"excluded_file": 1, "excluded_directory": 1, "symlink": 1}


def test_github_rate_limit_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"})

    source = GitHubSource("https://github.com/acme/shop", transport=httpx.MockTransport(handler))
    with pytest.raises(SourceError) as err:
        source.resolve("main")
    assert err.value.code == "GITHUB_RATE_LIMITED"

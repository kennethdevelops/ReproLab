"""Indexing + retrieval against PostgreSQL (FTS + pgvector) with the deterministic hashing
embedder. Semantic (fastembed) behaviour is covered by the `embedding`-marked test."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from reprolab.api.app import create_app
from reprolab.api.v1 import projects as projects_api
from reprolab.config.settings import AppMode, get_settings
from reprolab.db.models import Project, RetrievalEvent, SourceDocument
from reprolab.db.session import session_scope
from reprolab.indexing.local_snapshot import export_snapshot
from reprolab.indexing.pipeline import index_snapshot

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[3]


def write_snapshot(root: Path, name: str, sha: str, files: dict[str, str]) -> None:
    target = root / name / sha
    for rel, text in files.items():
        (target / "files" / rel).parent.mkdir(parents=True, exist_ok=True)
        (target / "files" / rel).write_text(text, encoding="utf-8")
    (target / "manifest.json").write_text(json.dumps({"commit_sha": sha, "files": sorted(files)}))
    (root / name / "CURRENT").write_text(sha)


@pytest.fixture
def env(clean_db: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    settings = get_settings()
    monkeypatch.setattr(settings, "snapshots_dir", tmp_path)
    monkeypatch.setattr(settings, "embedding_provider", "hashing")
    monkeypatch.setattr(projects_api, "enqueue_index", [index_snapshot])
    yield tmp_path


def make_project(repo_url: str) -> uuid.UUID:
    pid = uuid.uuid4()
    with session_scope() as db:
        db.add(Project(id=pid, name=f"p-{pid.hex[:6]}", test_origin="http://127.0.0.1:1", mode="demo",
                       repo_url=repo_url))  # fmt: skip
    return pid


@pytest.fixture
def demo(env: Path) -> tuple[TestClient, uuid.UUID, str]:
    sha, _, _ = export_snapshot(REPO, "demo-target", "demo-target", env)
    pid = make_project("local://demo-target")
    client = TestClient(create_app())
    r = client.post(f"/api/v1/projects/{pid}/index")
    assert r.status_code == 202, r.text
    return client, pid, sha


def test_index_demo_snapshot(demo: tuple[TestClient, uuid.UUID, str]) -> None:
    client, pid, sha = demo
    status = client.get(f"/api/v1/projects/{pid}/index").json()[0]
    assert status["status"] == "ready", status["error"]
    assert status["commit_sha"] == sha and status["embed_model"] == "hashing-256"
    assert status["progress"]["documents"] > 10 and status["progress"]["chunks"] > 20
    with session_scope() as db:
        paths = set(db.scalars(select(SourceDocument.path)))
    assert "src/checkout/useCoupon.ts" in paths
    assert not any("fixtures" in p or "ground-truth" in p for p in paths)
    # Idempotent: same commit, embedder and chunker -> same snapshot.
    again = client.post(f"/api/v1/projects/{pid}/index").json()
    assert again["index_job_id"] == status["id"] and again["status"] == "ready"
    project = client.get(f"/api/v1/projects/{pid}").json()
    assert project["current_snapshot"]["commit_sha"] == sha


def test_exit_gate_query_returns_coupon_source_with_correct_lines(
    demo: tuple[TestClient, uuid.UUID, str],
) -> None:
    client, pid, sha = demo
    for strategy in ("lexical", "vector", "hybrid"):
        r = client.get(f"/api/v1/projects/{pid}/search",
                       params={"q": "coupon removed on checkout refresh", "strategy": strategy})  # fmt: skip
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["commit_sha"] == sha and body["strategy"] == strategy
        paths = [h["path"] for h in body["hits"]]
        assert "src/checkout/useCoupon.ts" in paths, (strategy, paths)
    hit = next(h for h in body["hits"] if h["path"] == "src/checkout/useCoupon.ts")
    assert set(hit["ranks"]) <= {"lexical", "vector"} and hit["ranks"]
    src = client.get(f"/api/v1/projects/{pid}/source",
                     params={"path": hit["path"], "start_line": hit["start_line"], "end_line": hit["end_line"]}).json()  # fmt: skip
    assert (
        src["content"].splitlines()[: len(hit["excerpt"].splitlines())]
        == hit["excerpt"].splitlines()
    )
    on_disk = (REPO / "demo-target" / hit["path"]).read_text("utf-8").splitlines()
    assert src["content"] == "\n".join(on_disk[hit["start_line"] - 1 : hit["end_line"]])
    with session_scope() as db:
        assert db.scalar(select(RetrievalEvent).where(RetrievalEvent.mode == "hybrid")) is not None


def test_exact_identifier_lexical(demo: tuple[TestClient, uuid.UUID, str]) -> None:
    client, pid, _ = demo
    body = client.get(
        f"/api/v1/projects/{pid}/search", params={"q": "useCartTotals", "strategy": "lexical"}
    ).json()
    assert body["hits"][0]["path"] == "src/cart/useCartTotals.ts"
    tests_only = client.get(f"/api/v1/projects/{pid}/search",
                            params={"q": "coupon", "strategy": "lexical", "kind": "test"}).json()  # fmt: skip
    assert all(h["kind"] == "test" for h in tests_only["hits"])


def test_answer_keys_and_unindexed_paths_are_unreadable(
    demo: tuple[TestClient, uuid.UUID, str],
) -> None:
    client, pid, _ = demo
    for path in ("fixtures/fixed/src/checkout/useCoupon.ts", "../benchmarks/ground-truth/fixtures.v1.json",
                 "src/../fixtures/fixed/src/cart/useCartTotals.ts", "/etc/passwd"):  # fmt: skip
        r = client.get(f"/api/v1/projects/{pid}/source", params={"path": path})
        assert r.status_code == 404, path
    body = client.get(f"/api/v1/projects/{pid}/search",
                      params={"q": "northwind.coupon.v1 localStorage persist coupon", "strategy": "hybrid", "top_k": 20}).json()  # fmt: skip
    # The fixed variant persists the coupon under this key; it must not be retrievable.
    assert all("northwind.coupon.v1" not in h["excerpt"] for h in body["hits"])


def test_cross_project_isolation(env: Path) -> None:
    write_snapshot(
        env, "alpha", "1" * 40, {"src/a.ts": "export function alphaOnly() { return 'zebrafish' }\n"}
    )
    write_snapshot(
        env, "beta", "2" * 40, {"src/b.ts": "export function betaOnly() { return 'narwhal' }\n"}
    )
    a, b = make_project("local://alpha"), make_project("local://beta")
    client = TestClient(create_app())
    for pid in (a, b):
        assert client.post(f"/api/v1/projects/{pid}/index").status_code == 202
    for strategy in ("lexical", "vector", "hybrid"):
        hits = client.get(
            f"/api/v1/projects/{a}/search", params={"q": "narwhal betaOnly", "strategy": strategy}
        ).json()["hits"]
        assert all(h["path"] == "src/a.ts" for h in hits)
    assert (
        client.get(f"/api/v1/projects/{a}/source", params={"path": "src/b.ts"}).status_code == 404
    )


def test_new_snapshot_replaces_stale_one_and_reuses_embeddings(env: Path) -> None:
    shared = "export function sharedHelper() {\n  return 1\n}\n" * 3
    write_snapshot(
        env,
        "evolving",
        "3" * 40,
        {"src/s.ts": shared, "src/old.ts": "export const legacyWombat = 1\n"},
    )
    pid = make_project("local://evolving")
    client = TestClient(create_app())
    first = client.post(f"/api/v1/projects/{pid}/index").json()
    write_snapshot(
        env,
        "evolving",
        "4" * 40,
        {"src/s.ts": shared, "src/new.ts": "export const freshOtter = 2\n"},
    )
    second = client.post(f"/api/v1/projects/{pid}/index").json()
    assert first["index_job_id"] != second["index_job_id"] and second["commit_sha"] == "4" * 40
    statuses = {s["commit_sha"]: s for s in client.get(f"/api/v1/projects/{pid}/index").json()}
    assert statuses["4" * 40]["progress"]["reused_embeddings"] >= 1
    body = client.get(
        f"/api/v1/projects/{pid}/search",
        params={"q": "legacyWombat freshOtter", "strategy": "lexical"},
    ).json()
    assert body["commit_sha"] == "4" * 40
    assert [h["path"] for h in body["hits"]] == ["src/new.ts"]


def test_unready_index_and_public_mode(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = make_project("local://missing")
    client = TestClient(create_app())
    r = client.post(f"/api/v1/projects/{pid}/index")
    assert r.status_code == 422 and r.json()["error"]["code"] == "SNAPSHOT_NOT_FOUND"
    assert (
        client.get(f"/api/v1/projects/{pid}/search", params={"q": "x"}).json()["error"]["code"]
        == "NOT_INDEXED"
    )
    monkeypatch.setattr(get_settings(), "app_mode", AppMode.PUBLIC_DEMO)
    assert client.post(f"/api/v1/projects/{pid}/index").status_code == 403


@pytest.mark.embedding
def test_semantic_paraphrase_with_fastembed(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Paraphrase with no shared identifiers; needs the local fastembed model (downloaded once)."""
    monkeypatch.setattr(get_settings(), "embedding_provider", "fastembed")
    export_snapshot(REPO, "demo-target", "demo-target", env)
    pid = make_project("local://demo-target")
    client = TestClient(create_app())
    assert client.post(f"/api/v1/projects/{pid}/index").status_code == 202
    status = client.get(f"/api/v1/projects/{pid}/index").json()[0]
    assert status["status"] == "ready", status["error"]
    body = client.get(f"/api/v1/projects/{pid}/search",
                      params={"q": "the page numbers at the bottom of the product list", "strategy": "vector"}).json()  # fmt: skip
    assert "src/catalog/Pagination.tsx" in [h["path"] for h in body["hits"][:3]], body["hits"]

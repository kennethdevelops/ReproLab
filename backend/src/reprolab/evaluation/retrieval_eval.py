"""Retrieval evaluation (M6): lexical vs vector vs hybrid on the demo-store cases.

Each public bug report (``benchmarks/cases``) is used verbatim as the query. Hits are compared with
the labelled files in ``benchmarks/ground-truth``. Ground truth is read only here, by the
evaluator. It is never indexed and never reaches the agent.

Metrics (file level, hits deduplicated by path in rank order):
- Recall@k: share of the case's ``relevant_files`` among the top k files.
- MRR: reciprocal rank of the first ``defect_files`` entry (0 if absent from the top 10).

Usage (needs PostgreSQL with pgvector; the database name must contain "eval" or "test")::

    uv run python -m reprolab.evaluation.retrieval_eval --out ../benchmarks/results/retrieval
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from reprolab.config.settings import get_settings
from reprolab.db.models import Project, RepoSnapshot
from reprolab.db.session import session_scope
from reprolab.indexing.embeddings import get_embedder
from reprolab.indexing.local_snapshot import export_snapshot
from reprolab.retrieval.search import search

REPO = Path(__file__).resolve().parents[4]
STRATEGIES = ("lexical", "vector", "hybrid")
PREFIX = "demo-target/"


def _strip(path: str) -> str:
    return path[len(PREFIX) :] if path.startswith(PREFIX) else path


def file_ranking(paths: list[str]) -> list[str]:
    seen: list[str] = []
    for p in paths:
        if p not in seen:
            seen.append(p)
    return seen


def score(ranked_files: list[str], relevant: list[str], defects: list[str]) -> dict[str, float]:
    rel = set(relevant)
    out: dict[str, float] = {}
    for k in (1, 3, 5, 10):
        out[f"recall@{k}"] = round(len(rel & set(ranked_files[:k])) / len(rel), 4) if rel else 0.0
    rr = 0.0
    for i, f in enumerate(ranked_files[:10], 1):
        if f in defects:
            rr = 1.0 / i
            break
    out["mrr"] = round(rr, 4)
    return out


def _index_demo(snapshots_dir: Path) -> tuple[uuid.UUID, str]:
    from fastapi.testclient import TestClient

    from reprolab.api.app import create_app
    from reprolab.api.v1 import projects as projects_api
    from reprolab.indexing.pipeline import index_snapshot

    sha, _, _ = export_snapshot(REPO, "demo-target", "demo-target", snapshots_dir)
    pid = uuid.uuid4()
    with session_scope() as db:
        db.add(Project(id=pid, name=f"retrieval-eval-{pid.hex[:6]}", test_origin="http://127.0.0.1:1",
                       mode="demo", repo_url="local://demo-target"))  # fmt: skip

    def _index_inline(snapshot_id: uuid.UUID) -> None:
        index_snapshot(snapshot_id)

    projects_api.enqueue_index[0] = _index_inline
    r = TestClient(create_app()).post(f"/api/v1/projects/{pid}/index")
    if r.status_code != 202 or r.json()["status"] != "ready":
        raise SystemExit(f"indexing failed: {r.status_code} {r.text}")
    return pid, sha


def run(out_dir: Path, top_k: int = 10) -> dict[str, Any]:
    settings = get_settings()
    db_name = settings.database_url.rsplit("/", 1)[-1]
    if "eval" not in db_name and "test" not in db_name:
        raise SystemExit(
            f"refusing to write evaluation data into {db_name!r}; use an eval/test database"
        )
    cases = json.loads((REPO / "benchmarks/cases/cases.v1.json").read_text(encoding="utf-8"))[
        "cases"
    ]
    truth = {f["case_id"]: f for f in json.loads(
        (REPO / "benchmarks/ground-truth/fixtures.v1.json").read_text(encoding="utf-8"))["fixtures"]}  # fmt: skip
    with tempfile.TemporaryDirectory() as tmp:
        settings.snapshots_dir = Path(tmp)
        pid, sha = _index_demo(Path(tmp))
    embedder = get_embedder(settings)
    rows: list[dict[str, Any]] = []
    with session_scope() as db:
        snap = db.scalars(select(RepoSnapshot).where(RepoSnapshot.project_id == pid)).one()
        for case in cases:
            gt = truth[case["case_id"]]
            relevant = [_strip(p) for p in gt["relevant_files"]]
            defects = [_strip(p) for p in gt["defect_files"]]
            for strategy in STRATEGIES:
                result = search(db, snap, case["bug_report"], strategy, embedder,  # type: ignore[arg-type]
                                top_k=top_k * 3, candidates=settings.retrieval_candidates,
                                rrf_k=settings.retrieval_rrf_k)  # fmt: skip
                ranked = file_ranking([h.path for h in result.hits])[:top_k]
                rows.append({"case_id": case["case_id"], "strategy": strategy,
                             **score(ranked, relevant, defects), "top_files": ranked[:5],
                             "timing_ms": result.timing_ms})  # fmt: skip
    summary: dict[str, dict[str, float]] = {}
    for strategy in STRATEGIES:
        sel = [r for r in rows if r["strategy"] == strategy]
        summary[strategy] = {m: round(sum(r[m] for r in sel) / len(sel), 4)
                             for m in ("recall@1", "recall@3", "recall@5", "recall@10", "mrr")}  # fmt: skip
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,  # noqa: S607
                            text=True, check=False).stdout.strip()  # fmt: skip
    report = {
        "kind": "retrieval_eval",
        "suite_version": "1",
        "ran_at": datetime.now(UTC).isoformat(),
        "repo_commit": commit,
        "snapshot_commit": sha,
        "embedding_model": embedder.model_id,
        "query": "bug_report text, verbatim",
        "level": "file",
        "summary": summary,
        "rows": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = f"retrieval-{stamp}-{embedder.model_id.replace('/', '_')}"
    json_path, csv_path = out_dir / f"{base}.json", out_dir / f"{base}.csv"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["case_id", "strategy", "recall@1", "recall@3", "recall@5",
                                "recall@10", "mrr", "timing_ms"], extrasaction="ignore")  # fmt: skip
        w.writeheader()
        w.writerows(rows)
    report["written"] = str(json_path)
    return report


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", type=Path, default=REPO / "benchmarks/results/retrieval")
    args = p.parse_args()
    report = run(args.out)
    print(json.dumps({"summary": report["summary"], "embedding_model": report["embedding_model"],
                      "written": report["written"]}, indent=2))  # fmt: skip


if __name__ == "__main__":
    main()

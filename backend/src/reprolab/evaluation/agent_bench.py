"""Agent benchmark: each case x fixture variant x RAG arm x run, with the configured model.

The variants are the buggy store (expected ``reproduced``) and the fixed store (expected
``not_reproduced``). The arms are ``rag_mode`` values, ``none`` and ``hybrid`` by default. All
other variables are held constant. Each run goes through the real API and job code: the real
browser, verification, budgets and, when the runner is configured, regression-test validation.

Raw rows and a per-arm summary go to ``benchmarks/results/agent/``, with the model id. Replay runs
are labelled ``replay:<model>`` and must not be reported as model results.

Usage (demo store buggy and fixed servers running; eval/test database)::

    uv run python -m reprolab.evaluation.agent_bench --buggy-url http://127.0.0.1:4173 \\
        --fixed-url http://127.0.0.1:4174 --runs 2 --cases D01 D02 D05 --arms none hybrid
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
import time
import urllib.request
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reprolab.agent.model_client import ModelClient, build_model_client
from reprolab.config.settings import Settings, get_settings
from reprolab.db.models import Investigation, Project
from reprolab.db.session import session_scope

REPO = Path(__file__).resolve().parents[4]
EXPECTED = {"buggy": "reproduced", "fixed": "not_reproduced"}

ModelFactory = Callable[[Settings], ModelClient]


def _reset(origin: str, token: str | None) -> None:
    if not token:
        return
    req = urllib.request.Request(f"{origin}/__admin/reset", method="POST",  # noqa: S310
                                 headers={"x-admin-token": token})  # fmt: skip
    with urllib.request.urlopen(req, timeout=5):  # noqa: S310
        pass


def run_bench(
    buggy_url: str,
    fixed_url: str,
    case_ids: list[str],
    arms: list[str],
    runs: int,
    out_dir: Path,
    model_factory: ModelFactory = build_model_client,
    admin_token: str | None = None,
) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from reprolab.api.app import create_app
    from reprolab.api.v1 import investigations as inv_api
    from reprolab.api.v1 import projects as projects_api
    from reprolab.indexing.local_snapshot import export_snapshot
    from reprolab.indexing.pipeline import index_snapshot
    from reprolab.workers.investigation_job import execute_investigation

    settings = get_settings()
    db_name = settings.database_url.rsplit("/", 1)[-1]
    if "eval" not in db_name and "test" not in db_name:
        raise SystemExit(f"refusing to write benchmark data into {db_name!r}")
    cases = {c["case_id"]: c for c in json.loads(
        (REPO / "benchmarks/cases/cases.v1.json").read_text(encoding="utf-8"))["cases"]}  # fmt: skip
    model_id = model_factory(settings).model_id

    def _run_inline(investigation_id: uuid.UUID) -> None:
        execute_investigation(investigation_id, model_factory=model_factory)

    inv_api.enqueue_investigation[0] = _run_inline

    def _index_inline(snapshot_id: uuid.UUID) -> None:
        index_snapshot(snapshot_id)

    projects_api.enqueue_index[0] = _index_inline
    client = TestClient(create_app())

    projects: dict[str, uuid.UUID] = {}
    with tempfile.TemporaryDirectory() as tmp:
        settings.snapshots_dir = Path(tmp)
        export_snapshot(REPO, "demo-target", "demo-target", Path(tmp))
        for variant, origin in (("buggy", buggy_url), ("fixed", fixed_url)):
            pid = uuid.uuid4()
            with session_scope() as db:
                db.add(Project(id=pid, name=f"bench-{variant}-{pid.hex[:6]}", test_origin=origin,
                               mode="demo", repo_url="local://demo-target"))  # fmt: skip
            if any(a != "none" for a in arms):
                r = client.post(f"/api/v1/projects/{pid}/index")
                if r.json().get("status") != "ready":
                    raise SystemExit(f"indexing failed: {r.text}")
            projects[variant] = pid

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in model_id)
    # Each row is appended as soon as its run ends, so a killed bench keeps finished runs.
    # The file is removed once the full report is written.
    partial_path = out_dir / f"agent-{stamp}-{safe}.partial.jsonl"
    rows: list[dict[str, Any]] = []
    for case_id in case_ids:
        case = cases[case_id]
        for variant, origin in (("buggy", buggy_url), ("fixed", fixed_url)):
            for arm in arms:
                for n in range(1, runs + 1):
                    _reset(origin, admin_token)
                    started = time.monotonic()
                    r = client.post("/api/v1/investigations", json={
                        "project_id": str(projects[variant]), "bug_report": case["bug_report"],
                        "start_path": case["start_path"], "rag_mode": arm})  # fmt: skip
                    if r.status_code != 202:
                        raise SystemExit(f"start failed: {r.status_code} {r.text}")
                    inv_id = uuid.UUID(r.json()["investigation_id"])
                    with session_scope() as db:
                        inv = db.get(Investigation, inv_id)
                        assert inv is not None
                        result = inv.result or {}
                        run = result.get("run") or {}
                        rt = result.get("regression_test") or {}
                        rows.append({
                            "case_id": case_id, "variant": variant, "rag_mode": arm, "run": n,
                            "investigation_id": str(inv_id), "status": inv.status,
                            "expected": EXPECTED[variant], "correct": inv.status == EXPECTED[variant],
                            "claimed_status": result.get("claimed_status"),
                            "regression_test": rt.get("status"),
                            "regression_test_reason": rt.get("reason"),
                            "model_id": run.get("model_id", model_id),
                            "model_calls": run.get("model_calls"),
                            "browser_steps": run.get("browser_steps"),
                            "input_tokens": (run.get("usage") or {}).get("input_tokens"),
                            "output_tokens": (run.get("usage") or {}).get("output_tokens"),
                            "estimated_cost_usd": run.get("estimated_cost_usd"),
                            "seconds": round(time.monotonic() - started, 1),
                            "status_reason": (inv.status_reason or "")[:300],
                        })  # fmt: skip
                    with partial_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(rows[-1]) + "\n")

    summary: dict[str, Any] = {}
    for arm in arms:
        sel = [r for r in rows if r["rag_mode"] == arm]
        buggy = [r for r in sel if r["variant"] == "buggy"]
        summary[arm] = {
            "runs": len(sel),
            "accuracy": round(sum(r["correct"] for r in sel) / len(sel), 4) if sel else None,
            "reproduced_on_buggy": f"{sum(r['correct'] for r in buggy)}/{len(buggy)}",
            "false_reproductions_on_fixed": sum(
                r["status"] == "reproduced" for r in sel if r["variant"] == "fixed"
            ),
            "validated_tests": sum(r["regression_test"] == "validated" for r in buggy),
            "mean_model_calls": round(sum(r["model_calls"] or 0 for r in sel) / len(sel), 2) if sel else None,
        }  # fmt: skip
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,  # noqa: S607
                            text=True, check=False).stdout.strip()  # fmt: skip
    report = {
        "kind": "agent_bench",
        "suite_version": "1",
        "ran_at": datetime.now(UTC).isoformat(),
        "repo_commit": commit,
        "model_id": model_id,
        "is_replay": model_id.startswith("replay:"),
        "llm_provider": settings.llm_provider,
        "limits": {
            "max_browser_steps": settings.max_browser_steps,
            "max_model_calls": settings.max_model_calls,
            "max_seconds": settings.max_investigation_seconds,
        },  # fmt: skip
        "summary": summary,
        "rows": rows,
    }
    json_path, csv_path = (
        out_dir / f"agent-{stamp}-{safe}.json",
        out_dir / f"agent-{stamp}-{safe}.csv",
    )
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, list(rows[0]) if rows else ["case_id"])
        w.writeheader()
        w.writerows(rows)
    partial_path.unlink(missing_ok=True)
    report["written"] = str(json_path)
    return report


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--buggy-url", required=True)
    p.add_argument("--fixed-url", required=True)
    p.add_argument("--cases", nargs="+", default=["D01", "D02", "D05"])
    p.add_argument("--arms", nargs="+", default=["none", "hybrid"],
                   choices=["none", "lexical", "vector", "hybrid"])  # fmt: skip
    p.add_argument("--runs", type=int, default=2)
    p.add_argument("--out", type=Path, default=REPO / "benchmarks/results/agent")
    args = p.parse_args()
    settings = get_settings()
    token = settings.demo_admin_token.get_secret_value() if settings.demo_admin_token else None
    report = run_bench(args.buggy_url, args.fixed_url, args.cases, args.arms, args.runs, args.out,
                       admin_token=token)  # fmt: skip
    print(json.dumps({"model_id": report["model_id"], "summary": report["summary"],
                      "written": report["written"]}, indent=2))  # fmt: skip


if __name__ == "__main__":
    main()

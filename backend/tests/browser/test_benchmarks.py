"""Benchmark harnesses run end to end. The stub model checks wiring only and is labelled as such."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reprolab.agent.model_client import StubModelClient
from reprolab.config.settings import get_settings
from reprolab.evaluation.agent_bench import run_bench
from reprolab.evaluation.retrieval_eval import file_ranking, score
from reprolab.evaluation.retrieval_eval import run as run_retrieval
from tests.browser.test_agent_d01 import d01_script

pytestmark = [pytest.mark.integration, pytest.mark.browser]


def test_score_math() -> None:
    ranked = file_ranking(["a", "b", "a", "c", "d"])
    assert ranked == ["a", "b", "c", "d"]
    s = score(ranked, relevant=["b", "d", "z"], defects=["c"])
    assert s["recall@1"] == 0.0 and s["recall@5"] == pytest.approx(0.6667, abs=1e-4)
    assert s["mrr"] == pytest.approx(1 / 3, abs=1e-4)


def test_retrieval_eval_writes_results(
    clean_db: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "embedding_provider", "hashing")
    report = run_retrieval(tmp_path)
    assert set(report["summary"]) == {"lexical", "vector", "hybrid"}
    assert len(report["rows"]) == 9
    assert json.loads(Path(report["written"]).read_text())["embedding_model"].startswith("hashing")


def test_agent_bench_with_stub(
    clean_db: None, buggy_origin: str, fixed_origin: str, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    monkeypatch.setattr(get_settings(), "artifacts_dir", tmp_path / "art")
    report = run_bench(buggy_origin, fixed_origin, ["D01"], ["none"], 1, tmp_path / "out",
                       model_factory=lambda s: StubModelClient(d01_script()))  # fmt: skip
    rows = {r["variant"]: r for r in report["rows"]}
    assert rows["buggy"]["status"] == "reproduced" and rows["buggy"]["correct"]
    assert rows["fixed"]["status"] == "not_reproduced" and rows["fixed"]["correct"]
    assert report["summary"]["none"]["accuracy"] == 1.0
    assert report["model_id"] == "stub"
    assert Path(report["written"]).with_suffix(".csv").exists()

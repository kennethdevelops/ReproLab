"""Regression-test spec builder: only honest, verified, CSS-free reproductions get a test."""

from __future__ import annotations

from typing import Any

from reprolab.agent.investigator import AgentOutcome
from reprolab.agent.model_client import Usage
from reprolab.agent.tool_specs import Assessment
from reprolab.agent.verification import StepRecord
from reprolab.config.settings import Settings
from reprolab.reports.regression_test import build_spec, propose_regression_test

SUMMARY = {"kind": "role", "value": "complementary", "name": "Order summary", "exact": False}
BTN = {"kind": "role", "value": "button", "name": "Apply coupon", "exact": False}


def _steps(locator: dict[str, Any] = BTN) -> dict[int, StepRecord]:
    rows = [
        ("open_page", True, "", {"path": "/checkout"}),
        ("fill", True, "", {"locator": {**BTN, "kind": "label", "value": "Coupon code", "name": None},
                            "text": "SAVE10"}),
        ("click", True, "", {"locator": locator}),
        ("click", False, "", {"locator": BTN}),  # failed steps are skipped
        ("read_visible_text", True, "Order summary Discount (SAVE10) −$0.90", {"locator": SUMMARY}),
        ("capture_screenshot", True, "", {"label": "x"}),
        ("reload_page", True, "", {}),
        ("read_visible_text", True, "Order summary Subtotal $9.00", {"locator": SUMMARY}),
    ]  # fmt: skip
    return {i: StepRecord(i, t, ok, out, inp) for i, (t, ok, out, inp) in enumerate(rows, 1)}


def _outcome(status: str = "reproduced", check: Any = "default", **kw: Any) -> AgentOutcome:
    if check == "default":
        check = {"locator": SUMMARY, "expected_text": "Discount (SAVE10)"}
    a = Assessment.model_validate({
        "status": "reproduced", "expected_behaviour": "x", "observed_behaviour": "x",
        "outcome_reason": "x", "evidence": [], "reproduction_steps": [], "hypotheses": [],
        "regression_check": check})  # fmt: skip
    return AgentOutcome(status, "", "reproduced", None, a, None, Usage(), 1, 1, None, None,
                        steps=kw.get("steps") or _steps())  # fmt: skip


def test_builds_spec_with_wait_before_reload() -> None:
    spec, _ = build_spec(_outcome(), "Regression: coupon")
    assert spec is not None
    assert spec["start_path"] == "/checkout"
    assert [s["action"] for s in spec["steps"]] == ["fill", "click", "wait_for_text", "reload"]
    assert spec["steps"][0]["value"] == "SAVE10"
    assert spec["assertions"] == [
        {"type": "text_visible", "locator": SUMMARY, "value": "Discount (SAVE10)"}
    ]


def test_no_test_without_verified_reproduction_or_clear_behaviour() -> None:
    assert build_spec(_outcome(status="inconclusive"), "t")[0] is None
    assert build_spec(_outcome(check=None), "t")[0] is None
    css = {"kind": "css", "value": "#apply", "name": None, "exact": False}
    assert build_spec(_outcome(steps=_steps(css)), "t")[0] is None


def test_without_runner_spec_is_kept_but_no_code() -> None:
    rt = propose_regression_test(_outcome(), "t", True, Settings(_env_file=None))  # type: ignore[call-arg]
    assert rt["status"] == "not_generated" and rt["spec"] is not None and rt["code"] is None

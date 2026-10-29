"""End-to-end agent runs with a scripted (stub) model against the real demo store.

The stub chooses fixed actions, but every observation comes from a real Chromium session and its
final status is computed from the text the browser actually returned. Verification then checks
the cited quotes against the recorded step outputs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from reprolab.agent.investigator import Limits, RunConfig, RunContext, run_investigation_agent
from reprolab.agent.model_client import StubModelClient
from reprolab.agent.recorder import MemoryRecorder
from reprolab.artifacts.store import ArtifactStore
from reprolab.browser.policy import OriginPolicy
from reprolab.browser.session import BrowserSession

pytestmark = pytest.mark.browser

LIMITS = Limits(
    max_browser_steps=25,
    max_model_calls=15,
    max_seconds=120,
    max_input_tokens=100_000,
    max_output_tokens=10_000,
    max_cost_usd=1.0,
)

SUMMARY = {"kind": "role", "value": "complementary", "name": "Order summary", "exact": False}


def _last_tool_result(messages: Any) -> tuple[int, str]:
    for block in messages[-1]["content"][::-1]:
        if block.get("type") == "tool_result":
            text = block["content"]
            step = int(re.match(r"\[step (\d+)\]", text).group(1))  # type: ignore[union-attr]
            return step, text
    raise AssertionError("no tool result")


def _assess(messages: Any) -> list[tuple[str, dict[str, Any]]]:
    step, text = _last_tool_result(messages)
    discount_kept = "Discount (SAVE10)" in text
    quote = "Discount (SAVE10)" if discount_kept else "Subtotal"
    return [
        (
            "finish_with_assessment",
            {
                "status": "not_reproduced" if discount_kept else "reproduced",
                "expected_behaviour": "Applied coupon persists through a reload.",
                "observed_behaviour": "Discount still shown after reload."
                if discount_kept
                else "Order summary shows no discount line after reload.",
                "outcome_reason": "Compared the order summary before and after reload.",
                "evidence": [{"step": step, "quote": quote}],
                "reproduction_steps": [
                    "Open /shop",
                    "Add Cast Iron Skillet",
                    "Open /checkout",
                    "Apply SAVE10",
                    "Reload",
                ],  # fmt: skip
                "hypotheses": [],
            },
        )
    ]


def d01_script() -> list[Any]:
    def role(r: str, name: str) -> dict[str, Any]:
        return {"kind": "role", "value": r, "name": name, "exact": False}

    return [
        [
            (
                "record_plan",
                {
                    "reported_symptom": "coupon lost on reload",
                    "expected_behaviour": "discount persists",
                    "plan_steps": ["add", "apply", "reload"],
                },
            )
        ],  # fmt: skip
        [("open_page", {"path": "/shop"})],
        [("click", {"locator": role("button", "Add Cast Iron Skillet to cart")})],
        [("open_page", {"path": "/checkout"})],
        [
            (
                "fill",
                {
                    "locator": {
                        "kind": "label",
                        "value": "Coupon code",
                        "name": None,
                        "exact": False,
                    },
                    "text": "SAVE10",
                },
            )
        ],  # fmt: skip
        [("click", {"locator": role("button", "Apply coupon")})],
        [
            ("read_visible_text", {"locator": SUMMARY}),
            ("capture_screenshot", {"label": "before reload"}),
        ],
        [("reload_page", {})],
        [("capture_screenshot", {"label": "after reload"})],
        [("read_visible_text", {"locator": SUMMARY})],
        _assess,
    ]


def _run(origin: str, tmp_path: Path, script: list[Any]) -> tuple[Any, MemoryRecorder]:
    store = ArtifactStore(tmp_path / "artifacts")
    recorder = MemoryRecorder(store)
    policy = OriginPolicy.from_origins([origin])
    config = RunConfig("Coupon disappears after checkout refresh.", "/shop", origin, LIMITS)
    with BrowserSession(
        policy, origin, tmp_path / "trace.zip", {"width": 1280, "height": 800}
    ) as browser:
        ctx = RunContext(config, StubModelClient(script), browser, recorder)
        outcome = run_investigation_agent(ctx)
    return outcome, recorder


def test_d01_reproduced_on_buggy_build(buggy_origin: str, tmp_path: Path) -> None:
    outcome, recorder = _run(buggy_origin, tmp_path, d01_script())
    assert outcome.status == "reproduced", outcome.status_reason
    assert outcome.verdict is not None and outcome.verdict.level == "browser_observation"
    assert [e["label"] for e in recorder.evidence_items] == ["before reload", "after reload"]
    assert (tmp_path / "trace.zip").stat().st_size > 1000
    assert all(s["ok"] for s in recorder.steps), recorder.steps


def test_d01_not_reproduced_on_fixed_build(fixed_origin: str, tmp_path: Path) -> None:
    outcome, _ = _run(fixed_origin, tmp_path, d01_script())
    assert outcome.status == "not_reproduced", outcome.status_reason


def test_fabricated_quote_is_rejected(buggy_origin: str, tmp_path: Path) -> None:
    script = d01_script()[:-1]
    script.append(
        lambda messages: [
            (
                "finish_with_assessment",
                {
                    "status": "reproduced",
                    "expected_behaviour": "x",
                    "observed_behaviour": "y",
                    "outcome_reason": "z",
                    "evidence": [
                        {
                            "step": _last_tool_result(messages)[0],
                            "quote": "Error 500: coupon service crashed",
                        }
                    ],
                    "reproduction_steps": [],
                    "hypotheses": [],
                },
            )
        ]  # fmt: skip
    )
    outcome, _ = _run(buggy_origin, tmp_path, script)
    assert outcome.status == "inconclusive"
    assert outcome.claimed_status == "reproduced"
    assert "does not appear" in outcome.status_reason


def test_navigation_to_other_origin_is_blocked(buggy_origin: str, tmp_path: Path) -> None:
    script: list[Any] = [
        [("open_page", {"path": "https://example.com/"})],
        [("open_page", {"path": "file:///etc/passwd"})],
        [("open_page", {"path": "//evil.test/x"})],
    ]
    outcome, recorder = _run(buggy_origin, tmp_path, script)
    acts = [s for s in recorder.steps if s["node"] == "act"]
    assert [s["ok"] for s in acts] == [False, False, False]
    assert "TARGET_NOT_ALLOWED" in acts[0]["summary"]
    assert "SCHEME_NOT_ALLOWED" in acts[1]["summary"]
    assert outcome.status == "blocked"


def test_browser_step_budget_is_enforced(buggy_origin: str, tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    recorder = MemoryRecorder(store)
    limits = Limits(3, 50, 60, 100_000, 10_000, 1.0)
    script = [[("read_current_url", {})] for _ in range(10)]
    config = RunConfig("x", "/shop", buggy_origin, limits)
    policy = OriginPolicy.from_origins([buggy_origin])
    with BrowserSession(
        policy, buggy_origin, tmp_path / "t.zip", {"width": 800, "height": 600}
    ) as b:
        outcome = run_investigation_agent(RunContext(config, StubModelClient(script), b, recorder))
    assert outcome.browser_steps == 3
    assert "Browser step limit" in outcome.status_reason

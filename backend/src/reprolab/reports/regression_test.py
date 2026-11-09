"""Proposed Playwright regression test.

The spec is built deterministically from recorded, successful browser steps plus the model's
``regression_check`` (the text that should be visible once the bug is fixed). It is never
model-authored code. The isolated Node runner (``test-runner/``) re-validates the JSON, generates
the ``.spec.ts`` and, for demo projects only, runs it against the buggy and fixed fixtures.

Statuses: ``validated`` (fails on buggy at an assertion, passes on fixed), ``invalid`` (ran, but
not that pattern), ``unvalidated`` (code generated, not executed: non-demo target or runner
error), ``not_generated`` (no verified reproduction, no clear correct behaviour, or unsupported
steps).
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from reprolab.agent.investigator import AgentOutcome
from reprolab.agent.verification import StepRecord
from reprolab.config.settings import Settings

log = logging.getLogger(__name__)

SPEC_VERSION = 1
_ACTION_MAP = {
    "click": "click",
    "fill": "fill",
    "press": "press",
    "select_option": "select_option",
    "reload_page": "reload",
    "go_back": "go_back",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _locator(raw: dict[str, Any]) -> dict[str, Any] | None:
    if raw.get("kind") == "css":
        return None
    name = raw.get("name") if raw.get("kind") == "role" else None
    return {"kind": raw["kind"], "value": raw["value"], "name": name,
            "exact": bool(raw.get("exact", False))}  # fmt: skip


def _not_generated(reason: str) -> dict[str, Any]:
    return {"status": "not_generated", "reason": reason, "spec": None, "code": None,
            "validation": None}  # fmt: skip


def build_spec(outcome: AgentOutcome, title: str) -> tuple[dict[str, Any] | None, str]:
    """Return (spec, reason). ``spec`` is None when no honest test can be proposed."""
    a = outcome.assessment
    if outcome.status != "reproduced" or a is None:
        return None, "Only verified reproductions get a regression test."
    if a.regression_check is None:
        return None, "The agent gave no unambiguous correct behaviour to assert."
    check_loc = _locator(a.regression_check.locator.model_dump(mode="json"))
    if check_loc is None:
        return None, "CSS locators are not allowed in generated tests."
    expected = a.regression_check.expected_text

    ordered: list[StepRecord] = [outcome.steps[k] for k in sorted(outcome.steps)]
    start_path: str | None = None
    steps: list[dict[str, Any]] = []
    for s in ordered:
        if not s.ok:
            continue
        if s.tool == "open_page":
            path = str(s.input.get("path", ""))
            if start_path is None:
                start_path = path
            else:
                steps.append({"action": "goto", "path": path})
        elif s.tool in _ACTION_MAP:
            if start_path is None:
                return None, "The reproduction did not start with open_page."
            step: dict[str, Any] = {"action": _ACTION_MAP[s.tool]}
            if "locator" in s.input:
                loc = _locator(s.input["locator"])
                if loc is None:
                    return None, "CSS locators are not allowed in generated tests."
                step["locator"] = loc
            if s.tool in ("fill",):
                step["value"] = s.input.get("text", "")
            if s.tool == "select_option":
                step["value"] = s.input.get("value", "")
            if s.tool == "press":
                step["key"] = s.input.get("key", "")
            steps.append(step)
        elif s.tool == "read_visible_text" and _norm(expected) in _norm(s.output) and steps:
            # The expected state was observed mid-run (e.g. before a reload): wait for it there,
            # so the final assertion checks the bug, not a race with an async update.
            loc = _locator(s.input["locator"]) if s.input.get("locator") else None
            wait: dict[str, Any] = {"action": "wait_for_text", "value": expected}
            if loc is not None:
                wait["locator"] = loc
            if steps[-1] != wait:
                steps.append(wait)
    if start_path is None:
        return None, "No page was opened."
    if steps and steps[-1]["action"] == "wait_for_text":
        # Expected text seen after the last action: the run did not end in the buggy state.
        return None, "The expected text was observed at the end of the run; nothing to assert."
    spec = {
        "version": SPEC_VERSION,
        "title": title[:200],
        "start_path": start_path,
        "steps": steps,
        "assertions": [{"type": "text_visible", "locator": check_loc, "value": expected}],
    }
    return spec, "Built from recorded browser steps."


def propose_regression_test(
    outcome: AgentOutcome, title: str, is_demo_project: bool, settings: Settings
) -> dict[str, Any]:
    spec, reason = build_spec(outcome, title)
    if spec is None:
        return _not_generated(reason)
    if not settings.test_runner_url:
        return {"status": "not_generated", "reason": "TEST_RUNNER_URL is not configured.",
                "spec": spec, "code": None, "validation": None}  # fmt: skip
    route = "/validate" if is_demo_project else "/generate"
    try:
        with httpx.Client(base_url=settings.test_runner_url, timeout=240.0) as http:
            r = http.post(route, json={"spec": spec})
    except httpx.HTTPError as exc:
        log.warning("test_runner_unreachable", extra={"error": type(exc).__name__})
        return {"status": "not_generated", "reason": "The test runner is unreachable.",
                "spec": spec, "code": None, "validation": None}  # fmt: skip
    if r.status_code == 422:
        return {"status": "not_generated", "reason": "The runner rejected the spec.",
                "spec": spec, "code": None, "validation": {"errors": r.json().get("details")}}  # fmt: skip
    if r.status_code != 200:
        return {"status": "not_generated", "reason": f"Runner error HTTP {r.status_code}.",
                "spec": spec, "code": None, "validation": None}  # fmt: skip
    body = r.json()
    if not is_demo_project:
        return {"status": "unvalidated",
                "reason": "Generated for review. Tests run automatically only against demo fixtures.",
                "spec": spec, "code": body["code"], "validation": None}  # fmt: skip
    verdict = body["verdict"]
    status = verdict["status"] if verdict["status"] in ("validated", "invalid") else "unvalidated"
    return {"status": status, "reason": verdict["reason"], "spec": spec, "code": body["code"],
            "validation": {"buggy": body["buggy"], "fixed": body["fixed"]}}  # fmt: skip

"""Structured investigation result and Markdown export (spec §3.3, §9.6).

Observed facts, model hypotheses and verification notes are kept in separate sections, and every
value comes from recorded data; nothing here is generated text.
"""

from __future__ import annotations

from typing import Any

from reprolab.agent.investigator import PROMPT_REVISION, AgentOutcome

RESULT_SCHEMA_VERSION = 1


def build_result(
    outcome: AgentOutcome, model_id: str, browser_version: str, viewport: dict[str, int]
) -> dict[str, Any]:
    a = outcome.assessment
    v = outcome.verdict
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": outcome.status,
        "status_reason": outcome.status_reason,
        "claimed_status": outcome.claimed_status,
        "verification": {
            "level": v.level if v else "none",
            "notes": v.notes if v else [],
            "verified_evidence": v.verified_evidence if v else [],
        },
        "expected_behaviour": a.expected_behaviour
        if a
        else (outcome.plan or {}).get("expected_behaviour"),
        "observed_behaviour": a.observed_behaviour if a else None,
        "reproduction_steps": a.reproduction_steps if a else [],
        "hypotheses": [
            {**h.model_dump(), "verification": "unverified_hypothesis"}
            for h in (a.hypotheses if a else [])
        ],
        "plan": outcome.plan,
        "run": {
            "model_id": model_id,
            "prompt_revision": PROMPT_REVISION,
            "model_calls": outcome.model_calls,
            "browser_steps": outcome.browser_steps,
            "usage": outcome.usage.as_dict(),
            "estimated_cost_usd": outcome.usage.cost_usd(model_id),
            "browser_version": browser_version,
            "viewport": viewport,
            "initial_url": outcome.initial_url,
            "final_url": outcome.final_url,
            "stop": outcome.stop,
        },
    }


def render_markdown(
    title: str,
    project_name: str,
    bug_report: str,
    result: dict[str, Any],
    steps: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    snapshot_sha: str | None,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"**Status:** {result['status'].upper().replace('_', ' ')}  ",
        f"**Target:** {project_name} (authorised test environment)  ",
        f"**Repository snapshot:** {snapshot_sha or 'none (browser-only investigation)'}  ",
        f"**Verification:** {result['verification']['level']}",
        "",
        "## Bug report",
        "",
        "> " + bug_report.replace("\n", "\n> "),
        "",
        "## Outcome",
        "",
        f"- Expected: {result.get('expected_behaviour') or 'n/a'}",
        f"- Observed: {result.get('observed_behaviour') or 'n/a'}",
        f"- Reason: {result['status_reason']}",
    ]
    if result.get("claimed_status") and result["claimed_status"] != result["status"]:
        lines.append(
            f"- The agent claimed `{result['claimed_status']}`; verification changed it to `{result['status']}`."
        )
    if result["verification"]["verified_evidence"]:
        lines += ["", "## Verified observations", ""]
        for e in result["verification"]["verified_evidence"]:
            lines.append(f'- Step {e["step"]} (`{e["tool"]}`): "{e["quote"]}"')
    if result["reproduction_steps"]:
        lines += ["", "## Reproduction steps (as reported by the agent)", ""]
        lines += [f"{i}. {s}" for i, s in enumerate(result["reproduction_steps"], 1)]
    lines += ["", "## Recorded browser actions", ""]
    for s in steps:
        if s.get("node") == "act":
            mark = "ok" if s["ok"] else "FAILED"
            lines.append(f"- [{s['sequence']}] `{s['tool']}` {mark}: {s['summary']}")
    if result["hypotheses"]:
        lines += ["", "## Root-cause hypotheses (NOT VERIFIED)", ""]
        for h in result["hypotheses"]:
            lines.append(f"- ({h['confidence']} confidence) {h['statement']}")
    if evidence:
        lines += ["", "## Evidence", ""]
        lines += [f"- {e['type']}: {e['label']} (sha256 {e['sha256'][:12]}…)" for e in evidence]
    run = result["run"]
    cost = run["estimated_cost_usd"]
    lines += [
        "",
        "## Run details",
        "",
        f"- Model: {run['model_id']} (prompt {run['prompt_revision']}), {run['model_calls']} calls",
        f"- Browser: Chromium {run['browser_version']}, viewport {run['viewport']}",
        f"- Browser actions: {run['browser_steps']}",
        f"- Tokens: {run['usage']}",
        f"- Estimated cost: {'$' + format(cost, '.4f') if cost is not None else 'unknown'} (estimate, not an invoice)",
        "",
    ]
    return "\n".join(lines)

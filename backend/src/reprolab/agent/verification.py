"""Code-level checks on the model's final assessment (spec §2.5, §9.4).

The model proposes a status; this module decides whether recorded evidence supports it.
A ``reproduced`` claim survives only if every cited quote appears verbatim in the output of a
successful observation step that ran after at least one successful page interaction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from reprolab.agent.tool_specs import Assessment
from reprolab.browser.actions import MUTATING_ACTIONS, OBSERVATION_ACTIONS


@dataclass
class StepRecord:
    sequence: int
    tool: str
    ok: bool
    output: str


@dataclass
class Verdict:
    status: str
    level: str  # browser_observation | none
    notes: list[str] = field(default_factory=list)
    verified_evidence: list[dict[str, Any]] = field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def verify_assessment(assessment: Assessment, steps: dict[int, StepRecord]) -> Verdict:
    interactions = [s for s in steps.values() if s.tool in MUTATING_ACTIONS and s.ok]
    claimed = assessment.status

    if claimed == "reproduced":
        notes: list[str] = []
        verified: list[dict[str, Any]] = []
        if not interactions:
            notes.append("No successful page interaction was recorded.")
        if not assessment.evidence:
            notes.append("No evidence was cited.")
        first_interaction = min((s.sequence for s in interactions), default=None)
        for ref in assessment.evidence:
            step = steps.get(ref.step)
            if step is None:
                notes.append(f"Evidence cites step {ref.step}, which does not exist.")
            elif step.tool not in OBSERVATION_ACTIONS:
                notes.append(f"Step {ref.step} ({step.tool}) is not an observation step.")
            elif not step.ok:
                notes.append(f"Step {ref.step} failed, so it cannot be evidence.")
            elif first_interaction is None or step.sequence < first_interaction:
                notes.append(f"Step {ref.step} ran before any page interaction.")
            elif _norm(ref.quote) not in _norm(step.output):
                notes.append(f"Quote cited for step {ref.step} does not appear in its output.")
            else:
                verified.append({"step": ref.step, "tool": step.tool, "quote": ref.quote})
        if notes:
            return Verdict(
                "inconclusive",
                "none",
                ["Reproduction claim rejected: " + n for n in notes],
                verified,
            )
        return Verdict("reproduced", "browser_observation", [], verified)

    if claimed == "not_reproduced":
        if not interactions:
            return Verdict(
                "inconclusive",
                "none",
                ["'not_reproduced' requires at least one successful page interaction."],
            )
        return Verdict("not_reproduced", "browser_observation")

    if claimed == "blocked":
        return Verdict("blocked", "none")
    return Verdict("inconclusive", "none")

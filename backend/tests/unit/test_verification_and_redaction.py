from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from reprolab.agent.model_client import Usage
from reprolab.agent.tool_specs import BROWSER_TOOLS, Assessment, all_tools
from reprolab.agent.verification import StepRecord, verify_assessment
from reprolab.browser.actions import BROWSER_ACTIONS, Locator
from reprolab.observability.redaction import redact_headers, redact_text, redact_value

STEPS = {
    2: StepRecord(2, "open_page", True, ""),
    3: StepRecord(3, "reload_page", True, ""),
    4: StepRecord(4, "read_visible_text", True, "Order summary\nSubtotal $20.00\nTotal $24.99"),
    5: StepRecord(5, "read_visible_text", False, ""),
    1: StepRecord(1, "read_current_url", True, "/shop"),
}


def assessment(status: str, evidence: list[dict[str, Any]]) -> Assessment:
    return Assessment.model_validate(
        {
            "status": status,
            "expected_behaviour": "e",
            "observed_behaviour": "o",
            "outcome_reason": "r",
            "evidence": evidence,
            "reproduction_steps": [],
            "hypotheses": [],
        }  # fmt: skip
    )


def test_verified_quote_keeps_reproduced() -> None:
    v = verify_assessment(
        assessment("reproduced", [{"step": 4, "quote": "subtotal   $20.00"}]), STEPS
    )
    assert v.status == "reproduced" and v.level == "browser_observation"


@pytest.mark.parametrize(
    ("evidence", "fragment"),
    [
        ([], "No evidence"),
        ([{"step": 99, "quote": "x"}], "does not exist"),
        ([{"step": 3, "quote": "x"}], "not an observation"),
        ([{"step": 5, "quote": "x"}], "failed"),
        ([{"step": 1, "quote": "/shop"}], "before any page interaction"),
        ([{"step": 4, "quote": "Discount removed"}], "does not appear"),
    ],
)
def test_unsupported_reproduced_is_downgraded(
    evidence: list[dict[str, Any]], fragment: str
) -> None:
    v = verify_assessment(assessment("reproduced", evidence), STEPS)
    assert v.status == "inconclusive"
    assert any(fragment in n for n in v.notes)


def test_not_reproduced_requires_interaction() -> None:
    only_reads = {1: StepRecord(1, "read_current_url", True, "/")}
    assert verify_assessment(assessment("not_reproduced", []), only_reads).status == "inconclusive"
    assert verify_assessment(assessment("not_reproduced", []), STEPS).status == "not_reproduced"


def test_every_browser_tool_has_validator_and_tool_names_unique() -> None:
    names = [t["name"] for t in all_tools()]
    assert len(names) == len(set(names))
    assert {t["name"] for t in BROWSER_TOOLS} == set(BROWSER_ACTIONS)
    for tool in all_tools():
        schema = tool["input_schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])


def test_locator_rejects_unknown_role_and_script_css() -> None:
    with pytest.raises(ValidationError):
        Locator.model_validate({"kind": "role", "value": "script", "name": None, "exact": False})
    with pytest.raises(ValidationError):
        Locator.model_validate(
            {"kind": "css", "value": "a[href^='javascript:']", "name": None, "exact": False}
        )
    with pytest.raises(ValidationError):
        Locator.model_validate({"kind": "text", "value": "x", "evaluate": "alert(1)"})


def test_redaction() -> None:
    text = "key sk-ant-api03-abcdefghijkl mail alex@example.test Bearer abc.def.ghi"
    out = redact_text(text)
    assert "sk-ant" not in out and "alex@" not in out and "abc.def" not in out
    assert redact_headers({"Cookie": "s=1", "Accept": "x"}) == {
        "Cookie": "[REDACTED]",
        "Accept": "x",
    }
    assert redact_value({"password": "hunter2", "nested": [{"api_key": "k"}]}) == {
        "password": "[REDACTED]",
        "nested": [{"api_key": "[REDACTED]"}],
    }


def test_usage_cost_estimate() -> None:
    u = Usage(input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=1_000_000)
    assert u.cost_usd("claude-opus-5-5") == pytest.approx(4.0 + 2.0 + 0.2)
    assert u.cost_usd("unknown-model") is None

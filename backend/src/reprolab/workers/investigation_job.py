"""Investigation job: loads a persisted run, executes the agent in a fresh browser, persists the
outcome. Called by the Celery task; also callable directly from tests."""

from __future__ import annotations

import logging
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from reprolab.agent.investigator import Limits, RunConfig, RunContext, run_investigation_agent
from reprolab.agent.model_client import ModelClient, ModelUnavailable, build_model_client
from reprolab.agent.recorder import DbRecorder
from reprolab.artifacts.store import ArtifactStore
from reprolab.browser.policy import OriginPolicy
from reprolab.browser.session import BrowserSession
from reprolab.config.settings import Settings, get_settings
from reprolab.db.enums import FindingVerification, InvestigationStatus
from reprolab.db.models import Finding, Investigation, Project
from reprolab.db.session import session_scope
from reprolab.reports.report import build_result

log = logging.getLogger(__name__)

ModelFactory = Callable[[Settings], ModelClient]


def allowed_origins(project: Project, settings: Settings) -> list[str]:
    origins = [project.test_origin]
    if not settings.is_public_demo:
        origins += settings.local_extra_allowed_origins
    return origins


def execute_investigation(
    investigation_id: uuid.UUID,
    model_factory: ModelFactory = build_model_client,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    store = ArtifactStore(settings.artifacts_dir)

    with session_scope() as db:
        inv = db.get(Investigation, investigation_id)
        if inv is None:
            log.warning("investigation_missing", extra={"investigation_id": str(investigation_id)})
            return "missing"
        if InvestigationStatus(inv.status).is_terminal:
            return inv.status
        project = db.get(Project, inv.project_id)
        assert project is not None
        if inv.started_at is not None:
            # Redelivered after a worker crash. Browser actions are not idempotent and the old
            # browser state is gone, so do not resume: end the run honestly.
            inv.retry_count += 1
            redelivered = True
        else:
            inv.started_at = datetime.now(UTC)
            redelivered = False
        config = RunConfig(
            bug_report=inv.bug_report,
            start_path=inv.start_path,
            base_origin=project.test_origin,
            limits=Limits(**inv.limits),
        )
        viewport = inv.viewport or {"width": 1365, "height": 768}
        origins = allowed_origins(project, settings)
        cancel_requested = inv.cancel_requested

    recorder = DbRecorder(investigation_id, store)
    if redelivered:
        return _finish(investigation_id, recorder, "failed",
                       "Worker restarted during the investigation; the run was not resumed to avoid replaying browser actions.", None)  # fmt: skip
    recorder.event("investigation.started", {"limits": config.limits.as_dict()})
    if cancel_requested:
        return _finish(investigation_id, recorder, "cancelled", "Cancelled before start.", None)

    try:
        model = model_factory(settings)
    except ModelUnavailable as exc:
        return _finish(investigation_id, recorder, "blocked", f"{exc.code}: {exc}", None)

    trace_tmp = store.scratch_path(investigation_id, "trace.zip")
    result: dict[str, Any] | None = None
    try:
        policy = OriginPolicy.from_origins(origins, allow_internal_ips=True)
        browser = BrowserSession(policy, config.base_origin, trace_tmp, viewport)
        with browser:
            ctx = RunContext(config, model, browser, recorder)
            outcome = run_investigation_agent(ctx)
            recorder.set_status("reporting")
            try:
                recorder.evidence("screenshot", "final state", "png", browser.screenshot(), None)
            except Exception:  # noqa: BLE001 - a missing final screenshot must not fail the run
                log.warning("final_screenshot_failed")
            result = build_result(outcome, model.model_id, browser.browser_version, viewport)
        if trace_tmp.exists():
            data = trace_tmp.read_bytes()
            trace_tmp.unlink()
            recorder.evidence("trace", "Playwright trace", "zip", data, None)
    except Exception as exc:
        log.error(
            "investigation_crashed",
            extra={"error_type": type(exc).__name__, "tb": traceback.format_exc()},
        )
        return _finish(
            investigation_id, recorder, "failed", f"Internal error ({type(exc).__name__}).", result
        )

    assert result is not None
    _save_findings(investigation_id, result)
    return _finish(investigation_id, recorder, result["status"], result["status_reason"], result,
                   usage={**result["run"]["usage"], "estimated_cost_usd": result["run"]["estimated_cost_usd"],
                          "model_calls": result["run"]["model_calls"], "browser_steps": result["run"]["browser_steps"]})  # fmt: skip


def _save_findings(investigation_id: uuid.UUID, result: dict[str, Any]) -> None:
    with session_scope() as db:
        for e in result["verification"]["verified_evidence"]:
            db.add(Finding(investigation_id=investigation_id, type="observation",
                           statement=f"Step {e['step']} ({e['tool']}) showed: \"{e['quote']}\"",
                           verification_status=FindingVerification.VERIFIED_OBSERVATION.value,
                           citations=[], evidence_ids=[]))  # fmt: skip
        for h in result["hypotheses"]:
            db.add(Finding(investigation_id=investigation_id, type="hypothesis",
                           statement=h["statement"], verification_status=FindingVerification.UNVERIFIED_HYPOTHESIS.value,
                           citations=[], evidence_ids=[]))  # fmt: skip


TERMINAL_EVENT = {
    "cancelled": "investigation.cancelled",
    "failed": "investigation.failed",
}


def _finish(
    investigation_id: uuid.UUID,
    recorder: DbRecorder,
    status: str,
    reason: str,
    result: dict[str, Any] | None,
    usage: dict[str, Any] | None = None,
) -> str:
    with session_scope() as db:
        inv = db.get(Investigation, investigation_id)
        assert inv is not None
        inv.status = status
        inv.status_reason = reason
        inv.result = result
        if usage is not None:
            inv.usage = usage
        inv.completed_at = datetime.now(UTC)
    recorder.event(
        TERMINAL_EVENT.get(status, "investigation.completed"), {"status": status, "reason": reason}
    )
    return status

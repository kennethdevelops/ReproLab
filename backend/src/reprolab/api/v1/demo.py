"""Preloaded public demo bug reports (the public problem statements only; no answers)."""

from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter
from pydantic import BaseModel

from reprolab.config.settings import get_settings

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoCase(BaseModel):
    case_id: str
    title: str
    bug_report: str
    start_path: str


@lru_cache
def _load_cases() -> list[DemoCase]:
    path = get_settings().demo_cases_path
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [DemoCase.model_validate(c) for c in data.get("cases", [])]


@router.get("/cases", response_model=list[DemoCase])
def list_demo_cases() -> list[DemoCase]:
    return _load_cases()

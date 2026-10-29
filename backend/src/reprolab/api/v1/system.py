from __future__ import annotations

from fastapi import APIRouter

from reprolab.config.settings import get_settings

router = APIRouter(tags=["system"])


@router.get("/settings")
def read_public_settings() -> dict[str, object]:
    """Provider status and limits. Never returns secrets."""
    return get_settings().public_view()

from __future__ import annotations

from fastapi import APIRouter

from reprolab.api.v1 import demo, investigations, projects, system

router = APIRouter()
router.include_router(system.router)
router.include_router(projects.router)
router.include_router(demo.router)
router.include_router(investigations.router)

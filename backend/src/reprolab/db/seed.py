"""Idempotent seed for the preconfigured demo project. Run: ``python -m reprolab.db.seed``."""

from __future__ import annotations

import uuid

from reprolab.config.settings import get_settings
from reprolab.db.models import Project
from reprolab.db.session import session_scope

DEMO_PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def seed() -> None:
    settings = get_settings()
    with session_scope() as db:
        project = db.get(Project, DEMO_PROJECT_ID)
        if project is None:
            project = Project(id=DEMO_PROJECT_ID)
            db.add(project)
        project.name = "Demo Store"
        project.description = (
            "Synthetic storefront with intentionally injected defects. "
            "Authorised test environment operated by ReproLab."
        )
        project.repo_url = None
        project.repo_ref = None
        project.test_origin = settings.demo_allowed_origin
        project.mode = "demo"


if __name__ == "__main__":
    seed()
    print(f"seeded demo project {DEMO_PROJECT_ID}")

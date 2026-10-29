from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from reprolab.api.deps import DbSession
from reprolab.api.errors import ApiError
from reprolab.config.settings import get_settings
from reprolab.db.models import Project, RepoSnapshot

router = APIRouter(prefix="/projects", tags=["projects"])


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    commit_sha: str
    ref: str | None
    status: str
    embed_model: str
    indexed_at: datetime | None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    repo_url: str | None
    repo_ref: str | None
    test_origin: str
    mode: str
    created_at: datetime
    current_snapshot: SnapshotOut | None = None


def _current_snapshot(db: Session, project_id: uuid.UUID) -> RepoSnapshot | None:
    return db.scalars(
        select(RepoSnapshot)
        .where(RepoSnapshot.project_id == project_id, RepoSnapshot.status == "ready")
        .order_by(RepoSnapshot.indexed_at.desc())
        .limit(1)
    ).first()


def _to_out(db: Session, project: Project) -> ProjectOut:
    out = ProjectOut.model_validate(project)
    snapshot = _current_snapshot(db, project.id)
    out.current_snapshot = SnapshotOut.model_validate(snapshot) if snapshot else None
    return out


@router.get("", response_model=list[ProjectOut])
def list_projects(db: DbSession) -> list[ProjectOut]:
    query = select(Project).order_by(Project.created_at)
    if get_settings().is_public_demo:
        query = query.where(Project.mode == "demo")
    return [_to_out(db, p) for p in db.scalars(query)]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, db: DbSession) -> ProjectOut:
    project = db.get(Project, project_id)
    if project is None or (get_settings().is_public_demo and project.mode != "demo"):
        raise ApiError(404, "PROJECT_NOT_FOUND", "Project not found.")
    return _to_out(db, project)

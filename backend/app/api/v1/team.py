"""Team (who has which role) and the action log. Both are for the owner only (enforced in core/permissions.py)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_db
from app.models import AuditLog, User
from app.schemas.imports import CamelModel

router = APIRouter(tags=["team"])

Role = Literal["owner", "staff", "viewer"]


class MemberOut(CamelModel):
    id: str
    email: str
    name: str
    role: Role
    is_active: bool
    last_login_at: datetime | None


class MemberPatch(CamelModel):
    role: Role | None = None
    is_active: bool | None = None


class AuditOut(CamelModel):
    id: int
    at: datetime
    actor_email: str
    actor_role: str
    method: str
    route: str
    outcome: str
    detail: dict[str, Any]


def _out(u: User) -> MemberOut:
    return MemberOut(id=str(u.id), email=u.email, name=u.name, role=u.role, is_active=u.is_active, last_login_at=u.last_login_at)  # type: ignore[arg-type]


@router.get("/team/users", response_model=list[MemberOut], summary="Everyone who can sign in, with their role")
def members(db: Session = Depends(get_db)) -> list[MemberOut]:
    return [_out(u) for u in db.scalars(select(User).where(User.email_verified_at.is_not(None)).order_by(User.created_at))]


@router.patch("/team/users/{user_id}", response_model=MemberOut, summary="Change someone's role or switch their account off")
def change_member(user_id: uuid.UUID, body: MemberPatch, db: Session = Depends(get_db)) -> MemberOut:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "user_not_found", "No such person.")
    new_role = body.role or user.role
    new_active = user.is_active if body.is_active is None else body.is_active
    other_owners = db.scalar(select(func.count()).select_from(User).where(User.role == "owner", User.is_active.is_(True), User.id != user.id)) or 0
    if user.role == "owner" and (new_role != "owner" or not new_active) and other_owners == 0:
        raise ApiError(409, "last_owner", "There must always be one active owner. Make someone else an owner first.")
    user.role, user.is_active = new_role, new_active
    db.commit()
    return _out(user)


@router.get("/audit", response_model=list[AuditOut], summary="The action log: who changed what, and what was refused")
def action_log(
    outcome: Literal["allowed", "denied"] | None = Query(None), actor: str | None = Query(None, max_length=320), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
) -> list[AuditLog]:
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if outcome:
        query = query.where(AuditLog.outcome == outcome)
    if actor:
        query = query.where(AuditLog.actor_email == actor.strip().lower())
    return list(db.scalars(query))

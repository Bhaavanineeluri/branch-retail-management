from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_roles
from models import AuditLog, User, UserRole
from schemas.audit_log import AuditLogResponse


router = APIRouter(prefix="/api/audit-logs", tags=["Audit Logs"])

AdminUser = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN)),
]


@router.get("", response_model=list[AuditLogResponse])
def get_audit_logs(
    current_user: AdminUser,
    db: Annotated[Session, Depends(get_db)],
    entity_type: str | None = Query(default=None, max_length=100),
    user_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    statement = select(AuditLog)

    if entity_type:
        statement = statement.where(
            AuditLog.entity_type == entity_type.upper()
        )

    if user_id is not None:
        statement = statement.where(AuditLog.user_id == user_id)

    logs = db.scalars(
        statement.order_by(AuditLog.created_at.desc()).limit(limit)
    ).all()

    return logs


@router.get("/{log_id}", response_model=AuditLogResponse)
def get_audit_log(
    log_id: int,
    current_user: AdminUser,
    db: Annotated[Session, Depends(get_db)],
):
    log = db.get(AuditLog, log_id)

    if log is None:
        raise HTTPException(status_code=404, detail="Audit log not found")

    return log

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import AuditLog, User, UserRole
from schemas.user import (
    UserListResponse,
    UserResponse,
    UserRoleUpdate,
    UserStatusUpdate,
)

router = APIRouter(
    prefix="/api/users",
    tags=["User Management"],
)


@router.get("", response_model=UserListResponse)
def list_users(
    current_admin: Annotated[
        User, Depends(require_roles(UserRole.ADMIN))
    ],
    db: Annotated[Session, Depends(get_db)],
):
    users = db.scalars(select(User).order_by(User.id)).all()
    total = db.scalar(select(func.count()).select_from(User)) or 0

    return {"users": users, "total": total}


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    current_admin: Annotated[
        User, Depends(require_roles(UserRole.ADMIN))
    ],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.patch("/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    current_admin: Annotated[
        User, Depends(require_roles(UserRole.ADMIN))
    ],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_admin.id and data.role != current_admin.role:
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own role",
        )

    old_role = user.role
    user.role = data.role

    db.add(
        AuditLog(
            user_id=current_admin.id,
            action="USER_ROLE_UPDATED",
            entity_type="User",
            entity_id=user.id,
            details=f"Role changed from {old_role.value} to {data.role.value}",
        )
    )

    db.commit()
    db.refresh(user)

    return user


@router.patch("/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: int,
    data: UserStatusUpdate,
    current_admin: Annotated[
        User, Depends(require_roles(UserRole.ADMIN))
    ],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_admin.id and not data.is_active:
        raise HTTPException(
            status_code=400,
            detail="You cannot deactivate your own account",
        )

    user.is_active = data.is_active

    db.add(
        AuditLog(
            user_id=current_admin.id,
            action="USER_STATUS_UPDATED",
            entity_type="User",
            entity_id=user.id,
            details=f"Account active status set to {data.is_active}",
        )
    )

    db.commit()
    db.refresh(user)

    return user

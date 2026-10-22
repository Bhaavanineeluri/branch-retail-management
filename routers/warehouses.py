from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import AuditLog, User, UserRole, Warehouse
from schemas.warehouse import (
    WarehouseCreate,
    WarehouseResponse,
    WarehouseUpdate,
)

router = APIRouter(
    prefix="/api/warehouses",
    tags=["Warehouses"],
)


@router.post(
    "",
    response_model=WarehouseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_warehouse(
    data: WarehouseCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    code = data.code.strip().upper()

    existing = db.scalar(
        select(Warehouse).where(Warehouse.code == code)
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Warehouse code already exists",
        )

    warehouse = Warehouse(
        name=data.name.strip(),
        code=code,
        location=data.location,
        type=data.type,
        is_active=True,
    )

    db.add(warehouse)

    try:
        db.flush()

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="WAREHOUSE_CREATED",
                entity_type="Warehouse",
                entity_id=warehouse.id,
                details=f"Warehouse '{warehouse.code}' created",
            )
        )

        db.commit()
        db.refresh(warehouse)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Warehouse code already exists",
        )

    return warehouse


@router.get("", response_model=list[WarehouseResponse])
def list_warehouses(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(
        select(Warehouse).order_by(Warehouse.name)
    ).all()


@router.get("/{warehouse_id}", response_model=WarehouseResponse)
def get_warehouse(
    warehouse_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    warehouse = db.get(Warehouse, warehouse_id)

    if warehouse is None:
        raise HTTPException(
            status_code=404,
            detail="Warehouse not found",
        )

    return warehouse


@router.patch("/{warehouse_id}", response_model=WarehouseResponse)
def update_warehouse(
    warehouse_id: int,
    data: WarehouseUpdate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    warehouse = db.get(Warehouse, warehouse_id)

    if warehouse is None:
        raise HTTPException(
            status_code=404,
            detail="Warehouse not found",
        )

    updates = data.model_dump(exclude_unset=True)

    if "code" in updates and updates["code"] is not None:
        updates["code"] = updates["code"].strip().upper()

        duplicate = db.scalar(
            select(Warehouse).where(
                Warehouse.code == updates["code"],
                Warehouse.id != warehouse_id,
            )
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Warehouse code already exists",
            )

    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()

    for field, value in updates.items():
        setattr(warehouse, field, value)

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="WAREHOUSE_UPDATED",
            entity_type="Warehouse",
            entity_id=warehouse.id,
            details="Warehouse details updated",
        )
    )

    db.commit()
    db.refresh(warehouse)

    return warehouse

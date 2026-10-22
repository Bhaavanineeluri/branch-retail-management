from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import AuditLog, Supplier, User, UserRole
from schemas.supplier import (
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)

router = APIRouter(
    prefix="/api/suppliers",
    tags=["Suppliers"],
)


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier(
    data: SupplierCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    supplier = Supplier(
        name=data.name.strip(),
        email=str(data.email) if data.email else None,
        phone=data.phone,
        address=data.address,
        is_active=True,
    )

    db.add(supplier)
    db.flush()

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="SUPPLIER_CREATED",
            entity_type="Supplier",
            entity_id=supplier.id,
            details=f"Supplier '{supplier.name}' created",
        )
    )

    db.commit()
    db.refresh(supplier)

    return supplier


@router.get("", response_model=list[SupplierResponse])
def list_suppliers(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(
        select(Supplier).order_by(Supplier.name)
    ).all()


@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier(
    supplier_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    supplier = db.get(Supplier, supplier_id)

    if supplier is None:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found",
        )

    return supplier


@router.patch("/{supplier_id}", response_model=SupplierResponse)
def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    supplier = db.get(Supplier, supplier_id)

    if supplier is None:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found",
        )

    updates = data.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()

    if "email" in updates and updates["email"] is not None:
        updates["email"] = str(updates["email"])

    for field, value in updates.items():
        setattr(supplier, field, value)

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="SUPPLIER_UPDATED",
            entity_type="Supplier",
            entity_id=supplier.id,
            details="Supplier details updated",
        )
    )

    db.commit()
    db.refresh(supplier)

    return supplier

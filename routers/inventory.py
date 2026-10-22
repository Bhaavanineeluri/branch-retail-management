from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import (
    AuditLog,
    Inventory,
    Product,
    StockMovement,
    StockMovementType,
    User,
    UserRole,
    Warehouse,
)
from schemas.inventory import (
    InventoryResponse,
    StockAdjustmentRequest,
    StockMovementResponse,
)
from services.inventory import increase_stock, decrease_stock

router = APIRouter(
    prefix="/api/inventory",
    tags=["Inventory"],
)


@router.get("", response_model=list[InventoryResponse])
def list_inventory(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(
        select(Inventory)
        .order_by(Inventory.warehouse_id, Inventory.product_id)
    ).all()


@router.get(
    "/product/{product_id}",
    response_model=list[InventoryResponse],
)
def get_product_inventory(
    product_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return db.scalars(
        select(Inventory)
        .where(Inventory.product_id == product_id)
        .order_by(Inventory.warehouse_id)
    ).all()


@router.get(
    "/warehouse/{warehouse_id}",
    response_model=list[InventoryResponse],
)
def get_warehouse_inventory(
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

    return db.scalars(
        select(Inventory)
        .where(Inventory.warehouse_id == warehouse_id)
        .order_by(Inventory.product_id)
    ).all()


@router.post(
    "/{product_id}/{warehouse_id}/increase",
    response_model=InventoryResponse,
)
def increase_inventory(
    product_id: int,
    warehouse_id: int,
    data: StockAdjustmentRequest,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        inventory = increase_stock(
            db=db,
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity=data.quantity,
            movement_type=StockMovementType.ADJUSTMENT,
            reason=data.reason,
            reference_type="MANUAL_ADJUSTMENT",
            reference_id=None,
        )

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="STOCK_INCREASED",
                entity_type="Inventory",
                entity_id=inventory.id,
                details=(
                    f"Increased stock by {data.quantity}. "
                    f"Reason: {data.reason}"
                ),
            )
        )

        db.commit()
        db.refresh(inventory)

        return inventory

    except Exception:
        db.rollback()
        raise


@router.post(
    "/{product_id}/{warehouse_id}/decrease",
    response_model=InventoryResponse,
)
def decrease_inventory(
    product_id: int,
    warehouse_id: int,
    data: StockAdjustmentRequest,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        inventory = decrease_stock(
            db=db,
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity=data.quantity,
            movement_type=StockMovementType.ADJUSTMENT,
            reason=data.reason,
            reference_type="MANUAL_ADJUSTMENT",
            reference_id=None,
        )

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="STOCK_DECREASED",
                entity_type="Inventory",
                entity_id=inventory.id,
                details=(
                    f"Decreased stock by {data.quantity}. "
                    f"Reason: {data.reason}"
                ),
            )
        )

        db.commit()
        db.refresh(inventory)

        return inventory

    except Exception:
        db.rollback()
        raise


@router.get(
    "/movements",
    response_model=list[StockMovementResponse],
)
def list_stock_movements(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(
        select(StockMovement)
        .order_by(StockMovement.created_at.desc())
    ).all()

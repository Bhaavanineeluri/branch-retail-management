from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    Inventory,
    Product,
    StockMovement,
    StockMovementType,
    Warehouse,
)


def get_or_create_inventory(
    db: Session,
    product_id: int,
    warehouse_id: int,
) -> Inventory:
    inventory = db.scalar(
        select(Inventory)
        .where(
            Inventory.product_id == product_id,
            Inventory.warehouse_id == warehouse_id,
        )
        .with_for_update()
    )

    if inventory:
        return inventory

    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise HTTPException(
            status_code=404,
            detail="Warehouse not found",
        )

    if not product.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot add stock for an inactive product",
        )

    if not warehouse.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot add stock to an inactive warehouse",
        )

    inventory = Inventory(
        product_id=product_id,
        warehouse_id=warehouse_id,
        quantity_on_hand=0,
        quantity_reserved=0,
    )

    db.add(inventory)
    db.flush()

    return inventory


def increase_stock(
    db: Session,
    product_id: int,
    warehouse_id: int,
    quantity: int,
    movement_type: StockMovementType,
    reason: str,
    reference_type: str | None = None,
    reference_id: int | None = None,
) -> Inventory:
    if quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than zero",
        )

    inventory = get_or_create_inventory(
        db,
        product_id,
        warehouse_id,
    )

    inventory.quantity_on_hand += quantity

    db.add(
        StockMovement(
            product_id=product_id,
            warehouse_id=warehouse_id,
            movement_type=movement_type,
            quantity=quantity,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
        )
    )

    db.flush()

    return inventory


def decrease_stock(
    db: Session,
    product_id: int,
    warehouse_id: int,
    quantity: int,
    movement_type: StockMovementType,
    reason: str,
    reference_type: str | None = None,
    reference_id: int | None = None,
) -> Inventory:
    if quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than zero",
        )

    inventory = get_or_create_inventory(
        db,
        product_id,
        warehouse_id,
    )

    available_quantity = (
        inventory.quantity_on_hand
        - inventory.quantity_reserved
    )

    if quantity > available_quantity:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient available stock. "
                f"Available: {available_quantity}, requested: {quantity}"
            ),
        )

    inventory.quantity_on_hand -= quantity

    db.add(
        StockMovement(
            product_id=product_id,
            warehouse_id=warehouse_id,
            movement_type=movement_type,
            quantity=quantity,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
        )
    )

    db.flush()

    return inventory

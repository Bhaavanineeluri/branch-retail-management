from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import (
    Inventory,
    Product,
    PurchaseOrder,
    PurchaseOrderStatus,
    SalesOrder,
    SalesOrderStatus,
    StockMovement,
    User,
    UserRole,
    Warehouse,
)


router = APIRouter(prefix="/api/reports", tags=["Reports"])

InventoryManager = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
]

SalesManager = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.SALES_MANAGER)),
]

AuthenticatedUser = Annotated[User, Depends(get_current_user)]


@router.get("/inventory-summary")
def inventory_summary(
    current_user: InventoryManager,
    db: Annotated[Session, Depends(get_db)],
):
    rows = db.execute(
        select(
            Warehouse.id,
            Warehouse.name,
            Inventory.product_id,
            Product.name.label("product_name"),
            Inventory.quantity_on_hand,
            Inventory.quantity_reserved,
            Product.unit_price,
        )
        .join(Inventory, Inventory.warehouse_id == Warehouse.id)
        .join(Product, Product.id == Inventory.product_id)
        .order_by(Warehouse.id, Product.name)
    ).all()

    items = []
    total_units = 0
    total_value = 0

    for row in rows:
        available = row.quantity_on_hand - row.quantity_reserved
        value = row.quantity_on_hand * row.unit_price

        items.append({
            "warehouse_id": row.id,
            "warehouse_name": row.name,
            "product_id": row.product_id,
            "product_name": row.product_name,
            "quantity_on_hand": row.quantity_on_hand,
            "quantity_reserved": row.quantity_reserved,
            "quantity_available": available,
            "unit_price": row.unit_price,
            "stock_value": value,
        })

        total_units += row.quantity_on_hand
        total_value += value

    return {
        "total_inventory_records": len(items),
        "total_units_on_hand": total_units,
        "total_stock_value": total_value,
        "items": items,
    }


@router.get("/low-stock")
def low_stock_report(
    current_user: InventoryManager,
    db: Annotated[Session, Depends(get_db)],
):
    rows = db.execute(
        select(
            Inventory,
            Product.name.label("product_name"),
            Product.sku,
            Product.reorder_level,
            Warehouse.name.label("warehouse_name"),
        )
        .join(Product, Product.id == Inventory.product_id)
        .join(Warehouse, Warehouse.id == Inventory.warehouse_id)
        .where(
            Product.is_active.is_(True),
            Warehouse.is_active.is_(True),
            (
                Inventory.quantity_on_hand - Inventory.quantity_reserved
            ) <= Product.reorder_level,
        )
        .order_by(Warehouse.name, Product.name)
    ).all()

    items = [
        {
            "product_id": row.Inventory.product_id,
            "product_name": row.product_name,
            "sku": row.sku,
            "warehouse_id": row.Inventory.warehouse_id,
            "warehouse_name": row.warehouse_name,
            "quantity_on_hand": row.Inventory.quantity_on_hand,
            "quantity_reserved": row.Inventory.quantity_reserved,
            "quantity_available": (
                row.Inventory.quantity_on_hand
                - row.Inventory.quantity_reserved
            ),
            "reorder_level": row.reorder_level,
        }
        for row in rows
    ]

    return {"low_stock_count": len(items), "items": items}


@router.get("/sales-summary")
def sales_summary(
    current_user: SalesManager,
    db: Annotated[Session, Depends(get_db)],
):
    result = db.execute(
        select(
            func.count(SalesOrder.id),
            func.coalesce(func.sum(SalesOrder.subtotal), 0),
            func.coalesce(func.sum(SalesOrder.discount_amount), 0),
            func.coalesce(func.sum(SalesOrder.total_amount), 0),
        ).where(SalesOrder.status == SalesOrderStatus.FULFILLED)
    ).one()

    orders = db.scalars(
        select(SalesOrder)
        .where(SalesOrder.status == SalesOrderStatus.FULFILLED)
        .order_by(SalesOrder.created_at.desc())
    ).all()

    return {
        "fulfilled_order_count": result[0],
        "subtotal": result[1],
        "discount_total": result[2],
        "sales_total": result[3],
        "orders": [
            {
                "id": order.id,
                "order_number": order.order_number,
                "customer_name": order.customer_name,
                "warehouse_id": order.warehouse_id,
                "total_amount": order.total_amount,
                "created_at": order.created_at,
            }
            for order in orders
        ],
    }


@router.get("/purchase-summary")
def purchase_summary(
    current_user: InventoryManager,
    db: Annotated[Session, Depends(get_db)],
):
    result = db.execute(
        select(
            func.count(PurchaseOrder.id),
            func.coalesce(func.sum(PurchaseOrder.total_amount), 0),
        ).where(
            PurchaseOrder.status.in_([
                PurchaseOrderStatus.APPROVED,
                PurchaseOrderStatus.PARTIALLY_RECEIVED,
                PurchaseOrderStatus.RECEIVED,
            ])
        )
    ).one()

    orders = db.scalars(
        select(PurchaseOrder)
        .order_by(PurchaseOrder.created_at.desc())
    ).all()

    return {
        "approved_or_received_order_count": result[0],
        "approved_or_received_order_value": result[1],
        "orders": [
            {
                "id": order.id,
                "order_number": order.order_number,
                "supplier_id": order.supplier_id,
                "warehouse_id": order.warehouse_id,
                "status": order.status.value,
                "total_amount": order.total_amount,
                "created_at": order.created_at,
            }
            for order in orders
        ],
    }


@router.get("/stock-movements")
def stock_movement_report(
    current_user: InventoryManager,
    db: Annotated[Session, Depends(get_db)],
):
    movements = db.scalars(
        select(StockMovement).order_by(StockMovement.created_at.desc())
    ).all()

    return {
        "movement_count": len(movements),
        "items": [
            {
                "id": movement.id,
                "product_id": movement.product_id,
                "warehouse_id": movement.warehouse_id,
                "movement_type": movement.movement_type.value,
                "quantity": movement.quantity,
                "reason": movement.reason,
                "reference_type": movement.reference_type,
                "reference_id": movement.reference_id,
                "created_at": movement.created_at,
            }
            for movement in movements
        ],
    }

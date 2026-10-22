from decimal import Decimal
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import (
    AuditLog,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatus,
    StockMovementType,
    Supplier,
    User,
    UserRole,
    Warehouse,
)
from schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderDetail,
    PurchaseOrderReceive,
    PurchaseOrderResponse,
)
from services.inventory import increase_stock

router = APIRouter(
    prefix="/api/purchase-orders",
    tags=["Purchase Orders"],
)

InventoryManager = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
]


@router.post(
    "",
    response_model=PurchaseOrderDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_purchase_order(
    data: PurchaseOrderCreate,
    current_user: InventoryManager,
    db: Annotated[Session, Depends(get_db)],
):
    supplier = db.get(Supplier, data.supplier_id)
    warehouse = db.get(Warehouse, data.warehouse_id)

    if supplier is None or not supplier.is_active:
        raise HTTPException(status_code=400, detail="Supplier not found or inactive")

    if warehouse is None or not warehouse.is_active:
        raise HTTPException(status_code=400, detail="Warehouse not found or inactive")

    # Prevent duplicate products in one order.
    product_ids = [item.product_id for item in data.items]
    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(
            status_code=400,
            detail="Each product can appear only once in a purchase order",
        )

    products = {}
    for item in data.items:
        product = db.get(Product, item.product_id)
        if product is None or not product.is_active:
            raise HTTPException(
                status_code=400,
                detail=f"Product {item.product_id} not found or inactive",
            )
        products[item.product_id] = product

    total = sum(
        (
            item.unit_price * item.quantity_ordered
            for item in data.items
        ),
        Decimal("0.00"),
    )

    order = PurchaseOrder(
        order_number=f"PO-{uuid4().hex[:12].upper()}",
        supplier_id=data.supplier_id,
        warehouse_id=data.warehouse_id,
        status=PurchaseOrderStatus.DRAFT,
        total_amount=total,
        created_by=current_user.id,
    )

    try:
        db.add(order)
        db.flush()

        for item in data.items:
            db.add(
                PurchaseOrderItem(
                    purchase_order_id=order.id,
                    product_id=item.product_id,
                    quantity_ordered=item.quantity_ordered,
                    quantity_received=0,
                    unit_price=item.unit_price,
                )
            )

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="PURCHASE_ORDER_CREATED",
                entity_type="PurchaseOrder",
                entity_id=order.id,
                details=f"Purchase order {order.order_number} created",
            )
        )

        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        raise

    items = db.scalars(
        select(PurchaseOrderItem).where(
            PurchaseOrderItem.purchase_order_id == order.id
        )
    ).all()

    return {**{
        "id": order.id,
        "order_number": order.order_number,
        "supplier_id": order.supplier_id,
        "warehouse_id": order.warehouse_id,
        "status": order.status,
        "total_amount": order.total_amount,
        "created_by": order.created_by,
        "created_at": order.created_at,
    }, "items": items}


@router.get("", response_model=list[PurchaseOrderResponse])
def list_purchase_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(
        select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
    ).all()


@router.get("/{order_id}", response_model=PurchaseOrderDetail)
def get_purchase_order(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    items = db.scalars(
        select(PurchaseOrderItem).where(
            PurchaseOrderItem.purchase_order_id == order.id
        )
    ).all()

    return {
        "id": order.id,
        "order_number": order.order_number,
        "supplier_id": order.supplier_id,
        "warehouse_id": order.warehouse_id,
        "status": order.status,
        "total_amount": order.total_amount,
        "created_by": order.created_by,
        "created_at": order.created_at,
        "items": items,
    }


@router.post("/{order_id}/submit", response_model=PurchaseOrderResponse)
def submit_purchase_order(
    order_id: int,
    current_user: InventoryManager,
    db: Annotated[Session, Depends(get_db)],
):
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    if order.status != PurchaseOrderStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft orders can be submitted")

    order.status = PurchaseOrderStatus.PENDING_APPROVAL
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="PURCHASE_ORDER_SUBMITTED",
            entity_type="PurchaseOrder",
            entity_id=order.id,
            details="Purchase order submitted for approval",
        )
    )
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/approve", response_model=PurchaseOrderResponse)
def approve_purchase_order(
    order_id: int,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    if order.status != PurchaseOrderStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail="Only orders pending approval can be approved",
        )

    order.status = PurchaseOrderStatus.APPROVED
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="PURCHASE_ORDER_APPROVED",
            entity_type="PurchaseOrder",
            entity_id=order.id,
            details="Purchase order approved",
        )
    )
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/receive", response_model=PurchaseOrderDetail)
def receive_purchase_order(
    order_id: int,
    data: PurchaseOrderReceive,
    current_user: InventoryManager,
    db: Annotated[Session, Depends(get_db)],
):
    order = db.scalar(
        select(PurchaseOrder)
        .where(PurchaseOrder.id == order_id)
        .with_for_update()
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    if order.status not in (
        PurchaseOrderStatus.APPROVED,
        PurchaseOrderStatus.PARTIALLY_RECEIVED,
    ):
        raise HTTPException(
            status_code=400,
            detail="Only approved or partially received orders can receive stock",
        )

    items = db.scalars(
        select(PurchaseOrderItem)
        .where(PurchaseOrderItem.purchase_order_id == order.id)
        .with_for_update()
    ).all()
    items_by_id = {item.id: item for item in items}

    requested_ids = [item.item_id for item in data.items]
    if len(requested_ids) != len(set(requested_ids)):
        raise HTTPException(
            status_code=400,
            detail="Each purchase order item can be received only once per request",
        )

    try:
        for received in data.items:
            item = items_by_id.get(received.item_id)

            if item is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Item {received.item_id} does not belong to this order",
                )

            remaining = item.quantity_ordered - item.quantity_received
            if received.quantity > remaining:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot receive {received.quantity} units for item "
                        f"{item.id}; only {remaining} remain"
                    ),
                )

            increase_stock(
                db=db,
                product_id=item.product_id,
                warehouse_id=order.warehouse_id,
                quantity=received.quantity,
                movement_type=StockMovementType.PURCHASE_RECEIPT,
                reason=f"Received purchase order {order.order_number}",
                reference_type="PURCHASE_ORDER",
                reference_id=order.id,
            )

            item.quantity_received += received.quantity

        if all(item.quantity_received == item.quantity_ordered for item in items):
            order.status = PurchaseOrderStatus.RECEIVED
        else:
            order.status = PurchaseOrderStatus.PARTIALLY_RECEIVED

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="PURCHASE_ORDER_STOCK_RECEIVED",
                entity_type="PurchaseOrder",
                entity_id=order.id,
                details="Purchase order quantities received into inventory",
            )
        )

        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        raise

    refreshed_items = db.scalars(
        select(PurchaseOrderItem).where(
            PurchaseOrderItem.purchase_order_id == order.id
        )
    ).all()

    return {
        "id": order.id,
        "order_number": order.order_number,
        "supplier_id": order.supplier_id,
        "warehouse_id": order.warehouse_id,
        "status": order.status,
        "total_amount": order.total_amount,
        "created_by": order.created_by,
        "created_at": order.created_at,
        "items": refreshed_items,
    }

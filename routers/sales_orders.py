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
    SalesOrder,
    SalesOrderItem,
    SalesOrderStatus,
    StockMovementType,
    User,
    UserRole,
    Warehouse,
)
from schemas.sales_order import (
    SalesOrderCreate,
    SalesOrderDetail,
    SalesOrderItemResponse,
    SalesOrderResponse,
)
from services.inventory import decrease_stock


router = APIRouter(prefix="/api/sales-orders", tags=["Sales Orders"])

SalesManager = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.SALES_MANAGER)),
]

AuthenticatedUser = Annotated[
    User,
    Depends(get_current_user),
]


def build_sales_order_response(order: SalesOrder) -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "customer_name": order.customer_name,
        "warehouse_id": order.warehouse_id,
        "status": order.status.value,
        "subtotal": order.subtotal,
        "discount_amount": order.discount_amount,
        "total_amount": order.total_amount,
        "created_by": order.created_by,
    }


@router.post(
    "",
    response_model=SalesOrderDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_sales_order(
    data: SalesOrderCreate,
    current_user: SalesManager,
    db: Annotated[Session, Depends(get_db)],
):
    warehouse = db.get(Warehouse, data.warehouse_id)

    if warehouse is None or not warehouse.is_active:
        raise HTTPException(
            status_code=404,
            detail="Warehouse not found or inactive",
        )

    product_ids = [item.product_id for item in data.items]

    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(
            status_code=400,
            detail="Duplicate products are not allowed in a sales order",
        )

    products = db.scalars(
        select(Product).where(Product.id.in_(product_ids))
    ).all()

    product_map = {product.id: product for product in products}

    if len(product_map) != len(product_ids):
        raise HTTPException(
            status_code=404,
            detail="One or more products were not found",
        )

    for product in products:
        if not product.is_active:
            raise HTTPException(
                status_code=400,
                detail=f"Product {product.id} is inactive",
            )

    subtotal = Decimal("0.00")

    order = SalesOrder(
        order_number=f"SO-{uuid4().hex[:12].upper()}",
        customer_name=data.customer_name,
        warehouse_id=data.warehouse_id,
        status=SalesOrderStatus.DRAFT,
        subtotal=Decimal("0.00"),
        discount_amount=data.discount_amount,
        total_amount=Decimal("0.00"),
        created_by=current_user.id,
    )

    db.add(order)
    db.flush()

    response_items = []

    for item in data.items:
        product = product_map[item.product_id]

        unit_price = product.unit_price
        line_total = unit_price * item.quantity
        subtotal += line_total

        order_item = SalesOrderItem(
            sales_order_id=order.id,
            product_id=product.id,
            quantity=item.quantity,
            unit_price=unit_price,
            line_total=line_total,
        )

        db.add(order_item)
        response_items.append(order_item)

    if data.discount_amount > subtotal:
        raise HTTPException(
            status_code=400,
            detail="Discount cannot exceed subtotal",
        )

    order.subtotal = subtotal
    order.total_amount = subtotal - data.discount_amount

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="CREATE",
            entity_type="SALES_ORDER",
            entity_id=order.id,
            details=f"Created sales order {order.order_number}",
        )
    )

    db.commit()
    db.refresh(order)

    return {
        **build_sales_order_response(order),
        "items": response_items,
    }


@router.get(
    "",
    response_model=list[SalesOrderResponse],
)
def get_sales_orders(
    current_user: AuthenticatedUser,
    db: Annotated[Session, Depends(get_db)],
):
    orders = db.scalars(
        select(SalesOrder).order_by(SalesOrder.id.desc())
    ).all()

    return [build_sales_order_response(order) for order in orders]


@router.get(
    "/{order_id}",
    response_model=SalesOrderDetail,
)
def get_sales_order(
    order_id: int,
    current_user: AuthenticatedUser,
    db: Annotated[Session, Depends(get_db)],
):
    order = db.get(SalesOrder, order_id)

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Sales order not found",
        )

    items = db.scalars(
        select(SalesOrderItem).where(
            SalesOrderItem.sales_order_id == order.id
        )
    ).all()

    return {
        **build_sales_order_response(order),
        "items": items,
    }


@router.post(
    "/{order_id}/confirm",
    response_model=SalesOrderResponse,
)
def confirm_sales_order(
    order_id: int,
    current_user: SalesManager,
    db: Annotated[Session, Depends(get_db)],
):
    order = db.get(SalesOrder, order_id)

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Sales order not found",
        )

    if order.status != SalesOrderStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Only DRAFT sales orders can be confirmed",
        )

    order.status = SalesOrderStatus.CONFIRMED

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="CONFIRM",
            entity_type="SALES_ORDER",
            entity_id=order.id,
            details=f"Confirmed sales order {order.order_number}",
        )
    )

    db.commit()
    db.refresh(order)

    return build_sales_order_response(order)


@router.post(
    "/{order_id}/fulfill",
    response_model=SalesOrderResponse,
)
def fulfill_sales_order(
    order_id: int,
    current_user: SalesManager,
    db: Annotated[Session, Depends(get_db)],
):
    order = db.get(SalesOrder, order_id)

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Sales order not found",
        )

    if order.status != SalesOrderStatus.CONFIRMED:
        raise HTTPException(
            status_code=400,
            detail="Only CONFIRMED sales orders can be fulfilled",
        )

    items = db.scalars(
        select(SalesOrderItem)
        .where(SalesOrderItem.sales_order_id == order.id)
        .with_for_update()
    ).all()

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Sales order has no items",
        )

    try:
        for item in items:
            decrease_stock(
                db=db,
                product_id=item.product_id,
                warehouse_id=order.warehouse_id,
                quantity=item.quantity,
                movement_type=StockMovementType.SALE_FULFILLMENT,
                reason=f"Fulfillment of sales order {order.order_number}",
                reference_type="SALES_ORDER",
                reference_id=order.id,
            )

        order.status = SalesOrderStatus.FULFILLED

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="FULFILL",
                entity_type="SALES_ORDER",
                entity_id=order.id,
                details=f"Fulfilled sales order {order.order_number}",
            )
        )

        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        raise

    return build_sales_order_response(order)

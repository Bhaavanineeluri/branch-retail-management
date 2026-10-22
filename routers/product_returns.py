from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import (
    AuditLog,
    ProductReturn,
    ProductReturnItem,
    ProductReturnStatus,
    SalesOrder,
    SalesOrderItem,
    SalesOrderStatus,
    StockMovementType,
    User,
    UserRole,
    Warehouse,
)
from schemas.product_return import (
    ProductReturnCreate,
    ProductReturnDetail,
    ProductReturnResponse,
)
from services.inventory import increase_stock


router = APIRouter(prefix="/api/product-returns", tags=["Product Returns"])

ReturnManager = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.SALES_MANAGER)),
]

InventoryManager = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
]

AuthenticatedUser = Annotated[User, Depends(get_current_user)]


def build_return_response(product_return: ProductReturn) -> dict:
    return {
        "id": product_return.id,
        "sales_order_id": product_return.sales_order_id,
        "warehouse_id": product_return.warehouse_id,
        "status": product_return.status.value,
        "reason": product_return.reason,
        "created_by": product_return.created_by,
    }


@router.post(
    "",
    response_model=ProductReturnDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_product_return(
    data: ProductReturnCreate,
    current_user: ReturnManager,
    db: Annotated[Session, Depends(get_db)],
):
    sales_order = db.get(SalesOrder, data.sales_order_id)

    if sales_order is None:
        raise HTTPException(status_code=404, detail="Sales order not found")

    if sales_order.status != SalesOrderStatus.FULFILLED:
        raise HTTPException(
            status_code=400,
            detail="Returns can only be created for fulfilled sales orders",
        )

    if data.warehouse_id != sales_order.warehouse_id:
        raise HTTPException(
            status_code=400,
            detail="Return warehouse must match the sales order warehouse",
        )

    warehouse = db.get(Warehouse, data.warehouse_id)
    if warehouse is None or not warehouse.is_active:
        raise HTTPException(
            status_code=404,
            detail="Warehouse not found or inactive",
        )

    item_ids = [item.sales_order_item_id for item in data.items]

    if len(item_ids) != len(set(item_ids)):
        raise HTTPException(
            status_code=400,
            detail="Duplicate sales order items are not allowed",
        )

    sold_items = db.scalars(
        select(SalesOrderItem)
        .where(
            SalesOrderItem.sales_order_id == sales_order.id,
            SalesOrderItem.id.in_(item_ids),
        )
        .with_for_update()
    ).all()

    sold_item_map = {item.id: item for item in sold_items}

    if len(sold_item_map) != len(item_ids):
        raise HTTPException(
            status_code=400,
            detail="One or more items do not belong to this sales order",
        )

    for requested_item in data.items:
        sold_item = sold_item_map[requested_item.sales_order_item_id]

        previously_requested = db.scalar(
            select(func.coalesce(func.sum(ProductReturnItem.quantity), 0))
            .join(
                ProductReturn,
                ProductReturn.id == ProductReturnItem.return_id,
            )
            .where(
                ProductReturnItem.sales_order_item_id == sold_item.id,
                ProductReturn.status != ProductReturnStatus.REJECTED,
            )
        ) or 0

        if previously_requested + requested_item.quantity > sold_item.quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Return quantity exceeds quantity sold for "
                    f"sales order item {sold_item.id}"
                ),
            )

    try:
        product_return = ProductReturn(
            sales_order_id=sales_order.id,
            warehouse_id=data.warehouse_id,
            status=ProductReturnStatus.PENDING,
            reason=data.reason,
            created_by=current_user.id,
        )
        db.add(product_return)
        db.flush()

        response_items = []

        for item in data.items:
            return_item = ProductReturnItem(
                return_id=product_return.id,
                sales_order_item_id=item.sales_order_item_id,
                quantity=item.quantity,
                restockable=item.restockable,
            )
            db.add(return_item)
            response_items.append(return_item)

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="CREATE",
                entity_type="PRODUCT_RETURN",
                entity_id=product_return.id,
                details=f"Created return for sales order {sales_order.id}",
            )
        )

        db.commit()
        db.refresh(product_return)

        return {
            **build_return_response(product_return),
            "items": response_items,
        }

    except Exception:
        db.rollback()
        raise


@router.get("", response_model=list[ProductReturnResponse])
def get_product_returns(
    current_user: AuthenticatedUser,
    db: Annotated[Session, Depends(get_db)],
):
    returns = db.scalars(
        select(ProductReturn).order_by(ProductReturn.id.desc())
    ).all()

    return [build_return_response(item) for item in returns]


@router.get("/{return_id}", response_model=ProductReturnDetail)
def get_product_return(
    return_id: int,
    current_user: AuthenticatedUser,
    db: Annotated[Session, Depends(get_db)],
):
    product_return = db.get(ProductReturn, return_id)

    if product_return is None:
        raise HTTPException(status_code=404, detail="Product return not found")

    items = db.scalars(
        select(ProductReturnItem).where(
            ProductReturnItem.return_id == product_return.id
        )
    ).all()

    return {
        **build_return_response(product_return),
        "items": items,
    }


@router.post("/{return_id}/approve", response_model=ProductReturnResponse)
def approve_product_return(
    return_id: int,
    current_user: ReturnManager,
    db: Annotated[Session, Depends(get_db)],
):
    product_return = db.get(ProductReturn, return_id)

    if product_return is None:
        raise HTTPException(status_code=404, detail="Product return not found")

    if product_return.status != ProductReturnStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Only PENDING returns can be approved",
        )

    product_return.status = ProductReturnStatus.APPROVED
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="APPROVE",
            entity_type="PRODUCT_RETURN",
            entity_id=product_return.id,
            details=f"Approved product return {product_return.id}",
        )
    )

    db.commit()
    db.refresh(product_return)
    return build_return_response(product_return)


@router.post("/{return_id}/reject", response_model=ProductReturnResponse)
def reject_product_return(
    return_id: int,
    current_user: ReturnManager,
    db: Annotated[Session, Depends(get_db)],
):
    product_return = db.get(ProductReturn, return_id)

    if product_return is None:
        raise HTTPException(status_code=404, detail="Product return not found")

    if product_return.status != ProductReturnStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Only PENDING returns can be rejected",
        )

    product_return.status = ProductReturnStatus.REJECTED
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="REJECT",
            entity_type="PRODUCT_RETURN",
            entity_id=product_return.id,
            details=f"Rejected product return {product_return.id}",
        )
    )

    db.commit()
    db.refresh(product_return)
    return build_return_response(product_return)


@router.post("/{return_id}/process", response_model=ProductReturnResponse)
def process_product_return(
    return_id: int,
    current_user: InventoryManager,
    db: Annotated[Session, Depends(get_db)],
):
    product_return = db.scalar(
        select(ProductReturn)
        .where(ProductReturn.id == return_id)
        .with_for_update()
    )

    if product_return is None:
        raise HTTPException(status_code=404, detail="Product return not found")

    if product_return.status != ProductReturnStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail="Only APPROVED returns can be processed",
        )

    items = db.scalars(
        select(ProductReturnItem)
        .where(ProductReturnItem.return_id == product_return.id)
        .with_for_update()
    ).all()

    if not items:
        raise HTTPException(status_code=400, detail="Return has no items")

    try:
        for item in items:
            if not item.restockable:
                continue

            sold_item = db.get(SalesOrderItem, item.sales_order_item_id)

            if sold_item is None:
                raise HTTPException(
                    status_code=400,
                    detail="Associated sales order item was not found",
                )

            increase_stock(
                db=db,
                product_id=sold_item.product_id,
                warehouse_id=product_return.warehouse_id,
                quantity=item.quantity,
                movement_type=StockMovementType.RETURN_RESTOCK,
                reason=f"Restock for product return {product_return.id}",
                reference_type="PRODUCT_RETURN",
                reference_id=product_return.id,
            )

        product_return.status = ProductReturnStatus.PROCESSED

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="PROCESS",
                entity_type="PRODUCT_RETURN",
                entity_id=product_return.id,
                details=f"Processed product return {product_return.id}",
            )
        )

        db.commit()
        db.refresh(product_return)

    except Exception:
        db.rollback()
        raise

    return build_return_response(product_return)

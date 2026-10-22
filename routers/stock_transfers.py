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
    StockMovementType,
    StockTransfer,
    StockTransferItem,
    StockTransferStatus,
    User,
    UserRole,
    Warehouse,
)
from schemas.stock_transfer import (
    StockTransferCreate,
    StockTransferDetail,
    StockTransferResponse,
)
from services.inventory import decrease_stock, increase_stock


router = APIRouter(
    prefix="/api/stock-transfers",
    tags=["Stock Transfers"],
)

TransferManager = Annotated[
    User,
    Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
]

AuthenticatedUser = Annotated[
    User,
    Depends(get_current_user),
]


def build_transfer_response(transfer: StockTransfer) -> dict:
    return {
        "id": transfer.id,
        "transfer_number": transfer.transfer_number,
        "source_warehouse_id": transfer.source_warehouse_id,
        "destination_warehouse_id": transfer.destination_warehouse_id,
        "status": transfer.status.value,
        "created_by": transfer.created_by,
    }


@router.post(
    "",
    response_model=StockTransferDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_stock_transfer(
    data: StockTransferCreate,
    current_user: TransferManager,
    db: Annotated[Session, Depends(get_db)],
):
    if data.source_warehouse_id == data.destination_warehouse_id:
        raise HTTPException(
            status_code=400,
            detail="Source and destination warehouses must be different",
        )

    source = db.get(Warehouse, data.source_warehouse_id)
    destination = db.get(Warehouse, data.destination_warehouse_id)

    if source is None or not source.is_active:
        raise HTTPException(
            status_code=404,
            detail="Source warehouse not found or inactive",
        )

    if destination is None or not destination.is_active:
        raise HTTPException(
            status_code=404,
            detail="Destination warehouse not found or inactive",
        )

    product_ids = [item.product_id for item in data.items]

    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(
            status_code=400,
            detail="Duplicate products are not allowed in a transfer",
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

    transfer = StockTransfer(
        transfer_number=f"ST-{uuid4().hex[:12].upper()}",
        source_warehouse_id=data.source_warehouse_id,
        destination_warehouse_id=data.destination_warehouse_id,
        status=StockTransferStatus.PENDING_APPROVAL,
        created_by=current_user.id,
    )

    db.add(transfer)
    db.flush()

    response_items = []

    for item in data.items:
        transfer_item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=item.product_id,
            quantity=item.quantity,
        )
        db.add(transfer_item)
        response_items.append(transfer_item)

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="CREATE",
            entity_type="STOCK_TRANSFER",
            entity_id=transfer.id,
            details=f"Created stock transfer {transfer.transfer_number}",
        )
    )

    db.commit()
    db.refresh(transfer)

    return {
        **build_transfer_response(transfer),
        "items": response_items,
    }


@router.get(
    "",
    response_model=list[StockTransferResponse],
)
def get_stock_transfers(
    current_user: AuthenticatedUser,
    db: Annotated[Session, Depends(get_db)],
):
    transfers = db.scalars(
        select(StockTransfer).order_by(StockTransfer.id.desc())
    ).all()

    return [build_transfer_response(transfer) for transfer in transfers]


@router.get(
    "/{transfer_id}",
    response_model=StockTransferDetail,
)
def get_stock_transfer(
    transfer_id: int,
    current_user: AuthenticatedUser,
    db: Annotated[Session, Depends(get_db)],
):
    transfer = db.get(StockTransfer, transfer_id)

    if transfer is None:
        raise HTTPException(
            status_code=404,
            detail="Stock transfer not found",
        )

    items = db.scalars(
        select(StockTransferItem).where(
            StockTransferItem.transfer_id == transfer.id
        )
    ).all()

    return {
        **build_transfer_response(transfer),
        "items": items,
    }


@router.post(
    "/{transfer_id}/approve",
    response_model=StockTransferResponse,
)
def approve_stock_transfer(
    transfer_id: int,
    current_user: TransferManager,
    db: Annotated[Session, Depends(get_db)],
):
    transfer = db.get(StockTransfer, transfer_id)

    if transfer is None:
        raise HTTPException(
            status_code=404,
            detail="Stock transfer not found",
        )

    if transfer.status != StockTransferStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail="Only PENDING_APPROVAL transfers can be approved",
        )

    transfer.status = StockTransferStatus.APPROVED

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="APPROVE",
            entity_type="STOCK_TRANSFER",
            entity_id=transfer.id,
            details=f"Approved stock transfer {transfer.transfer_number}",
        )
    )

    db.commit()
    db.refresh(transfer)

    return build_transfer_response(transfer)


@router.post(
    "/{transfer_id}/dispatch",
    response_model=StockTransferResponse,
)
def dispatch_stock_transfer(
    transfer_id: int,
    current_user: TransferManager,
    db: Annotated[Session, Depends(get_db)],
):
    transfer = db.get(StockTransfer, transfer_id)

    if transfer is None:
        raise HTTPException(
            status_code=404,
            detail="Stock transfer not found",
        )

    if transfer.status != StockTransferStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail="Only APPROVED transfers can be dispatched",
        )

    items = db.scalars(
        select(StockTransferItem).where(
            StockTransferItem.transfer_id == transfer.id
        )
    ).all()

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Stock transfer has no items",
        )

    try:
        for item in items:
            decrease_stock(
                db=db,
                product_id=item.product_id,
                warehouse_id=transfer.source_warehouse_id,
                quantity=item.quantity,
                movement_type=StockMovementType.TRANSFER_OUT,
                reason=f"Dispatch of transfer {transfer.transfer_number}",
                reference_type="STOCK_TRANSFER",
                reference_id=transfer.id,
            )

        transfer.status = StockTransferStatus.IN_TRANSIT

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="DISPATCH",
                entity_type="STOCK_TRANSFER",
                entity_id=transfer.id,
                details=f"Dispatched stock transfer {transfer.transfer_number}",
            )
        )

        db.commit()
        db.refresh(transfer)

    except Exception:
        db.rollback()
        raise

    return build_transfer_response(transfer)


@router.post(
    "/{transfer_id}/receive",
    response_model=StockTransferResponse,
)
def receive_stock_transfer(
    transfer_id: int,
    current_user: TransferManager,
    db: Annotated[Session, Depends(get_db)],
):
    transfer = db.get(StockTransfer, transfer_id)

    if transfer is None:
        raise HTTPException(
            status_code=404,
            detail="Stock transfer not found",
        )

    if transfer.status != StockTransferStatus.IN_TRANSIT:
        raise HTTPException(
            status_code=400,
            detail="Only IN_TRANSIT transfers can be received",
        )

    items = db.scalars(
        select(StockTransferItem).where(
            StockTransferItem.transfer_id == transfer.id
        )
    ).all()

    if not items:
        raise HTTPException(
            status_code=400,
            detail="Stock transfer has no items",
        )

    try:
        for item in items:
            increase_stock(
                db=db,
                product_id=item.product_id,
                warehouse_id=transfer.destination_warehouse_id,
                quantity=item.quantity,
                movement_type=StockMovementType.TRANSFER_IN,
                reason=f"Receipt of transfer {transfer.transfer_number}",
                reference_type="STOCK_TRANSFER",
                reference_id=transfer.id,
            )

        transfer.status = StockTransferStatus.COMPLETED

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="RECEIVE",
                entity_type="STOCK_TRANSFER",
                entity_id=transfer.id,
                details=f"Received stock transfer {transfer.transfer_number}",
            )
        )

        db.commit()
        db.refresh(transfer)

    except Exception:
        db.rollback()
        raise

    return build_transfer_response(transfer)

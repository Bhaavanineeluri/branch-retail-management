from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from models.purchase_order import PurchaseOrderStatus


class PurchaseOrderItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity_ordered: int = Field(gt=0)
    unit_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class PurchaseOrderCreate(BaseModel):
    supplier_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    items: list[PurchaseOrderItemCreate] = Field(min_length=1)


class PurchaseOrderItemResponse(BaseModel):
    id: int
    purchase_order_id: int
    product_id: int
    quantity_ordered: int
    quantity_received: int
    unit_price: Decimal

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderResponse(BaseModel):
    id: int
    order_number: str
    supplier_id: int
    warehouse_id: int
    status: PurchaseOrderStatus
    total_amount: Decimal
    created_by: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderDetail(PurchaseOrderResponse):
    items: list[PurchaseOrderItemResponse]


class PurchaseOrderReceiveItem(BaseModel):
    item_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class PurchaseOrderReceive(BaseModel):
    items: list[PurchaseOrderReceiveItem] = Field(min_length=1)

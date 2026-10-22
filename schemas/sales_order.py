from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SalesOrderItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class SalesOrderCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=150)
    warehouse_id: int = Field(gt=0)
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    items: list[SalesOrderItemCreate] = Field(min_length=1)


class SalesOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sales_order_id: int
    product_id: int
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class SalesOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    customer_name: str
    warehouse_id: int
    status: str
    subtotal: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    created_by: int


class SalesOrderDetail(SalesOrderResponse):
    items: list[SalesOrderItemResponse]


class SalesOrderStatusResponse(BaseModel):
    message: str
    order: SalesOrderResponse

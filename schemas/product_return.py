from pydantic import BaseModel, ConfigDict, Field


class ProductReturnItemCreate(BaseModel):
    sales_order_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0)
    restockable: bool = True


class ProductReturnCreate(BaseModel):
    sales_order_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    items: list[ProductReturnItemCreate] = Field(min_length=1)


class ProductReturnItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    return_id: int
    sales_order_item_id: int
    quantity: int
    restockable: bool


class ProductReturnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sales_order_id: int
    warehouse_id: int
    status: str
    reason: str
    created_by: int


class ProductReturnDetail(ProductReturnResponse):
    items: list[ProductReturnItemResponse]

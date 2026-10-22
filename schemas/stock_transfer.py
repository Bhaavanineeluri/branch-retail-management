from pydantic import BaseModel, ConfigDict, Field


class StockTransferItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class StockTransferCreate(BaseModel):
    source_warehouse_id: int = Field(gt=0)
    destination_warehouse_id: int = Field(gt=0)
    items: list[StockTransferItemCreate] = Field(min_length=1)


class StockTransferItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transfer_id: int
    product_id: int
    quantity: int


class StockTransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transfer_number: str
    source_warehouse_id: int
    destination_warehouse_id: int
    status: str
    created_by: int


class StockTransferDetail(StockTransferResponse):
    items: list[StockTransferItemResponse]

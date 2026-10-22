from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InventoryResponse(BaseModel):
    id: int
    product_id: int
    warehouse_id: int
    quantity_on_hand: int
    quantity_reserved: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StockAdjustmentRequest(BaseModel):
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


class StockMovementResponse(BaseModel):
    id: int
    product_id: int
    warehouse_id: int
    movement_type: str
    quantity: int
    reason: str | None
    reference_type: str | None
    reference_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

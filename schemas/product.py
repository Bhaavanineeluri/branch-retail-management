from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    sku: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    category_id: int
    unit_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reorder_level: int = Field(default=0, ge=0)


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=2, max_length=100)
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    category_id: int | None = None
    unit_price: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )
    reorder_level: int | None = Field(default=None, ge=0)


class ProductStatusUpdate(BaseModel):
    is_active: bool


class ProductResponse(BaseModel):
    id: int
    sku: str
    name: str
    description: str | None
    category_id: int
    unit_price: Decimal
    reorder_level: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

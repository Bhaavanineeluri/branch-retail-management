from pydantic import BaseModel, ConfigDict, Field

from models.warehouse import WarehouseType


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    code: str = Field(min_length=2, max_length=50)
    location: str | None = Field(default=None, max_length=300)
    type: WarehouseType


class WarehouseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    code: str | None = Field(default=None, min_length=2, max_length=50)
    location: str | None = Field(default=None, max_length=300)
    type: WarehouseType | None = None
    is_active: bool | None = None


class WarehouseResponse(BaseModel):
    id: int
    name: str
    code: str
    location: str | None
    type: WarehouseType
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

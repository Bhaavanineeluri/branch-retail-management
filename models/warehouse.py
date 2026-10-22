from enum import Enum

from sqlalchemy import Boolean, Enum as SQLEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class WarehouseType(str, Enum):
    WAREHOUSE = "WAREHOUSE"
    STORE = "STORE"


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    location: Mapped[str] = mapped_column(String(255), nullable=False)

    warehouse_type: Mapped[WarehouseType] = mapped_column(
        SQLEnum(WarehouseType),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

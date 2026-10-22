from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ProductReturnStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PROCESSED = "PROCESSED"


class ProductReturn(Base):
    __tablename__ = "product_returns"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    sales_order_id: Mapped[int] = mapped_column(
        ForeignKey("sales_orders.id"),
        nullable=False,
    )

    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id"),
        nullable=False,
    )

    status: Mapped[ProductReturnStatus] = mapped_column(
        SQLEnum(ProductReturnStatus),
        nullable=False,
        default=ProductReturnStatus.PENDING,
    )

    reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class ProductReturnItem(Base):
    __tablename__ = "product_return_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    return_id: Mapped[int] = mapped_column(
        ForeignKey("product_returns.id"),
        nullable=False,
    )

    sales_order_item_id: Mapped[int] = mapped_column(
        ForeignKey("sales_order_items.id"),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    restockable: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
    )

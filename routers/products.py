from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import AuditLog, Category, Product, User, UserRole
from schemas.product import (
    ProductCreate,
    ProductResponse,
    ProductStatusUpdate,
    ProductUpdate,
)

router = APIRouter(
    prefix="/api/products",
    tags=["Products"],
)


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    data: ProductCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    category = db.get(Category, data.category_id)

    if category is None:
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )

    sku = data.sku.strip().upper()

    if not sku:
        raise HTTPException(
            status_code=400,
            detail="SKU cannot be empty",
        )

    existing = db.scalar(
        select(Product).where(Product.sku == sku)
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="SKU already exists",
        )

    product = Product(
        sku=sku,
        name=data.name.strip(),
        description=data.description,
        category_id=data.category_id,
        unit_price=data.unit_price,
        reorder_level=data.reorder_level,
        is_active=True,
    )

    db.add(product)

    try:
        db.flush()

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="PRODUCT_CREATED",
                entity_type="Product",
                entity_id=product.id,
                details=f"Product '{product.sku}' created",
            )
        )

        db.commit()
        db.refresh(product)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Product SKU already exists",
        )

    return product


@router.get("", response_model=list[ProductResponse])
def list_products(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(
        select(Product).order_by(Product.id)
    ).all()


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return product


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    data: ProductUpdate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    updates = data.model_dump(exclude_unset=True)

    if "sku" in updates and updates["sku"] is not None:
        updates["sku"] = updates["sku"].strip().upper()

        duplicate = db.scalar(
            select(Product).where(
                Product.sku == updates["sku"],
                Product.id != product_id,
            )
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="SKU already exists",
            )

    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()

    if "category_id" in updates and updates["category_id"] is not None:
        category = db.get(Category, updates["category_id"])

        if category is None:
            raise HTTPException(
                status_code=404,
                detail="Category not found",
            )

    for field, value in updates.items():
        setattr(product, field, value)

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="PRODUCT_UPDATED",
            entity_type="Product",
            entity_id=product.id,
            details="Product details updated",
        )
    )

    try:
        db.commit()
        db.refresh(product)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Product update violates a database constraint",
        )

    return product


@router.patch("/{product_id}/status", response_model=ProductResponse)
def update_product_status(
    product_id: int,
    data: ProductStatusUpdate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    product.is_active = data.is_active

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="PRODUCT_STATUS_UPDATED",
            entity_type="Product",
            entity_id=product.id,
            details=f"Product active status set to {data.is_active}",
        )
    )

    db.commit()
    db.refresh(product)

    return product

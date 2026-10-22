from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_roles
from models import AuditLog, Category, User, UserRole
from schemas.category import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
)

router = APIRouter(
    prefix="/api/categories",
    tags=["Categories"],
)


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    data: CategoryCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    name = data.name.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Category name cannot be empty",
        )

    existing = db.scalar(
        select(Category).where(Category.name == name)
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Category already exists",
        )

    category = Category(
        name=name,
        description=data.description,
    )

    db.add(category)

    try:
        db.flush()

        db.add(
            AuditLog(
                user_id=current_user.id,
                action="CATEGORY_CREATED",
                entity_type="Category",
                entity_id=category.id,
                details=f"Category '{name}' created",
            )
        )

        db.commit()
        db.refresh(category)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Category already exists",
        )

    return category


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(
        select(Category).order_by(Category.name)
    ).all()


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(
    category_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    category = db.get(Category, category_id)

    if category is None:
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )

    return category


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    data: CategoryUpdate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN, UserRole.INVENTORY_MANAGER)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    category = db.get(Category, category_id)

    if category is None:
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )

    updates = data.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()

        if not updates["name"]:
            raise HTTPException(
                status_code=400,
                detail="Category name cannot be empty",
            )

        duplicate = db.scalar(
            select(Category).where(
                Category.name == updates["name"],
                Category.id != category_id,
            )
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Category name already exists",
            )

    for field, value in updates.items():
        setattr(category, field, value)

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="CATEGORY_UPDATED",
            entity_type="Category",
            entity_id=category.id,
            details="Category details updated",
        )
    )

    db.commit()
    db.refresh(category)

    return category


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.ADMIN)),
    ],
    db: Annotated[Session, Depends(get_db)],
):
    category = db.get(Category, category_id)

    if category is None:
        raise HTTPException(
            status_code=404,
            detail="Category not found",
        )

    product_exists = db.scalar(
        select(Category.id)
        .join(Category.products, isouter=True)
        .where(Category.id == category_id)
    )

    if product_exists:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a category that has products",
        )

    db.add(
        AuditLog(
            user_id=current_user.id,
            action="CATEGORY_DELETED",
            entity_type="Category",
            entity_id=category.id,
            details=f"Category '{category.name}' deleted",
        )
    )

    db.delete(category)
    db.commit()

    return {"message": "Category deleted successfully"}

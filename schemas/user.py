from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models.user import UserRole


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int

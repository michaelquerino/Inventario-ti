from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    email: str
    full_name: str
    role: str = "viewer"
    is_active: bool = True


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

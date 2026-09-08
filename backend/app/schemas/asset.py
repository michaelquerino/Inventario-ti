from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AssetBase(BaseModel):
    asset_tag: str
    screen_asset_tag: str | None = None
    name: str
    category: str | None = None
    status: str = "active"
    serial_number: str | None = None
    brand: str | None = None
    model: str | None = None
    location: str | None = None
    owner: str | None = None
    department: str | None = None
    notes: str | None = None


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    asset_tag: str | None = None
    screen_asset_tag: str | None = None
    name: str | None = None
    category: str | None = None
    status: str | None = None
    serial_number: str | None = None
    brand: str | None = None
    model: str | None = None
    location: str | None = None
    owner: str | None = None
    department: str | None = None
    notes: str | None = None


class AssetRead(AssetBase):
    id: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

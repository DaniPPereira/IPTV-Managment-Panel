from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import DeviceType, SubscriptionStatus

T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    pages: int


class LoginRequest(BaseModel):
    username: str
    password: str


class AdminMe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    must_change_password: bool
    last_login_at: datetime | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    device_type: DeviceType = DeviceType.OTHER
    mac_address: str | None = None
    device_identifier: str | None = None
    subscription_id: UUID | None = None
    active: bool = True


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    device_type: DeviceType | None = None
    mac_address: str | None = None
    device_identifier: str | None = None
    subscription_id: UUID | None = None
    active: bool | None = None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    subscription_id: UUID | None
    name: str
    device_type: DeviceType
    mac_address: str | None
    device_identifier: str | None
    active: bool
    last_seen_at: datetime | None
    last_ip: str | None
    last_user_agent: str | None
    created_at: datetime
    updated_at: datetime


class SubscriptionCreate(BaseModel):
    source_m3u_url: str = Field(min_length=8)
    source_epg_url: str | None = None
    starts_at: datetime | None = None
    expires_at: datetime
    max_devices: int = Field(default=2, ge=1, le=50)
    active: bool = True


class SubscriptionUpdate(BaseModel):
    source_m3u_url: str | None = None
    source_epg_url: str | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    max_devices: int | None = Field(default=None, ge=1, le=50)
    active: bool | None = None


class RenewRequest(BaseModel):
    months: int | None = Field(default=None, ge=1, le=120)
    days: int | None = Field(default=None, ge=1, le=3650)

    @model_validator(mode="after")
    def exactly_one(self) -> RenewRequest:
        if (self.months is None) == (self.days is None):
            raise ValueError("Provide either months or days, not both")
        return self


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    active: bool
    starts_at: datetime
    expires_at: datetime
    max_devices: int
    public_token: str
    xtream_username: str
    xtream_password: str
    last_access_at: datetime | None
    status: SubscriptionStatus
    m3u_url: str
    epg_url: str
    setup_url: str
    xtream_server: str
    source_m3u_url: str | None = None
    source_epg_url: str | None = None
    created_at: datetime
    updated_at: datetime


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = None
    notes: str | None = None
    active: bool = True
    subscription: SubscriptionCreate
    device: DeviceCreate | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = None
    notes: str | None = None
    active: bool | None = None


class ClientListItem(BaseModel):
    id: UUID
    name: str
    email: str | None
    phone: str | None
    active: bool
    status: SubscriptionStatus
    expires_at: datetime | None
    device_count: int
    last_access_at: datetime | None
    xtream_username: str | None = None


class ClientDetail(BaseModel):
    id: UUID
    name: str
    email: str | None
    phone: str | None
    notes: str | None
    active: bool
    created_at: datetime
    updated_at: datetime
    status: SubscriptionStatus
    current_subscription: SubscriptionOut | None
    devices: list[DeviceOut]


class DashboardStats(BaseModel):
    clients: dict[str, int]
    subscriptions: dict[str, int]
    devices: dict[str, int]


class SourceTestResult(BaseModel):
    m3u: dict
    epg: dict | None = None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    details: str | None
    ip_address: str | None
    created_at: datetime


class SetupPageOut(BaseModel):
    client_name: str
    status: SubscriptionStatus
    expires_at: datetime
    m3u_url: str
    epg_url: str
    xtream_server: str
    xtream_username: str
    xtream_password: str


class SettingsOut(BaseModel):
    public_base_url: str
    setup_page_enabled: bool
    m3u_cache_seconds: int
    epg_cache_seconds: int
    access_log_retention_days: int
    expiring_soon_days: int

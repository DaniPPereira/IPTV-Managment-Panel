from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.database import get_db
from app.core.security import client_ip
from app.models import AdminUser
from app.schemas import (
    ClientCreate,
    ClientDetail,
    ClientListItem,
    ClientUpdate,
    DeviceCreate,
    DeviceOut,
    Paginated,
    SubscriptionCreate,
    SubscriptionOut,
)
from app.services.client import ClientService

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=Paginated[ClientListItem])
async def list_clients(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    status: str | None = Query(None, alias="status"),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> Paginated[ClientListItem]:
    _ = admin
    return await ClientService(db).list_clients(
        page=page, page_size=page_size, search=search, status_filter=status
    )


@router.post("", response_model=ClientDetail, status_code=201)
async def create_client(
    payload: ClientCreate,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> ClientDetail:
    return await ClientService(db).create_client(payload, admin_id=admin.id, ip=client_ip(request))


@router.get("/{client_id}", response_model=ClientDetail)
async def get_client(
    client_id: UUID,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> ClientDetail:
    _ = admin
    return await ClientService(db).get_client(client_id)


@router.patch("/{client_id}", response_model=ClientDetail)
async def update_client(
    client_id: UUID,
    payload: ClientUpdate,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> ClientDetail:
    return await ClientService(db).update_client(client_id, payload, admin_id=admin.id, ip=client_ip(request))


@router.delete("/{client_id}")
async def delete_client(
    client_id: UUID,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ClientService(db).soft_delete_client(client_id, admin_id=admin.id, ip=client_ip(request))
    return {"ok": True}


@router.post("/{client_id}/subscriptions", response_model=SubscriptionOut, status_code=201)
async def create_subscription(
    client_id: UUID,
    payload: SubscriptionCreate,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    return await ClientService(db).create_subscription(
        client_id, payload, admin_id=admin.id, ip=client_ip(request)
    )


@router.get("/{client_id}/devices", response_model=list[DeviceOut])
async def list_devices(
    client_id: UUID,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[DeviceOut]:
    _ = admin
    return await ClientService(db).list_devices(client_id)


@router.post("/{client_id}/devices", response_model=DeviceOut, status_code=201)
async def add_device(
    client_id: UUID,
    payload: DeviceCreate,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> DeviceOut:
    return await ClientService(db).add_device(client_id, payload, admin_id=admin.id, ip=client_ip(request))

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.database import get_db
from app.core.security import client_ip
from app.models import AdminUser
from app.schemas import (
    DeviceOut,
    DeviceUpdate,
    Paginated,
    RenewRequest,
    SourceTestResult,
    SubscriptionOut,
    SubscriptionUpdate,
)
from app.services.client import ClientService

router = APIRouter(tags=["subscriptions-devices"])


@router.get("/subscriptions", response_model=Paginated[SubscriptionOut])
async def list_subscriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> Paginated[SubscriptionOut]:
    _ = admin
    return await ClientService(db).list_subscriptions(page=page, page_size=page_size)


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionOut)
async def get_subscription(
    subscription_id: UUID,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    _ = admin
    return await ClientService(db).get_subscription(subscription_id)


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionOut)
async def update_subscription(
    subscription_id: UUID,
    payload: SubscriptionUpdate,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    return await ClientService(db).update_subscription(
        subscription_id, payload, admin_id=admin.id, ip=client_ip(request)
    )


@router.post("/subscriptions/{subscription_id}/renew", response_model=SubscriptionOut)
async def renew_subscription(
    subscription_id: UUID,
    payload: RenewRequest,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    return await ClientService(db).renew(subscription_id, payload, admin_id=admin.id, ip=client_ip(request))


@router.post("/subscriptions/{subscription_id}/disable", response_model=SubscriptionOut)
async def disable_subscription(
    subscription_id: UUID,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    return await ClientService(db).set_subscription_active(
        subscription_id, False, admin_id=admin.id, ip=client_ip(request)
    )


@router.post("/subscriptions/{subscription_id}/enable", response_model=SubscriptionOut)
async def enable_subscription(
    subscription_id: UUID,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    return await ClientService(db).set_subscription_active(
        subscription_id, True, admin_id=admin.id, ip=client_ip(request)
    )


@router.post("/subscriptions/{subscription_id}/regenerate-token", response_model=SubscriptionOut)
async def regenerate_token(
    subscription_id: UUID,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    return await ClientService(db).regenerate_token(
        subscription_id, admin_id=admin.id, ip=client_ip(request)
    )


@router.post("/subscriptions/{subscription_id}/regenerate-xtream-password", response_model=SubscriptionOut)
async def regenerate_xtream_password(
    subscription_id: UUID,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    return await ClientService(db).regenerate_xtream_password(
        subscription_id, admin_id=admin.id, ip=client_ip(request)
    )


@router.post("/subscriptions/{subscription_id}/test-source", response_model=SourceTestResult)
async def test_source(
    subscription_id: UUID,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> SourceTestResult:
    _ = admin
    return await ClientService(db).test_source(subscription_id)


@router.post("/subscriptions/{subscription_id}/refresh-playlist")
async def refresh_playlist(
    subscription_id: UUID,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ = admin
    return await ClientService(db).refresh_playlist(subscription_id)


@router.post("/subscriptions/{subscription_id}/refresh-epg")
async def refresh_epg(
    subscription_id: UUID,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ = admin
    return await ClientService(db).refresh_epg(subscription_id)


@router.get("/devices", response_model=Paginated[DeviceOut])
async def list_all_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> Paginated[DeviceOut]:
    _ = admin
    return await ClientService(db).list_all_devices(page=page, page_size=page_size, search=search)


@router.patch("/devices/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: UUID,
    payload: DeviceUpdate,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> DeviceOut:
    return await ClientService(db).update_device(device_id, payload, admin_id=admin.id, ip=client_ip(request))


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: UUID,
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ClientService(db).delete_device(device_id, admin_id=admin.id, ip=client_ip(request))
    return {"ok": True}

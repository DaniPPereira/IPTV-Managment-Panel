from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.config import get_settings
from app.core.database import get_db
from app.models import AdminUser
from app.repositories import AuditRepository
from app.schemas import AuditLogOut, DashboardStats, Paginated, SettingsOut
from app.services.client import ClientService

router = APIRouter(tags=["admin-misc"])


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> DashboardStats:
    _ = admin
    return await ClientService(db).dashboard()


@router.get("/audit-logs", response_model=Paginated[AuditLogOut])
async def audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> Paginated[AuditLogOut]:
    _ = admin
    rows, total = await AuditRepository(db).list(page=page, page_size=page_size)
    pages = ceil(total / page_size) if page_size else 1
    return Paginated(
        items=[AuditLogOut.model_validate(r) for r in rows],
        page=page,
        page_size=page_size,
        total=total,
        pages=pages or 1,
    )


@router.get("/settings", response_model=SettingsOut)
async def settings(admin: AdminUser = Depends(get_current_admin)) -> SettingsOut:
    _ = admin
    s = get_settings()
    return SettingsOut(
        public_base_url=s.public_base_url,
        stalker_portal_url=s.resolved_stalker_portal_url,
        setup_page_enabled=s.setup_page_enabled,
        m3u_cache_seconds=s.m3u_cache_seconds,
        epg_cache_seconds=s.epg_cache_seconds,
        access_log_retention_days=s.access_log_retention_days,
        expiring_soon_days=s.expiring_soon_days,
        stalker_allow_multiple_devices=s.stalker_allow_multiple_devices,
        stalker_create_link_prefix=s.stalker_create_link_prefix,
    )

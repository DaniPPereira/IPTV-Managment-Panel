from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from math import ceil
from uuid import UUID

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Client, Device, Subscription, SubscriptionStatus
from app.repositories import ClientRepository, DeviceRepository, SubscriptionRepository
from app.schemas import (
    ClientCreate,
    ClientDetail,
    ClientListItem,
    ClientUpdate,
    DashboardStats,
    DeviceCreate,
    DeviceOut,
    DeviceUpdate,
    Paginated,
    RenewRequest,
    SourceTestResult,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
)
from app.services.audit import AuditService
from app.services.encryption import EncryptionService
from app.services.playlist import PlaylistService
from app.utils.mac import normalize_mac
from app.utils.status import ensure_utc, status_for_subscription
from app.utils.ssrf import SSRFError, validate_public_url


def _slug_username(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_") or "user"
    return f"{base[:20]}_{secrets.token_hex(3)}"


class ClientService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.clients = ClientRepository(db)
        self.subscriptions = SubscriptionRepository(db)
        self.devices = DeviceRepository(db)
        self.encryption = EncryptionService()
        self.audit = AuditService(db)
        self.settings = get_settings()
        self.playlist = PlaylistService(db)

    def _public_urls(self, token: str) -> tuple[str, str, str]:
        base = self.settings.public_base_url.rstrip("/")
        return f"{base}/m3u/{token}", f"{base}/epg/{token}", f"{base}/setup/{token}"

    def _subscription_out(self, sub: Subscription, *, reveal_sources: bool = False) -> SubscriptionOut:
        m3u_url, epg_url, setup_url = self._public_urls(sub.public_token)
        source_m3u = self.encryption.decrypt(sub.source_m3u_url_encrypted) if reveal_sources else None
        source_epg = None
        if reveal_sources and sub.source_epg_url_encrypted:
            source_epg = self.encryption.decrypt(sub.source_epg_url_encrypted)
        return SubscriptionOut(
            id=sub.id,
            client_id=sub.client_id,
            active=sub.active,
            starts_at=sub.starts_at,
            expires_at=sub.expires_at,
            max_devices=sub.max_devices,
            public_token=sub.public_token,
            xtream_username=sub.xtream_username,
            xtream_password=sub.xtream_password,
            last_access_at=sub.last_access_at,
            status=status_for_subscription(sub),
            m3u_url=m3u_url,
            epg_url=epg_url,
            setup_url=setup_url,
            xtream_server=self.settings.public_base_url.rstrip("/"),
            source_m3u_url=source_m3u,
            source_epg_url=source_epg,
            created_at=sub.created_at,
            updated_at=sub.updated_at,
        )

    def _current_subscription(self, client: Client) -> Subscription | None:
        if not client.subscriptions:
            return None
        sorted_subs = sorted(client.subscriptions, key=lambda s: s.expires_at, reverse=True)
        for sub in sorted_subs:
            if sub.active:
                return sub
        return sorted_subs[0]

    async def dashboard(self) -> DashboardStats:
        now = datetime.now(timezone.utc)
        client_rows, _ = await self.clients.list(
            page=1, page_size=10_000, search=None, status_filter=None, now=now, expiring_soon_days=7
        )
        total_clients = len(client_rows)
        active_clients = sum(1 for c in client_rows if c.active)
        disabled_clients = total_clients - active_clients

        subs = list((await self.db.execute(select(Subscription))).scalars().all())
        client_map = {c.id: c for c in client_rows}
        active_subs = expired = exp7 = exp30 = 0
        for sub in subs:
            client = client_map.get(sub.client_id)
            if not client or not client.active or not sub.active:
                continue
            if sub.expires_at <= now:
                expired += 1
            else:
                active_subs += 1
                if sub.expires_at <= now + timedelta(days=7):
                    exp7 += 1
                if sub.expires_at <= now + timedelta(days=30):
                    exp30 += 1

        devices_total = int(await self.db.scalar(select(func.count()).select_from(Device)) or 0)
        devices_active = int(
            await self.db.scalar(select(func.count()).select_from(Device).where(Device.active.is_(True))) or 0
        )
        return DashboardStats(
            clients={"total": total_clients, "active": active_clients, "disabled": disabled_clients},
            subscriptions={
                "active": active_subs,
                "expired": expired,
                "expiring_7_days": exp7,
                "expiring_30_days": exp30,
            },
            devices={"total": devices_total, "active": devices_active},
        )

    async def list_clients(
        self, *, page: int, page_size: int, search: str | None, status_filter: str | None
    ) -> Paginated[ClientListItem]:
        now = datetime.now(timezone.utc)
        rows, total = await self.clients.list(
            page=page,
            page_size=page_size,
            search=search,
            status_filter=status_filter,
            now=now,
            expiring_soon_days=self.settings.expiring_soon_days,
        )
        items: list[ClientListItem] = []
        for client in rows:
            sub = self._current_subscription(client)
            items.append(
                ClientListItem(
                    id=client.id,
                    name=client.name,
                    email=client.email,
                    phone=client.phone,
                    active=client.active,
                    status=status_for_subscription(sub, client) if sub else SubscriptionStatus.DISABLED,
                    expires_at=sub.expires_at if sub else None,
                    device_count=len(client.devices),
                    last_access_at=sub.last_access_at if sub else None,
                    xtream_username=sub.xtream_username if sub else None,
                )
            )
        pages = ceil(total / page_size) if page_size else 1
        return Paginated(items=items, page=page, page_size=page_size, total=total, pages=pages or 1)

    def _validate_source_urls(self, m3u: str, epg: str | None) -> None:
        try:
            validate_public_url(m3u, allow_private=self.settings.allow_private_urls)
            if epg:
                validate_public_url(epg, allow_private=self.settings.allow_private_urls)
        except SSRFError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    async def create_client(
        self, data: ClientCreate, *, admin_id: UUID | None, ip: str | None
    ) -> ClientDetail:
        self._validate_source_urls(data.subscription.source_m3u_url, data.subscription.source_epg_url)
        now = datetime.now(timezone.utc)
        starts_at = data.subscription.starts_at or now
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
        expires_at = data.subscription.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        client = Client(
            name=data.name,
            email=str(data.email) if data.email else None,
            phone=data.phone,
            notes=data.notes,
            active=data.active,
        )
        await self.clients.create(client)

        token = Subscription.generate_token()
        sub = Subscription(
            client_id=client.id,
            source_m3u_url_encrypted=self.encryption.encrypt(data.subscription.source_m3u_url),
            source_epg_url_encrypted=self.encryption.encrypt(data.subscription.source_epg_url)
            if data.subscription.source_epg_url
            else None,
            active=data.subscription.active,
            starts_at=starts_at,
            expires_at=expires_at,
            max_devices=data.subscription.max_devices,
            public_token=token,
            xtream_username=_slug_username(data.name),
            xtream_password=Subscription.generate_xtream_password(),
        )
        await self.subscriptions.create(sub)

        if data.device:
            await self._create_device(client, sub, data.device)

        await self.audit.log(
            action="CLIENT_CREATED",
            entity_type="client",
            entity_id=client.id,
            admin_user_id=admin_id,
            ip_address=ip,
            details={"name": client.name},
        )
        refreshed = await self.clients.get(client.id)
        assert refreshed is not None
        return await self.get_client(refreshed.id, reveal_sources=True)

    async def get_client(self, client_id: UUID, *, reveal_sources: bool = True) -> ClientDetail:
        client = await self.clients.get(client_id)
        if not client:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
        sub = self._current_subscription(client)
        return ClientDetail(
            id=client.id,
            name=client.name,
            email=client.email,
            phone=client.phone,
            notes=client.notes,
            active=client.active,
            created_at=client.created_at,
            updated_at=client.updated_at,
            status=status_for_subscription(sub, client) if sub else SubscriptionStatus.DISABLED,
            current_subscription=self._subscription_out(sub, reveal_sources=reveal_sources) if sub else None,
            devices=[DeviceOut.model_validate(d) for d in client.devices],
        )

    async def update_client(
        self, client_id: UUID, data: ClientUpdate, *, admin_id: UUID | None, ip: str | None
    ) -> ClientDetail:
        client = await self.clients.get(client_id)
        if not client:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "email" and value is not None:
                value = str(value)
            setattr(client, field, value)
        await self.audit.log(
            action="CLIENT_UPDATED" if data.active is not False else "CLIENT_DISABLED",
            entity_type="client",
            entity_id=client.id,
            admin_user_id=admin_id,
            ip_address=ip,
        )
        return await self.get_client(client.id)

    async def disable_client(self, client_id: UUID, *, admin_id: UUID | None, ip: str | None) -> ClientDetail:
        return await self.update_client(
            client_id, ClientUpdate(active=False), admin_id=admin_id, ip=ip
        )

    async def soft_delete_client(self, client_id: UUID, *, admin_id: UUID | None, ip: str | None) -> None:
        await self.disable_client(client_id, admin_id=admin_id, ip=ip)

    async def create_subscription(
        self, client_id: UUID, data: SubscriptionCreate, *, admin_id: UUID | None, ip: str | None
    ) -> SubscriptionOut:
        client = await self.clients.get(client_id)
        if not client:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
        self._validate_source_urls(data.source_m3u_url, data.source_epg_url)
        now = datetime.now(timezone.utc)
        starts_at = data.starts_at or now
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
        expires_at = data.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        # Deactivate previous active subscriptions to keep one current
        for existing in client.subscriptions:
            if existing.active:
                existing.active = False
        sub = Subscription(
            client_id=client.id,
            source_m3u_url_encrypted=self.encryption.encrypt(data.source_m3u_url),
            source_epg_url_encrypted=self.encryption.encrypt(data.source_epg_url) if data.source_epg_url else None,
            active=data.active,
            starts_at=starts_at,
            expires_at=expires_at,
            max_devices=data.max_devices,
            public_token=Subscription.generate_token(),
            xtream_username=_slug_username(client.name),
            xtream_password=Subscription.generate_xtream_password(),
        )
        await self.subscriptions.create(sub)
        await self.audit.log(
            action="SUBSCRIPTION_CREATED",
            entity_type="subscription",
            entity_id=sub.id,
            admin_user_id=admin_id,
            ip_address=ip,
        )
        return self._subscription_out(sub, reveal_sources=True)

    async def get_subscription(self, subscription_id: UUID) -> SubscriptionOut:
        sub = await self.subscriptions.get(subscription_id)
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
        return self._subscription_out(sub, reveal_sources=True)

    async def update_subscription(
        self, subscription_id: UUID, data: SubscriptionUpdate, *, admin_id: UUID | None, ip: str | None
    ) -> SubscriptionOut:
        sub = await self.subscriptions.get(subscription_id)
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
        payload = data.model_dump(exclude_unset=True)
        if "source_m3u_url" in payload:
            self._validate_source_urls(payload["source_m3u_url"], payload.get("source_epg_url"))
            sub.source_m3u_url_encrypted = self.encryption.encrypt(payload.pop("source_m3u_url"))
            self.playlist.invalidate_cache(str(sub.id), "m3u")
        if "source_epg_url" in payload:
            epg = payload.pop("source_epg_url")
            if epg:
                try:
                    validate_public_url(epg, allow_private=self.settings.allow_private_urls)
                except SSRFError as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
                sub.source_epg_url_encrypted = self.encryption.encrypt(epg)
            else:
                sub.source_epg_url_encrypted = None
            self.playlist.invalidate_cache(str(sub.id), "epg")
        for field, value in payload.items():
            if value is not None and field in {"starts_at", "expires_at"} and value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            setattr(sub, field, value)
        await self.audit.log(
            action="SUBSCRIPTION_UPDATED",
            entity_type="subscription",
            entity_id=sub.id,
            admin_user_id=admin_id,
            ip_address=ip,
        )
        return self._subscription_out(sub, reveal_sources=True)

    async def renew(
        self, subscription_id: UUID, data: RenewRequest, *, admin_id: UUID | None, ip: str | None
    ) -> SubscriptionOut:
        sub = await self.subscriptions.get(subscription_id)
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
        now = datetime.now(timezone.utc)
        base = ensure_utc(sub.expires_at)
        if base <= now:
            base = now
        if data.months:
            sub.expires_at = base + relativedelta(months=data.months)
        else:
            sub.expires_at = base + timedelta(days=data.days or 0)
        sub.active = True
        client = sub.__dict__.get("client")
        if client is not None:
            client.active = True
        await self.audit.log(
            action="SUBSCRIPTION_RENEWED",
            entity_type="subscription",
            entity_id=sub.id,
            admin_user_id=admin_id,
            ip_address=ip,
            details=data.model_dump(),
        )
        return self._subscription_out(sub, reveal_sources=True)

    async def set_subscription_active(
        self, subscription_id: UUID, active: bool, *, admin_id: UUID | None, ip: str | None
    ) -> SubscriptionOut:
        sub = await self.subscriptions.get(subscription_id)
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
        sub.active = active
        await self.audit.log(
            action="SUBSCRIPTION_ENABLED" if active else "SUBSCRIPTION_DISABLED",
            entity_type="subscription",
            entity_id=sub.id,
            admin_user_id=admin_id,
            ip_address=ip,
        )
        return self._subscription_out(sub, reveal_sources=True)

    async def regenerate_token(
        self, subscription_id: UUID, *, admin_id: UUID | None, ip: str | None
    ) -> SubscriptionOut:
        sub = await self.subscriptions.get(subscription_id)
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
        sub.public_token = Subscription.generate_token()
        await self.audit.log(
            action="ACCESS_TOKEN_REGENERATED",
            entity_type="subscription",
            entity_id=sub.id,
            admin_user_id=admin_id,
            ip_address=ip,
        )
        return self._subscription_out(sub, reveal_sources=True)

    async def regenerate_xtream_password(
        self, subscription_id: UUID, *, admin_id: UUID | None, ip: str | None
    ) -> SubscriptionOut:
        sub = await self.subscriptions.get(subscription_id)
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
        sub.xtream_password = Subscription.generate_xtream_password()
        await self.audit.log(
            action="XTREAM_PASSWORD_REGENERATED",
            entity_type="subscription",
            entity_id=sub.id,
            admin_user_id=admin_id,
            ip_address=ip,
        )
        return self._subscription_out(sub, reveal_sources=True)

    async def test_source(self, subscription_id: UUID) -> SourceTestResult:
        return await self.playlist.test_source(subscription_id)

    async def refresh_playlist(self, subscription_id: UUID) -> dict:
        return await self.playlist.refresh(subscription_id, kind="m3u")

    async def refresh_epg(self, subscription_id: UUID) -> dict:
        return await self.playlist.refresh(subscription_id, kind="epg")

    async def _create_device(self, client: Client, sub: Subscription | None, data: DeviceCreate) -> Device:
        mac = normalize_mac(data.mac_address) if data.mac_address else None
        if mac:
            existing = await self.devices.get_by_mac(mac)
            if existing and existing.active:
                raise HTTPException(status_code=400, detail="MAC address already in use by an active device")
        active_count = await self.devices.count_active_for_client(client.id)
        max_devices = sub.max_devices if sub else 50
        if data.active and active_count >= max_devices:
            raise HTTPException(status_code=400, detail="Maximum devices reached for this subscription")
        device = Device(
            client_id=client.id,
            subscription_id=sub.id if sub else data.subscription_id,
            name=data.name,
            device_type=data.device_type,
            mac_address=mac,
            device_identifier=data.device_identifier,
            active=data.active,
        )
        return await self.devices.create(device)

    async def list_devices(self, client_id: UUID) -> list[DeviceOut]:
        devices = await self.devices.list_for_client(client_id)
        return [DeviceOut.model_validate(d) for d in devices]

    async def add_device(
        self, client_id: UUID, data: DeviceCreate, *, admin_id: UUID | None, ip: str | None
    ) -> DeviceOut:
        client = await self.clients.get(client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        sub = self._current_subscription(client)
        device = await self._create_device(client, sub, data)
        await self.audit.log(
            action="DEVICE_CREATED",
            entity_type="device",
            entity_id=device.id,
            admin_user_id=admin_id,
            ip_address=ip,
        )
        return DeviceOut.model_validate(device)

    async def update_device(
        self, device_id: UUID, data: DeviceUpdate, *, admin_id: UUID | None, ip: str | None
    ) -> DeviceOut:
        device = await self.devices.get(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        payload = data.model_dump(exclude_unset=True)
        if "mac_address" in payload:
            mac = payload["mac_address"]
            payload["mac_address"] = normalize_mac(mac) if mac else None
            if payload["mac_address"]:
                existing = await self.devices.get_by_mac(payload["mac_address"])
                if existing and existing.id != device.id and existing.active:
                    raise HTTPException(status_code=400, detail="MAC address already in use")
        for field, value in payload.items():
            setattr(device, field, value)
        await self.audit.log(
            action="DEVICE_UPDATED",
            entity_type="device",
            entity_id=device.id,
            admin_user_id=admin_id,
            ip_address=ip,
        )
        return DeviceOut.model_validate(device)

    async def delete_device(self, device_id: UUID, *, admin_id: UUID | None, ip: str | None) -> None:
        device = await self.devices.get(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        await self.devices.delete(device)
        await self.audit.log(
            action="DEVICE_REMOVED",
            entity_type="device",
            entity_id=device_id,
            admin_user_id=admin_id,
            ip_address=ip,
        )

    async def list_all_devices(self, *, page: int, page_size: int, search: str | None) -> Paginated[DeviceOut]:
        rows, total = await self.devices.list_paginated(page=page, page_size=page_size, search=search)
        pages = ceil(total / page_size) if page_size else 1
        return Paginated(
            items=[DeviceOut.model_validate(d) for d in rows],
            page=page,
            page_size=page_size,
            total=total,
            pages=pages or 1,
        )

    async def list_subscriptions(self, *, page: int, page_size: int) -> Paginated[SubscriptionOut]:
        rows, total = await self.subscriptions.list_paginated(page=page, page_size=page_size)
        pages = ceil(total / page_size) if page_size else 1
        return Paginated(
            items=[self._subscription_out(s, reveal_sources=False) for s in rows],
            page=page,
            page_size=page_size,
            total=total,
            pages=pages or 1,
        )

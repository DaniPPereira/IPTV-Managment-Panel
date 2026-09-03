from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AccessLog, AdminUser, AuditLog, Client, Device, Subscription


class AdminRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def count(self) -> int:
        result = await self.db.scalar(select(func.count()).select_from(AdminUser))
        return int(result or 0)

    async def get_by_username(self, username: str) -> AdminUser | None:
        result = await self.db.execute(select(AdminUser).where(AdminUser.username == username))
        return result.scalar_one_or_none()

    async def get_by_id(self, admin_id: UUID) -> AdminUser | None:
        result = await self.db.execute(select(AdminUser).where(AdminUser.id == admin_id))
        return result.scalar_one_or_none()

    async def create(self, admin: AdminUser) -> AdminUser:
        self.db.add(admin)
        await self.db.flush()
        return admin


class ClientRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, client_id: UUID) -> Client | None:
        result = await self.db.execute(
            select(Client)
            .options(
                selectinload(Client.subscriptions),
                selectinload(Client.devices),
            )
            .where(Client.id == client_id)
        )
        return result.scalar_one_or_none()

    async def create(self, client: Client) -> Client:
        self.db.add(client)
        await self.db.flush()
        return client

    def _search_filter(self, search: str | None):
        if not search:
            return None
        term = f"%{search.strip()}%"
        return or_(
            Client.name.ilike(term),
            Client.email.ilike(term),
            Client.phone.ilike(term),
            Client.subscriptions.any(Subscription.xtream_username.ilike(term)),
            Client.devices.any(Device.mac_address.ilike(term)),
        )

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        status_filter: str | None = None,
        now: datetime,
        expiring_soon_days: int,
    ) -> tuple[list[Client], int]:
        query: Select = (
            select(Client)
            .options(selectinload(Client.subscriptions), selectinload(Client.devices))
            .order_by(Client.created_at.desc())
        )
        filters = []
        search_filter = self._search_filter(search)
        if search_filter is not None:
            filters.append(search_filter)

        if status_filter == "disabled":
            filters.append(Client.active.is_(False))
        elif status_filter in {"active", "expired", "expiring_7", "expiring_30"}:
            filters.append(Client.active.is_(True))

        if filters:
            query = query.where(and_(*filters))

        # Load then filter status in Python for clarity on current subscription semantics
        result = await self.db.execute(query)
        clients = list(result.scalars().unique().all())

        def current_sub(c: Client) -> Subscription | None:
            if not c.subscriptions:
                return None
            # Prefer active non-expired, else latest by expires_at
            sorted_subs = sorted(c.subscriptions, key=lambda s: s.expires_at, reverse=True)
            for sub in sorted_subs:
                if sub.active:
                    return sub
            return sorted_subs[0]

        filtered: list[Client] = []
        for client in clients:
            sub = current_sub(client)
            if status_filter in {None, "", "all"}:
                filtered.append(client)
                continue
            if status_filter == "disabled" and not client.active:
                filtered.append(client)
            elif status_filter == "active" and client.active and sub and sub.active and sub.expires_at > now:
                filtered.append(client)
            elif status_filter == "expired" and client.active and sub and sub.expires_at <= now:
                filtered.append(client)
            elif status_filter == "expiring_7" and client.active and sub and sub.active and now < sub.expires_at <= now + timedelta(days=7):
                filtered.append(client)
            elif status_filter == "expiring_30" and client.active and sub and sub.active and now < sub.expires_at <= now + timedelta(days=30):
                filtered.append(client)

        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        return filtered[start:end], total


class SubscriptionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, subscription_id: UUID) -> Subscription | None:
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.client), selectinload(Subscription.devices))
            .where(Subscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_by_token(self, token: str) -> Subscription | None:
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.client))
            .where(Subscription.public_token == token)
        )
        return result.scalar_one_or_none()

    async def get_by_xtream(self, username: str, password: str) -> Subscription | None:
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.client))
            .where(
                Subscription.xtream_username == username,
                Subscription.xtream_password == password,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, subscription: Subscription) -> Subscription:
        self.db.add(subscription)
        await self.db.flush()
        return subscription

    async def list_paginated(self, *, page: int, page_size: int) -> tuple[list[Subscription], int]:
        total = int(await self.db.scalar(select(func.count()).select_from(Subscription)) or 0)
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.client))
            .order_by(Subscription.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total


class DeviceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, device_id: UUID) -> Device | None:
        result = await self.db.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()

    async def list_for_client(self, client_id: UUID) -> list[Device]:
        result = await self.db.execute(
            select(Device).where(Device.client_id == client_id).order_by(Device.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_paginated(self, *, page: int, page_size: int, search: str | None = None) -> tuple[list[Device], int]:
        query = select(Device).order_by(Device.created_at.desc())
        count_query = select(func.count()).select_from(Device)
        if search:
            term = f"%{search.strip()}%"
            filt = or_(Device.name.ilike(term), Device.mac_address.ilike(term), Device.device_identifier.ilike(term))
            query = query.where(filt)
            count_query = count_query.where(filt)
        total = int(await self.db.scalar(count_query) or 0)
        result = await self.db.execute(query.offset((page - 1) * page_size).limit(page_size))
        return list(result.scalars().all()), total

    async def get_by_mac(self, mac: str) -> Device | None:
        result = await self.db.execute(select(Device).where(Device.mac_address == mac))
        return result.scalar_one_or_none()

    async def count_active_for_client(self, client_id: UUID) -> int:
        result = await self.db.scalar(
            select(func.count()).select_from(Device).where(Device.client_id == client_id, Device.active.is_(True))
        )
        return int(result or 0)

    async def create(self, device: Device) -> Device:
        self.db.add(device)
        await self.db.flush()
        return device

    async def delete(self, device: Device) -> None:
        await self.db.delete(device)


class AuditRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, log: AuditLog) -> AuditLog:
        self.db.add(log)
        await self.db.flush()
        return log

    async def list(self, *, page: int, page_size: int) -> tuple[list[AuditLog], int]:
        total = int(await self.db.scalar(select(func.count()).select_from(AuditLog)) or 0)
        result = await self.db.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total


class AccessLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, log: AccessLog) -> AccessLog:
        self.db.add(log)
        await self.db.flush()
        return log

    async def purge_older_than(self, cutoff: datetime) -> int:
        result = await self.db.execute(select(AccessLog).where(AccessLog.created_at < cutoff))
        rows = list(result.scalars().all())
        for row in rows:
            await self.db.delete(row)
        return len(rows)

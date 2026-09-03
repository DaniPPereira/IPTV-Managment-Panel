from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import AccessLog
from app.providers.m3u import M3UProvider
from app.repositories import AccessLogRepository, SubscriptionRepository
from app.schemas import SourceTestResult
from app.services.cache import FileCache
from app.services.encryption import EncryptionService
from app.utils.status import status_for_subscription
from app.models import SubscriptionStatus

logger = logging.getLogger(__name__)


class PlaylistService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.subscriptions = SubscriptionRepository(db)
        self.access_logs = AccessLogRepository(db)
        self.encryption = EncryptionService()
        self.cache = FileCache()
        self.provider = M3UProvider()
        self.settings = get_settings()

    def invalidate_cache(self, subscription_id: str, kind: str) -> None:
        self.cache.invalidate(subscription_id, kind)

    async def _assert_access(self, subscription_id: UUID | None = None, token: str | None = None):
        if token:
            sub = await self.subscriptions.get_by_token(token)
        elif subscription_id:
            sub = await self.subscriptions.get(subscription_id)
        else:
            sub = None
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        st = status_for_subscription(sub)
        if st == SubscriptionStatus.DISABLED:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access disabled")
        if st == SubscriptionStatus.EXPIRED:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription expired")
        return sub

    async def _record_access(self, sub, *, endpoint: str, ip: str | None, user_agent: str | None) -> None:
        sub.last_access_at = datetime.now(timezone.utc)
        await self.access_logs.create(
            AccessLog(
                subscription_id=sub.id,
                endpoint=endpoint,
                ip=ip,
                user_agent=user_agent,
            )
        )

    async def get_m3u_by_token(
        self, token: str, *, ip: str | None = None, user_agent: str | None = None, force_refresh: bool = False
    ) -> tuple[bytes, dict]:
        sub = await self._assert_access(token=token)
        content, meta = await self._get_content(sub, kind="m3u", force_refresh=force_refresh)
        await self._record_access(sub, endpoint="m3u", ip=ip, user_agent=user_agent)
        logger.info(
            "playlist_requested",
            extra={
                "event": "playlist_requested",
                "subscription_id": str(sub.id),
                "status": 200,
                "duration_ms": meta.get("duration_ms"),
                "endpoint": "m3u",
                "ip": ip,
            },
        )
        return content, meta

    async def get_epg_by_token(
        self, token: str, *, ip: str | None = None, user_agent: str | None = None, force_refresh: bool = False
    ) -> tuple[bytes, dict]:
        sub = await self._assert_access(token=token)
        if not sub.source_epg_url_encrypted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EPG not configured")
        content, meta = await self._get_content(sub, kind="epg", force_refresh=force_refresh)
        await self._record_access(sub, endpoint="epg", ip=ip, user_agent=user_agent)
        logger.info(
            "epg_requested",
            extra={
                "event": "epg_requested",
                "subscription_id": str(sub.id),
                "status": 200,
                "duration_ms": meta.get("duration_ms"),
                "endpoint": "epg",
                "ip": ip,
            },
        )
        return content, meta

    async def get_m3u_by_xtream(
        self, username: str, password: str, *, ip: str | None = None, user_agent: str | None = None
    ) -> tuple[bytes, dict]:
        sub = await self.subscriptions.get_by_xtream(username, password)
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        st = status_for_subscription(sub)
        if st == SubscriptionStatus.DISABLED:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access disabled")
        if st == SubscriptionStatus.EXPIRED:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscription expired")
        content, meta = await self._get_content(sub, kind="m3u")
        await self._record_access(sub, endpoint="get.php", ip=ip, user_agent=user_agent)
        return content, meta

    async def player_api(self, username: str, password: str) -> dict:
        sub = await self.subscriptions.get_by_xtream(username, password)
        if not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        st = status_for_subscription(sub)
        status_label = "Active" if st in {SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRING_SOON} else "Expired"
        if st == SubscriptionStatus.DISABLED:
            status_label = "Disabled"
        base = self.settings.public_base_url.rstrip("/")
        from urllib.parse import urlparse

        parsed = urlparse(base)
        return {
            "user_info": {
                "username": sub.xtream_username,
                "status": status_label,
                "exp_date": str(int(sub.expires_at.timestamp())),
                "is_trial": "0",
                "active_cons": "0",
                "max_connections": str(sub.max_devices),
            },
            "server_info": {
                "url": parsed.hostname or base,
                "port": str(parsed.port or (443 if parsed.scheme == "https" else 80)),
                "https_port": "443",
                "server_protocol": parsed.scheme or "http",
            },
        }

    async def _get_content(self, sub, *, kind: str, force_refresh: bool = False) -> tuple[bytes, dict]:
        ttl = self.settings.m3u_cache_seconds if kind == "m3u" else self.settings.epg_cache_seconds
        key = str(sub.id)
        if not force_refresh:
            cached = self.cache.get(key, kind, ttl)
            if cached is not None:
                etag = hashlib.md5(cached).hexdigest()
                return cached, {
                    "content_type": "application/x-mpegURL" if kind == "m3u" else "application/xml",
                    "etag": etag,
                    "duration_ms": 0,
                    "cached": True,
                }

        if kind == "m3u":
            url = self.encryption.decrypt(sub.source_m3u_url_encrypted)
            result = await self.provider.get_playlist(url)
            default_ct = "application/x-mpegURL"
        else:
            if not sub.source_epg_url_encrypted:
                raise HTTPException(status_code=404, detail="EPG not configured")
            url = self.encryption.decrypt(sub.source_epg_url_encrypted)
            result = await self.provider.get_epg(url)
            default_ct = "application/xml"

        if result.http_status >= 400:
            raise HTTPException(status_code=502, detail=f"Upstream returned {result.http_status}")

        self.cache.set(key, kind, result.content)
        etag = result.etag or hashlib.md5(result.content).hexdigest()
        return result.content, {
            "content_type": result.content_type or default_ct,
            "etag": etag,
            "last_modified": result.last_modified,
            "duration_ms": result.duration_ms,
            "cached": False,
        }

    async def refresh(self, subscription_id: UUID, *, kind: str) -> dict:
        sub = await self.subscriptions.get(subscription_id)
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        self.invalidate_cache(str(sub.id), kind)
        content, meta = await self._get_content(sub, kind=kind, force_refresh=True)
        return {"success": True, "size": len(content), **meta}

    async def test_source(self, subscription_id: UUID) -> SourceTestResult:
        sub = await self.subscriptions.get(subscription_id)
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")

        async def probe(kind: str) -> dict:
            try:
                if kind == "m3u":
                    url = self.encryption.decrypt(sub.source_m3u_url_encrypted)
                    result = await self.provider.get_playlist(url)
                else:
                    if not sub.source_epg_url_encrypted:
                        return {"success": False, "error": "not_configured"}
                    url = self.encryption.decrypt(sub.source_epg_url_encrypted)
                    result = await self.provider.get_epg(url)
                return {
                    "success": 200 <= result.http_status < 400,
                    "http_status": result.http_status,
                    "size": len(result.content),
                    "content_type": result.content_type,
                    "duration_ms": result.duration_ms,
                }
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc)}

        m3u = await probe("m3u")
        epg = await probe("epg") if sub.source_epg_url_encrypted else None
        return SourceTestResult(m3u=m3u, epg=epg)

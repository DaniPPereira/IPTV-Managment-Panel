from __future__ import annotations

import hashlib
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, unquote

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models import Device, Subscription, SubscriptionStatus
from app.repositories import ClientRepository, DeviceRepository
from app.services.audit import AuditService
from app.services.playlist import PlaylistService
from app.utils.logging_mask import mask_sensitive_url
from app.utils.mac import normalize_mac
from app.utils.m3u_parse import M3UChannel, parse_m3u_channels
from app.utils.status import ensure_utc, status_for_subscription

logger = logging.getLogger(__name__)

_TOKEN_TO_MAC: dict[str, str] = {}
_MAC_TO_TOKEN: dict[str, str] = {}

MAC_IN_TEXT = re.compile(
    r"(?:mac[=:\s]+)([0-9A-Fa-f]{2}(?:[:\-][0-9A-Fa-f]{2}){5}|[0-9A-Fa-f]{12})",
    re.IGNORECASE,
)


class StalkerAuthError(Exception):
    def __init__(self, message: str = "Authorization failed.") -> None:
        self.message = message
        super().__init__(message)


@dataclass
class RequestMeta:
    mac: str | None = None
    device_id: str | None = None
    device_id2: str | None = None
    serial_number: str | None = None
    device_type: str | None = None
    signature: str | None = None
    stb_type: str | None = None
    hw_version: str | None = None
    app_name: str | None = None
    app_version: str | None = None
    user_agent: str | None = None
    x_user_agent: str | None = None
    ip: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class AuthorizedDevice:
    device: Device
    subscription: Subscription
    mac: str
    meta: RequestMeta


def stalker_js(payload: Any, *, text: str = "") -> dict[str, Any]:
    return {"js": payload, "text": text}


def stalker_error(message: str = "Authorization failed.") -> dict[str, Any]:
    return stalker_js([] if False else {}, text=message)


def _first(*values: str | None) -> str | None:
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return s or "genre"


async def _read_body_params(request: Request) -> dict[str, str]:
    """Best-effort extract of POST body params without consuming twice when possible."""
    out: dict[str, str] = {}
    if request.method.upper() != "POST":
        return out
    content_type = request.headers.get("content-type", "")
    try:
        if "application/json" in content_type:
            body = await request.json()
            if isinstance(body, dict):
                for k, v in body.items():
                    if v is not None:
                        out[str(k)] = str(v)
        elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            for k, v in form.items():
                out[str(k)] = str(v)
        else:
            raw = (await request.body()).decode("utf-8", errors="ignore")
            parsed = parse_qs(raw)
            for k, vals in parsed.items():
                if vals:
                    out[k] = vals[0]
    except Exception:  # noqa: BLE001
        pass
    return out


def extract_mac_candidates(request: Request, body: dict[str, str] | None = None) -> list[str]:
    candidates: list[str] = []
    body = body or {}

    for key in ("mac", "device_mac"):
        if request.query_params.get(key):
            candidates.append(unquote(request.query_params.get(key) or ""))
        if body.get(key):
            candidates.append(unquote(body[key]))

    if request.cookies.get("mac"):
        candidates.append(unquote(request.cookies.get("mac") or ""))

    raw_cookie = request.headers.get("cookie") or ""
    for part in raw_cookie.split(";"):
        part = part.strip()
        if part.lower().startswith("mac="):
            candidates.append(unquote(part.split("=", 1)[1].strip().strip('"')))

    for header_name in ("x-user-agent", "user-agent", "x-mac-address", "device-id", "x-device-id"):
        value = request.headers.get(header_name)
        if value:
            candidates.append(value)
            match = MAC_IN_TEXT.search(value)
            if match:
                candidates.append(match.group(1))

    return candidates


def normalize_mac_from_candidates(candidates: list[str]) -> str | None:
    for raw in candidates:
        try:
            return normalize_mac(raw)
        except ValueError:
            match = MAC_IN_TEXT.search(raw)
            if match:
                try:
                    return normalize_mac(match.group(1))
                except ValueError:
                    continue
    return None


def extract_token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (
        request.query_params.get("token")
        or request.headers.get("x-token")
        or request.cookies.get("token")
    )


def build_request_meta(request: Request, body: dict[str, str], mac: str | None) -> RequestMeta:
    q = request.query_params
    return RequestMeta(
        mac=mac,
        device_id=_first(q.get("device_id"), body.get("device_id"), request.headers.get("x-device-id")),
        device_id2=_first(q.get("device_id2"), body.get("device_id2"), q.get("signature"), body.get("signature")),
        serial_number=_first(
            q.get("serial_number"),
            body.get("serial_number"),
            request.headers.get("x-serial-number"),
        ),
        device_type=_first(q.get("device_type"), body.get("device_type"), q.get("stb_type"), body.get("stb_type")),
        signature=_first(q.get("signature"), body.get("signature")),
        stb_type=_first(q.get("stb_type"), body.get("stb_type")),
        hw_version=_first(q.get("hw_version"), body.get("hw_version")),
        app_name=_first(q.get("app_name"), body.get("app_name")),
        app_version=_first(q.get("app_version"), body.get("app_version")),
        user_agent=request.headers.get("user-agent"),
        x_user_agent=request.headers.get("x-user-agent"),
        ip=request.client.host if request.client else None,
    )


class StalkerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.devices = DeviceRepository(db)
        self.playlist = PlaylistService(db)
        self.audit = AuditService(db)
        self.settings = get_settings()

    async def get_device_by_mac(self, mac: str) -> Device | None:
        result = await self.db.execute(
            select(Device)
            .options(
                selectinload(Device.client),
                selectinload(Device.subscription).selectinload(Subscription.client),
            )
            .where(Device.mac_address == mac)
        )
        return result.scalar_one_or_none()

    def _log(
        self,
        *,
        event: str,
        type_: str | None = None,
        action: str | None = None,
        method: str | None = None,
        mac: str | None = None,
        mac_present: bool = False,
        device_id_present: bool = False,
        user_agent: str | None = None,
        ip: str | None = None,
        channel_id: str | None = None,
        create_link_resolved: bool | None = None,
        duration_ms: int | None = None,
        status: str = "ok",
    ) -> None:
        logger.info(
            event,
            extra={
                "event": event,
                "type": type_,
                "action": action,
                "method": method,
                "mac_present": mac_present,
                "subscription_id": None,
                "endpoint": "stalker",
                "ip": ip,
                "status": status,
                "duration_ms": duration_ms,
            },
        )
        # Structured fields beyond JsonFormatter defaults — keep message rich but safe
        safe_ua = (user_agent or "")[:120]
        logger.info(
            "stalker_meta mac=%s device_id_present=%s channel_id=%s resolved=%s ua=%s",
            mac or "-",
            device_id_present,
            channel_id or "-",
            create_link_resolved,
            safe_ua,
        )

    async def authorize(self, request: Request, body: dict[str, str] | None = None) -> AuthorizedDevice:
        body = body if body is not None else await _read_body_params(request)
        candidates = extract_mac_candidates(request, body)
        mac = normalize_mac_from_candidates(candidates)
        token = extract_token_from_request(request)
        if not mac and token:
            mac = _TOKEN_TO_MAC.get(token)

        meta = build_request_meta(request, body, mac)
        if not mac:
            self._log(
                event="stalker_auth_failed",
                method=request.method,
                mac_present=False,
                device_id_present=bool(meta.device_id or meta.device_id2 or meta.serial_number),
                user_agent=meta.user_agent,
                ip=meta.ip,
                status="fail",
            )
            raise StalkerAuthError("Authorization failed.")

        device = await self.get_device_by_mac(mac)
        if not device or not device.active:
            self._log(
                event="stalker_auth_failed",
                method=request.method,
                mac=mac,
                mac_present=True,
                ip=meta.ip,
                status="fail",
            )
            raise StalkerAuthError("Authorization failed.")

        client = device.__dict__.get("client")
        if client is None or not client.active:
            raise StalkerAuthError("Authorization failed.")

        sub = device.__dict__.get("subscription")
        if sub is None:
            full_client = await ClientRepository(self.db).get(client.id)
            if not full_client or not full_client.subscriptions:
                raise StalkerAuthError("Authorization failed.")
            sorted_subs = sorted(full_client.subscriptions, key=lambda s: s.expires_at, reverse=True)
            sub = next((s for s in sorted_subs if s.active), sorted_subs[0])

        st = status_for_subscription(sub, client)
        if st in {SubscriptionStatus.DISABLED, SubscriptionStatus.EXPIRED}:
            raise StalkerAuthError("Authorization failed.")

        # Metadata capture — never block on device_id changes
        incoming_id = _first(meta.device_id, meta.device_id2, meta.signature, meta.serial_number)
        if incoming_id:
            if not device.device_identifier:
                device.device_identifier = incoming_id[:255]
            elif device.device_identifier != incoming_id:
                device.last_seen_identifier = incoming_id[:255]
                await self.audit.log(
                    action="DEVICE_IDENTIFIER_CHANGED",
                    entity_type="device",
                    entity_id=device.id,
                    details={"previous": device.device_identifier, "seen": incoming_id[:64]},
                    ip_address=meta.ip,
                )
        if meta.serial_number and not device.serial_number:
            device.serial_number = meta.serial_number[:255]
        if meta.app_name:
            device.app_name = meta.app_name[:100]
        if meta.app_version:
            device.app_version = meta.app_version[:50]

        device.last_seen_at = datetime.now(timezone.utc)
        if meta.ip:
            device.last_ip = meta.ip
        ua = meta.x_user_agent or meta.user_agent
        if ua:
            device.last_user_agent = ua[:512]

        return AuthorizedDevice(device=device, subscription=sub, mac=mac, meta=meta)

    def issue_token(self, mac: str) -> str:
        old = _MAC_TO_TOKEN.get(mac)
        if old:
            _TOKEN_TO_MAC.pop(old, None)
        token = secrets.token_hex(16)
        _TOKEN_TO_MAC[token] = mac
        _MAC_TO_TOKEN[mac] = token
        return token

    def _format_stream_cmd(self, url: str) -> str:
        prefix = (self.settings.stalker_create_link_prefix or "none").lower().strip()
        if prefix == "ffmpeg":
            return f"ffmpeg {url}"
        if prefix == "auto":
            return f"auto {url}"
        return url

    async def handshake(self, request: Request, body: dict[str, str] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            auth = await self.authorize(request, body)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)
        token = self.issue_token(auth.mac)
        self._log(
            event="stalker_handshake",
            type_="stb",
            action="handshake",
            method=request.method,
            mac=auth.mac,
            mac_present=True,
            device_id_present=bool(auth.meta.device_id or auth.meta.device_id2),
            user_agent=auth.meta.user_agent,
            ip=auth.meta.ip,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return stalker_js({"token": token, "random": secrets.token_hex(8)})

    async def get_profile(self, request: Request, body: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            auth = await self.authorize(request, body)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)

        sub = auth.subscription
        client = auth.device.__dict__.get("client")
        expires = int(ensure_utc(sub.expires_at).timestamp())
        portal = self.settings.resolved_stalker_portal_url
        profile = {
            "id": str(auth.device.id),
            "name": (client.name if client else auth.device.name)[:64],
            "sname": auth.device.name,
            "mac": auth.mac,
            "status": 1,
            "expire_billing_date": expires,
            "phone": (client.phone if client else "") or "",
            "parent_password": "0000",
            "user_id": str(auth.device.client_id),
            "locale": "en_GB.utf8",
            "language": "en",
            "country": "US",
            "plasma_saving": "0",
            "ts_enabled": "0",
            "ts_enable_icon": "1",
            "device_id": (auth.device.device_identifier or auth.mac.replace(":", ""))[:64],
            "device_id2": (auth.device.device_identifier or auth.mac.replace(":", ""))[:64],
            "hw_version": auth.meta.hw_version or "1.7-BD-00",
            "stb_type": auth.meta.stb_type or "MAG254",
            "image_version": "218",
            "hd": "1",
            "main_api_url": f"{self.settings.public_base_url.rstrip('/')}/stalker_portal/server/load.php",
            "portal_url": portal,
            "update_url": "",
            "settings": {},
        }
        return stalker_js(profile)

    async def _channels_for(self, auth: AuthorizedDevice) -> list[M3UChannel]:
        content, _meta = await self.playlist._get_content(auth.subscription, kind="m3u")
        return parse_m3u_channels(content)

    def _build_genres(self, channels: list[M3UChannel]) -> tuple[list[dict[str, Any]], dict[str, str]]:
        groups: list[str] = []
        seen: set[str] = set()
        for ch in channels:
            key = (ch.group or "").strip() or "General"
            if key not in seen:
                seen.add(key)
                groups.append(key)

        if not groups:
            genres = [{"id": "1", "title": "All", "alias": "all"}]
            return genres, {"General": "1", "All": "1"}

        genres = [{"id": str(i), "title": title, "alias": _slug(title)} for i, title in enumerate(groups, start=1)]
        mapping = {title: str(i) for i, title in enumerate(groups, start=1)}
        return genres, mapping

    async def get_genres(self, request: Request, body: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            auth = await self.authorize(request, body)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)
        channels = await self._channels_for(auth)
        genres, _ = self._build_genres(channels)
        return stalker_js(genres)

    async def get_all_channels(self, request: Request, body: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            auth = await self.authorize(request, body)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)

        channels = await self._channels_for(auth)
        _genres, genre_map = self._build_genres(channels)
        data = []
        for ch in channels:
            group = (ch.group or "").strip() or "General"
            cmd = f"ffmpeg http://localhost/ch/{ch.id}"
            # Ensure opaque cmd never embeds provider credentials
            if self.settings.log_mask_provider_credentials and ("username=" in ch.url.lower() or "password=" in ch.url.lower()):
                pass  # still use opaque localhost cmd
            data.append(
                {
                    "id": str(ch.id),
                    "name": ch.name,
                    "number": str(ch.number),
                    "cmd": cmd,
                    "logo": ch.logo or "",
                    "tv_genre_id": genre_map.get(group, "1"),
                    "base_ch": "0",
                    "censored": "0",
                    "hd": "0",
                    "fav": "0",
                    "status": 1,
                    "lock": 0,
                    "cost": "0",
                    "xmltv_id": ch.tvg_id or "",
                }
            )

        await self.playlist._record_access(
            auth.subscription,
            endpoint="stalker_channels",
            ip=auth.meta.ip,
            user_agent=auth.meta.user_agent,
        )
        return stalker_js({"total_items": len(data), "max_page_items": len(data), "data": data})

    async def create_link(self, request: Request, body: dict[str, str] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        body = body if body is not None else await _read_body_params(request)
        try:
            auth = await self.authorize(request, body)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)

        channels = await self._channels_for(auth)
        by_id = {str(ch.id): ch for ch in channels}

        raw_cmd = _first(
            request.query_params.get("cmd"),
            body.get("cmd"),
        ) or ""
        cid = _first(
            request.query_params.get("channel_id"),
            request.query_params.get("ch_id"),
            body.get("channel_id"),
            body.get("ch_id"),
        ) or ""

        cleaned_cmd = raw_cmd.strip()
        for prefix in ("ffmpeg ", "auto "):
            if cleaned_cmd.lower().startswith(prefix):
                cleaned_cmd = cleaned_cmd[len(prefix) :].strip()

        target: M3UChannel | None = None
        if cid and cid in by_id:
            target = by_id[cid]

        if target is None and cleaned_cmd:
            m = re.search(r"/ch/(\d+)", cleaned_cmd)
            if m:
                target = by_id.get(m.group(1))

        if target is None and cleaned_cmd.isdigit():
            target = by_id.get(cleaned_cmd)

        if target is None and cleaned_cmd.startswith(("http://", "https://")):
            # Pass through real upstream URL; never leave localhost
            if "localhost" in cleaned_cmd.lower() or "127.0.0.1" in cleaned_cmd:
                return stalker_error("Channel not found.")
            await self.playlist._record_access(
                auth.subscription,
                endpoint="stalker_link",
                ip=auth.meta.ip,
                user_agent=auth.meta.user_agent,
            )
            self._log(
                event="stalker_create_link",
                type_="itv",
                action="create_link",
                method=request.method,
                mac=auth.mac,
                mac_present=True,
                channel_id=cid or "0",
                create_link_resolved=True,
                ip=auth.meta.ip,
                user_agent=auth.meta.user_agent,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return stalker_js(
                {
                    "id": cid or "0",
                    "cmd": self._format_stream_cmd(cleaned_cmd),
                    "streamer_id": 0,
                    "link_id": 0,
                    "load": 0,
                }
            )

        if target is None and raw_cmd:
            for ch in channels:
                ch_id = str(ch.id)
                if raw_cmd.endswith(f"/ch/{ch_id}") or cleaned_cmd.endswith(f"/ch/{ch_id}") or cleaned_cmd == ch.url:
                    target = ch
                    break

        if target is None:
            self._log(
                event="stalker_create_link",
                type_="itv",
                action="create_link",
                method=request.method,
                mac=auth.mac,
                mac_present=True,
                channel_id=cid or None,
                create_link_resolved=False,
                ip=auth.meta.ip,
                status="fail",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return stalker_error("Channel not found.")

        stream_url = target.url
        if "localhost" in stream_url.lower() or "127.0.0.1" in stream_url:
            return stalker_error("Channel not found.")

        await self.playlist._record_access(
            auth.subscription,
            endpoint="stalker_link",
            ip=auth.meta.ip,
            user_agent=auth.meta.user_agent,
        )
        target_id = str(target.id)
        self._log(
            event="stalker_create_link",
            type_="itv",
            action="create_link",
            method=request.method,
            mac=auth.mac,
            mac_present=True,
            channel_id=target_id,
            create_link_resolved=True,
            ip=auth.meta.ip,
            user_agent=auth.meta.user_agent,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        # Never log raw stream URL with credentials
        _ = mask_sensitive_url(stream_url)

        return stalker_js(
            {
                "id": target_id,
                "cmd": self._format_stream_cmd(stream_url),
                "streamer_id": 0,
                "link_id": int(hashlib.md5(target_id.encode()).hexdigest()[:6], 16) % 100000,
                "load": 0,
            }
        )

    async def get_short_epg(self, request: Request, body: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            await self.authorize(request, body)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)
        # Full XMLTV mapping not required for live TV; empty valid response
        return stalker_js([])

    async def get_epg_info(self, request: Request, body: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            await self.authorize(request, body)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)
        return stalker_js([])

    async def dispatch(self, request: Request) -> dict[str, Any]:
        body = await _read_body_params(request)
        type_ = (request.query_params.get("type") or body.get("type") or "").lower()
        action = (request.query_params.get("action") or body.get("action") or "").lower()

        if type_ == "stb" and action == "handshake":
            return await self.handshake(request, body)
        if type_ == "stb" and action == "get_profile":
            return await self.get_profile(request, body)
        if type_ == "itv" and action == "get_all_channels":
            return await self.get_all_channels(request, body)
        if type_ == "itv" and action == "create_link":
            return await self.create_link(request, body)
        if type_ == "itv" and action == "get_genres":
            return await self.get_genres(request, body)
        if type_ == "itv" and action == "get_short_epg":
            return await self.get_short_epg(request, body)
        if type_ == "itv" and action == "get_epg_info":
            return await self.get_epg_info(request, body)

        if type_ == "stb" and action in {"get_localization", "get_modules"}:
            try:
                await self.authorize(request, body)
            except StalkerAuthError as exc:
                return stalker_error(exc.message)
            return stalker_js({} if action == "get_localization" else [])

        return stalker_error("Action not supported.")

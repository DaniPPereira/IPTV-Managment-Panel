from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Device, Subscription, SubscriptionStatus
from app.repositories import DeviceRepository
from app.services.playlist import PlaylistService
from app.utils.mac import normalize_mac
from app.utils.m3u_parse import M3UChannel, parse_m3u_channels
from app.utils.status import ensure_utc, status_for_subscription


# In-process token store: token -> mac
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
class AuthorizedDevice:
    device: Device
    subscription: Subscription
    mac: str


def stalker_js(payload: Any, *, text: str = "") -> dict[str, Any]:
    return {"js": payload, "text": text}


def stalker_error(message: str = "Authorization failed.") -> dict[str, Any]:
    return stalker_js({}, text=message)


def extract_mac_from_request(request: Request) -> str | None:
    """Pull MAC from cookie / query / common STB headers."""
    candidates: list[str] = []

    qmac = request.query_params.get("mac")
    if qmac:
        candidates.append(unquote(qmac))

    cookie_mac = request.cookies.get("mac")
    if cookie_mac:
        candidates.append(unquote(cookie_mac))

    # Cookie header may contain mac= without being parsed (encoded forms)
    raw_cookie = request.headers.get("cookie") or ""
    for part in raw_cookie.split(";"):
        part = part.strip()
        if part.lower().startswith("mac="):
            candidates.append(unquote(part.split("=", 1)[1].strip().strip('"')))

    for header_name in ("x-user-agent", "user-agent", "x-mac-address", "device-id"):
        value = request.headers.get(header_name)
        if not value:
            continue
        candidates.append(value)
        match = MAC_IN_TEXT.search(value)
        if match:
            candidates.append(match.group(1))

    for raw in candidates:
        try:
            return normalize_mac(raw)
        except ValueError:
            # Try extracting embedded MAC from longer strings
            match = MAC_IN_TEXT.search(raw)
            if match:
                try:
                    return normalize_mac(match.group(1))
                except ValueError:
                    continue
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


class StalkerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.devices = DeviceRepository(db)
        self.playlist = PlaylistService(db)
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

    async def authorize(self, request: Request) -> AuthorizedDevice:
        mac = extract_mac_from_request(request)
        token = extract_token_from_request(request)

        if not mac and token:
            mac = _TOKEN_TO_MAC.get(token)

        if not mac:
            raise StalkerAuthError("Authorization failed.")

        device = await self.get_device_by_mac(mac)
        if not device or not device.active:
            raise StalkerAuthError("Authorization failed.")

        client = device.__dict__.get("client")
        if client is None or not client.active:
            raise StalkerAuthError("Authorization failed.")

        sub = device.__dict__.get("subscription")
        if sub is None:
            # Fall back to client's current active subscription
            from app.repositories import ClientRepository

            full_client = await ClientRepository(self.db).get(client.id)
            if not full_client or not full_client.subscriptions:
                raise StalkerAuthError("Authorization failed.")
            sorted_subs = sorted(full_client.subscriptions, key=lambda s: s.expires_at, reverse=True)
            sub = next((s for s in sorted_subs if s.active), sorted_subs[0])

        st = status_for_subscription(sub, client)
        if st in {SubscriptionStatus.DISABLED, SubscriptionStatus.EXPIRED}:
            raise StalkerAuthError("Authorization failed.")

        # Touch last seen
        device.last_seen_at = datetime.now(timezone.utc)
        if request.client:
            device.last_ip = request.client.host
        device.last_user_agent = (request.headers.get("user-agent") or "")[:512]

        return AuthorizedDevice(device=device, subscription=sub, mac=mac)

    def issue_token(self, mac: str) -> str:
        old = _MAC_TO_TOKEN.get(mac)
        if old:
            _TOKEN_TO_MAC.pop(old, None)
        token = secrets.token_hex(16)
        _TOKEN_TO_MAC[token] = mac
        _MAC_TO_TOKEN[mac] = token
        return token

    async def handshake(self, request: Request) -> dict[str, Any]:
        try:
            auth = await self.authorize(request)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)

        token = self.issue_token(auth.mac)
        return stalker_js({"token": token, "random": secrets.token_hex(8)})

    async def get_profile(self, request: Request) -> dict[str, Any]:
        try:
            auth = await self.authorize(request)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)

        sub = auth.subscription
        client = auth.device.__dict__.get("client")
        expires = int(ensure_utc(sub.expires_at).timestamp())
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
            "device_id": auth.mac.replace(":", ""),
            "device_id2": auth.mac.replace(":", ""),
            "hw_version": "1.7-BD-00",
            "stb_type": "MAG254",
            "image_version": "218",
            "hd": "1",
            "main_api_url": f"{self.settings.public_base_url.rstrip('/')}/stalker_portal/server/load.php",
            "update_url": "",
            "settings": {},
        }
        return stalker_js(profile)

    async def _channels_for(self, auth: AuthorizedDevice) -> list[M3UChannel]:
        content, _meta = await self.playlist._get_content(auth.subscription, kind="m3u")
        return parse_m3u_channels(content)

    async def get_genres(self, request: Request) -> dict[str, Any]:
        try:
            auth = await self.authorize(request)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)

        channels = await self._channels_for(auth)
        groups: list[str] = []
        seen: set[str] = set()
        for ch in channels:
            key = ch.group or "General"
            if key not in seen:
                seen.add(key)
                groups.append(key)

        genres: list[dict[str, Any]] = [{"id": "*", "title": "All", "alias": "All"}]
        for i, title in enumerate(groups, start=1):
            genres.append({"id": str(i), "title": title, "alias": title})
        return stalker_js(genres)

    def _genre_id_map(self, channels: list[M3UChannel]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        next_id = 1
        for ch in channels:
            g = ch.group or "General"
            if g not in mapping:
                mapping[g] = str(next_id)
                next_id += 1
        return mapping

    async def get_all_channels(self, request: Request) -> dict[str, Any]:
        try:
            auth = await self.authorize(request)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)

        channels = await self._channels_for(auth)
        genre_map = self._genre_id_map(channels)
        data = []
        for ch in channels:
            # Stable opaque cmd that does not embed upstream credentials in a new form —
            # create_link resolves by channel id against the cached M3U.
            cmd = f"ffmpeg http://localhost/ch/{ch.id}"
            data.append(
                {
                    "id": ch.id,
                    "name": ch.name,
                    "number": str(ch.number),
                    "cmd": cmd,
                    "logo": ch.logo or "",
                    "tv_genre_id": genre_map.get(ch.group or "General", "1"),
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
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return stalker_js({"total_items": len(data), "max_page_items": len(data), "data": data})

    async def create_link(self, request: Request, *, cmd: str | None = None, channel_id: str | None = None) -> dict[str, Any]:
        try:
            auth = await self.authorize(request)
        except StalkerAuthError as exc:
            return stalker_error(exc.message)

        channels = await self._channels_for(auth)
        by_id = {ch.id: ch for ch in channels}

        target: M3UChannel | None = None
        raw_cmd = (cmd or request.query_params.get("cmd") or "").strip()
        cid = (channel_id or request.query_params.get("channel_id") or "").strip()

        if cid and cid in by_id:
            target = by_id[cid]
        elif raw_cmd:
            # Patterns: "ffmpeg http://localhost/ch/12", "/ch/12", bare id, or direct URL
            m = re.search(r"/ch/(\d+)", raw_cmd)
            if m and m.group(1) in by_id:
                target = by_id[m.group(1)]
            elif raw_cmd.isdigit() and raw_cmd in by_id:
                target = by_id[raw_cmd]
            else:
                # If client already sent a full stream URL, pass through
                if raw_cmd.startswith("http://") or raw_cmd.startswith("https://"):
                    url = raw_cmd.removeprefix("ffmpeg ").strip()
                    await self.playlist._record_access(
                        auth.subscription,
                        endpoint="stalker_link",
                        ip=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"),
                    )
                    return stalker_js({"id": cid or "0", "cmd": url, "streamer_id": 0, "link_id": 0, "load": 0})
                # Match by exact cmd stored earlier
                for ch in channels:
                    if raw_cmd.endswith(f"/ch/{ch.id}") or raw_cmd == ch.url:
                        target = ch
                        break

        if target is None and channels:
            # Some clients send only type/action without id after selecting — reject clearly
            return stalker_error("Channel not found.")

        if target is None:
            return stalker_error("Channel not found.")

        await self.playlist._record_access(
            auth.subscription,
            endpoint="stalker_link",
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return stalker_js(
            {
                "id": target.id,
                "cmd": target.url,
                "streamer_id": 0,
                "link_id": int(hashlib.md5(target.id.encode()).hexdigest()[:6], 16) % 100000,
                "load": 0,
            }
        )

    async def dispatch(self, request: Request) -> dict[str, Any]:
        type_ = (request.query_params.get("type") or "").lower()
        action = (request.query_params.get("action") or "").lower()

        if type_ == "stb" and action == "handshake":
            return await self.handshake(request)
        if type_ == "stb" and action == "get_profile":
            return await self.get_profile(request)
        if type_ == "itv" and action == "get_all_channels":
            return await self.get_all_channels(request)
        if type_ == "itv" and action == "create_link":
            return await self.create_link(request)
        if type_ == "itv" and action == "get_genres":
            return await self.get_genres(request)

        # Harmless defaults some firmwares probe
        if type_ == "stb" and action in {"get_localization", "get_modules"}:
            try:
                await self.authorize(request)
            except StalkerAuthError as exc:
                return stalker_error(exc.message)
            return stalker_js({} if action == "get_localization" else [])

        return stalker_error("Action not supported.")

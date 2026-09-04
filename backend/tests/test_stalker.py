from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATA_ENCRYPTION_KEY", "test-encryption-key")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_INITIAL_PASSWORD", "admin12345")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("CACHE_DIR", "/tmp/iptv-stalker-cache")
os.environ.setdefault("ALLOW_PRIVATE_URLS", "true")
os.environ.setdefault("COOKIE_SECURE", "false")

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.providers.base import FetchResult
from app.services.auth import AuthService
from app.utils.mac import normalize_mac
from app.utils.m3u_parse import parse_m3u_channels

get_settings.cache_clear()


SAMPLE_M3U = b"""#EXTM3U
#EXTINF:-1 tvg-id="ch1" tvg-logo="http://logo/1.png" group-title="News",CNN HD
http://stream.example/live/cnn.ts
#EXTINF:-1 group-title="Sports",ESPN
http://stream.example/live/espn.ts
"""


@pytest_asyncio.fixture
async def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    get_settings.cache_clear()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await AuthService(session).ensure_bootstrap_admin("admin", "admin12345")
        await session.commit()

    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from app.api import admin_misc, auth, clients, health, public, stalker, subscriptions
    from app.core.rate_limit import PublicRateLimitMiddleware

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Path(get_settings().cache_dir).mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title="test", lifespan=lifespan)
    app.add_middleware(PublicRateLimitMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(health.router)
    app.include_router(public.router)
    app.include_router(stalker.router)
    app.include_router(auth.router, prefix="/api/admin")
    app.include_router(clients.router, prefix="/api/admin")
    app.include_router(subscriptions.router, prefix="/api/admin")
    app.include_router(admin_misc.router, prefix="/api/admin")

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, session_factory
    await engine.dispose()
    get_settings.cache_clear()


async def login(client: AsyncClient) -> None:
    res = await client.post("/api/admin/auth/login", json={"username": "admin", "password": "admin12345"})
    assert res.status_code == 200


async def create_client_with_mac(client: AsyncClient, *, mac: str, active: bool = True, expired: bool = False) -> dict:
    await login(client)
    if expired:
        expires = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    else:
        expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    fake = FetchResult(content=SAMPLE_M3U, content_type="application/x-mpegURL", http_status=200, duration_ms=1)
    with patch("app.providers.m3u.M3UProvider.get_playlist", new=AsyncMock(return_value=fake)):
        res = await client.post(
            "/api/admin/clients",
            json={
                "name": "MAG Client",
                "active": active,
                "subscription": {
                    "source_m3u_url": "https://provider.example/list.m3u",
                    "expires_at": expires,
                    "max_devices": 3,
                },
                "device": {
                    "name": "MAG Box",
                    "device_type": "MAG",
                    "mac_address": mac,
                },
            },
        )
    assert res.status_code == 201, res.text
    return res.json()


def test_parse_m3u_channels():
    channels = parse_m3u_channels(SAMPLE_M3U)
    assert len(channels) == 2
    assert channels[0].name == "CNN HD"
    assert channels[0].group == "News"
    assert channels[0].url.endswith("cnn.ts")
    assert channels[1].name == "ESPN"


def test_normalize_mac_variants():
    assert normalize_mac("00-1a-79-aa-bb-cc") == "00:1A:79:AA:BB:CC"
    assert normalize_mac("001A79AABBCC") == "00:1A:79:AA:BB:CC"


@pytest.mark.asyncio
async def test_stalker_handshake_success(app_client):
    client, _ = app_client
    await create_client_with_mac(client, mac="00-1a-79-12-34-56")
    res = await client.get(
        "/stalker_portal/server/load.php",
        params={"type": "stb", "action": "handshake"},
        cookies={"mac": "00:1A:79:12:34:56"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["text"] == ""
    assert "token" in body["js"]


@pytest.mark.asyncio
async def test_stalker_handshake_invalid_mac(app_client):
    client, _ = app_client
    res = await client.get(
        "/stalker_portal/server/load.php",
        params={"type": "stb", "action": "handshake", "mac": "00:1A:79:00:00:01"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["text"] == "Authorization failed."


@pytest.mark.asyncio
async def test_stalker_inactive_device(app_client):
    client, _ = app_client
    created = await create_client_with_mac(client, mac="00:1A:79:AA:BB:01")
    device_id = created["devices"][0]["id"]
    await client.patch(f"/api/admin/devices/{device_id}", json={"active": False})

    res = await client.get(
        "/stalker_portal/server/load.php",
        params={"type": "stb", "action": "handshake"},
        headers={"Cookie": "mac=00:1A:79:AA:BB:01"},
    )
    assert res.json()["text"] == "Authorization failed."


@pytest.mark.asyncio
async def test_stalker_inactive_client(app_client):
    client, _ = app_client
    created = await create_client_with_mac(client, mac="00:1A:79:AA:BB:02")
    await client.patch(f"/api/admin/clients/{created['id']}", json={"active": False})
    res = await client.get(
        "/stalker_portal/server/load.php",
        params={"type": "stb", "action": "get_profile", "mac": "00:1A:79:AA:BB:02"},
    )
    assert res.json()["text"] == "Authorization failed."


@pytest.mark.asyncio
async def test_stalker_get_all_channels_and_create_link(app_client):
    client, _ = app_client
    await create_client_with_mac(client, mac="00:1A:79:CC:DD:EE")
    fake = FetchResult(content=SAMPLE_M3U, content_type="application/x-mpegURL", http_status=200, duration_ms=1)

    with patch("app.providers.m3u.M3UProvider.get_playlist", new=AsyncMock(return_value=fake)):
        channels = await client.get(
            "/stalker_portal/server/load.php",
            params={"type": "itv", "action": "get_all_channels"},
            cookies={"mac": "00:1A:79:CC:DD:EE"},
        )
        assert channels.status_code == 200
        body = channels.json()
        assert body["text"] == ""
        assert body["js"]["total_items"] == 2
        assert body["js"]["data"][0]["name"] == "CNN HD"
        assert "cmd" in body["js"]["data"][0]
        # Must not leak source playlist credentials field
        assert "source_m3u" not in str(body).lower()

        link = await client.get(
            "/stalker_portal/server/load.php",
            params={"type": "itv", "action": "create_link", "cmd": "ffmpeg http://localhost/ch/1"},
            cookies={"mac": "00:1A:79:CC:DD:EE"},
        )
        assert link.status_code == 200
        link_body = link.json()
        assert link_body["js"]["cmd"] == "http://stream.example/live/cnn.ts"

        genres = await client.get(
            "/stalker_portal/server/load.php",
            params={"type": "itv", "action": "get_genres"},
            cookies={"mac": "00:1A:79:CC:DD:EE"},
        )
        assert genres.json()["js"][0]["id"] == "*"


@pytest.mark.asyncio
async def test_stalker_mac_from_user_agent(app_client):
    client, _ = app_client
    await create_client_with_mac(client, mac="00:1A:79:11:22:33")
    res = await client.get(
        "/stalker_portal/server/load.php",
        params={"type": "stb", "action": "handshake"},
        headers={"X-User-Agent": "Model: MAG254; MAC:00:1A:79:11:22:33"},
    )
    assert res.json()["text"] == ""
    assert "token" in res.json()["js"]


@pytest.mark.asyncio
async def test_stalker_portal_c_page(app_client):
    client, _ = app_client
    res = await client.get("/stalker_portal/c/")
    assert res.status_code == 200
    assert "Stalker" in res.text or "stalker" in res.text.lower()

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
os.environ.setdefault("PUBLIC_BASE_URL", "https://iptv.danielpereira6.pt")
os.environ.setdefault("STALKER_PORTAL_URL", "https://iptv.danielpereira6.pt/c/")
os.environ.setdefault("STALKER_CREATE_LINK_PREFIX", "none")
os.environ.setdefault("CACHE_DIR", "/tmp/iptv-stalker-cache")
os.environ.setdefault("ALLOW_PRIVATE_URLS", "true")
os.environ.setdefault("COOKIE_SECURE", "false")

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.providers.base import FetchResult
from app.services.auth import AuthService
from app.utils.logging_mask import mask_sensitive_url
from app.utils.mac import normalize_mac
from app.utils.m3u_parse import parse_m3u_channels

get_settings.cache_clear()

SAMPLE_M3U = b"""#EXTM3U
#EXTINF:-1 tvg-id="ch1" tvg-logo="http://logo/1.png" group-title="News",CNN HD
http://stream.example/live/user/pass/cnn.ts
#EXTINF:-1 group-title="Sports",ESPN
http://stream.example/live/espn.ts
"""

SAMPLE_M3U_NO_GROUP = b"""#EXTM3U
#EXTINF:-1,Only Channel
http://stream.example/only.ts
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


async def create_client_with_mac(client: AsyncClient, *, mac: str, m3u: bytes = SAMPLE_M3U) -> dict:
    await login(client)
    expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    fake = FetchResult(content=m3u, content_type="application/x-mpegURL", http_status=200, duration_ms=1)
    with patch("app.providers.m3u.M3UProvider.get_playlist", new=AsyncMock(return_value=fake)):
        res = await client.post(
            "/api/admin/clients",
            json={
                "name": "MAG Client",
                "subscription": {
                    "source_m3u_url": "https://provider.example/get.php?username=secret&password=secret",
                    "expires_at": expires,
                    "max_devices": 50,
                    "upstream_max_connections": 2,
                    "notes": "line shared across devices",
                },
                "device": {"name": "MAG Box", "device_type": "MAG", "mac_address": mac},
            },
        )
    assert res.status_code == 201, res.text
    return res.json()


def test_mask_sensitive_url():
    masked = mask_sensitive_url("http://provider.com/get.php?username=u&password=p&type=m3u_plus")
    assert "username=***" in masked
    assert "password=***" in masked
    assert "u&password=p" not in masked


def test_normalize_mac_variants():
    assert normalize_mac("00-1a-79-aa-bb-cc") == "00:1A:79:AA:BB:CC"


@pytest.mark.asyncio
async def test_handshake_cookie_and_query(app_client):
    client, _ = app_client
    await create_client_with_mac(client, mac="00-1a-79-12-34-56")
    by_cookie = await client.get(
        "/stalker_portal/server/load.php",
        params={"type": "stb", "action": "handshake"},
        cookies={"mac": "00:1A:79:12:34:56"},
    )
    assert by_cookie.json()["text"] == ""
    assert "token" in by_cookie.json()["js"]

    by_query = await client.get(
        "/server/load.php",
        params={"type": "stb", "action": "handshake", "mac": "00:1A:79:12:34:56"},
    )
    assert by_query.json()["text"] == ""

    by_portal = await client.get(
        "/portal.php",
        params={"type": "stb", "action": "handshake", "mac": "00:1A:79:12:34:56"},
    )
    assert by_portal.json()["text"] == ""


@pytest.mark.asyncio
async def test_invalid_and_missing_mac(app_client):
    client, _ = app_client
    missing = await client.get("/stalker_portal/server/load.php", params={"type": "stb", "action": "handshake"})
    assert missing.json()["text"] == "Authorization failed."
    invalid = await client.get(
        "/stalker_portal/server/load.php",
        params={"type": "stb", "action": "handshake", "mac": "00:1A:79:00:00:01"},
    )
    assert invalid.json()["text"] == "Authorization failed."


@pytest.mark.asyncio
async def test_device_id_change_does_not_block(app_client):
    client, _ = app_client
    await create_client_with_mac(client, mac="00:1A:79:AA:BB:10")
    first = await client.get(
        "/stalker_portal/server/load.php",
        params={"type": "stb", "action": "handshake", "mac": "00:1A:79:AA:BB:10", "device_id": "AAAA"},
    )
    assert first.json()["text"] == ""
    second = await client.get(
        "/stalker_portal/server/load.php",
        params={"type": "stb", "action": "handshake", "mac": "00:1A:79:AA:BB:10", "device_id": "BBBB"},
    )
    assert second.json()["text"] == ""


@pytest.mark.asyncio
async def test_genres_and_channels(app_client):
    client, _ = app_client
    await create_client_with_mac(client, mac="00:1A:79:CC:DD:01")
    fake = FetchResult(content=SAMPLE_M3U, content_type="application/x-mpegURL", http_status=200, duration_ms=1)
    with patch("app.providers.m3u.M3UProvider.get_playlist", new=AsyncMock(return_value=fake)):
        genres = await client.get(
            "/stalker_portal/server/load.php",
            params={"type": "itv", "action": "get_genres"},
            cookies={"mac": "00:1A:79:CC:DD:01"},
        )
        gjs = genres.json()["js"]
        assert genres.json()["text"] == ""
        assert isinstance(gjs, list) and len(gjs) >= 1
        genre_ids = {g["id"] for g in gjs}

        channels = await client.get(
            "/stalker_portal/server/load.php",
            params={"type": "itv", "action": "get_all_channels"},
            cookies={"mac": "00:1A:79:CC:DD:01"},
        )
        body = channels.json()
        assert body["js"]["total_items"] == 2
        ch0 = body["js"]["data"][0]
        assert isinstance(ch0["id"], str)
        assert "cmd" in ch0
        assert "localhost/ch/" in ch0["cmd"]
        assert "username=" not in ch0["cmd"].lower()
        assert ch0["tv_genre_id"] in genre_ids


@pytest.mark.asyncio
async def test_genres_fallback_all(app_client):
    client, _ = app_client
    await create_client_with_mac(client, mac="00:1A:79:CC:DD:02", m3u=SAMPLE_M3U_NO_GROUP)
    fake = FetchResult(content=SAMPLE_M3U_NO_GROUP, content_type="application/x-mpegURL", http_status=200, duration_ms=1)
    with patch("app.providers.m3u.M3UProvider.get_playlist", new=AsyncMock(return_value=fake)):
        # Force empty groups by empty playlist parse path — use channel with General group only;
        # parse always yields General; for true empty categories patch parse
        with patch("app.services.stalker.parse_m3u_channels", return_value=[]):
            genres = await client.get(
                "/stalker_portal/server/load.php",
                params={"type": "itv", "action": "get_genres"},
                cookies={"mac": "00:1A:79:CC:DD:02"},
            )
            assert genres.json()["js"] == [{"id": "1", "title": "All", "alias": "all"}]


@pytest.mark.asyncio
async def test_create_link_variants(app_client):
    client, _ = app_client
    await create_client_with_mac(client, mac="00:1A:79:EE:FF:01")
    fake = FetchResult(content=SAMPLE_M3U, content_type="application/x-mpegURL", http_status=200, duration_ms=1)
    mac = "00:1A:79:EE:FF:01"
    with patch("app.providers.m3u.M3UProvider.get_playlist", new=AsyncMock(return_value=fake)):
        cases = [
            ("GET", {"cmd": "ffmpeg http://localhost/ch/1"}),
            ("GET", {"cmd": "/ch/1"}),
            ("GET", {"cmd": "1"}),
            ("GET", {"channel_id": "1"}),
        ]
        for method, params in cases:
            res = await client.request(
                method,
                "/stalker_portal/server/load.php",
                params={"type": "itv", "action": "create_link", **params},
                cookies={"mac": mac},
            )
            assert res.status_code == 200, res.text
            cmd = res.json()["js"]["cmd"]
            assert cmd.startswith("http")
            assert "localhost" not in cmd
            assert res.json()["js"]["id"] == "1"

        post = await client.post(
            "/stalker_portal/server/load.php?type=itv&action=create_link",
            data={"cmd": "ffmpeg http://localhost/ch/1"},
            cookies={"mac": mac},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert "stream.example" in post.json()["js"]["cmd"]
        assert "localhost" not in post.json()["js"]["cmd"]

        direct = await client.get(
            "/stalker_portal/server/load.php",
            params={"type": "itv", "action": "create_link", "cmd": "https://cdn.example/live.ts"},
            cookies={"mac": mac},
        )
        assert direct.json()["js"]["cmd"] == "https://cdn.example/live.ts"


@pytest.mark.asyncio
async def test_epg_actions_empty(app_client):
    client, _ = app_client
    await create_client_with_mac(client, mac="00:1A:79:E0:G0:01".replace("G0", "F0"))
    mac = "00:1A:79:E0:F0:01"
    for action in ("get_short_epg", "get_epg_info"):
        res = await client.get(
            "/stalker_portal/server/load.php",
            params={"type": "itv", "action": action, "mac": mac},
        )
        assert res.status_code == 200
        assert res.json()["text"] == ""
        assert res.json()["js"] == []


@pytest.mark.asyncio
async def test_portal_c_is_backend_html(app_client):
    client, _ = app_client
    res = await client.get("/c/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "Stalker" in res.text
    assert "root" not in res.text  # not React shell

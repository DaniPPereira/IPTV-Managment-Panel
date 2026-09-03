from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Configure env before importing app
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATA_ENCRYPTION_KEY", "test-encryption-key")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_INITIAL_PASSWORD", "admin12345")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("CACHE_DIR", "/tmp/iptv-test-cache")
os.environ.setdefault("ALLOW_PRIVATE_URLS", "true")
os.environ.setdefault("COOKIE_SECURE", "false")

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.services.auth import AuthService
from app.services.encryption import EncryptionService

get_settings.cache_clear()
settings = get_settings()
Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)


@pytest_asyncio.fixture
async def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
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
    from app.api import admin_misc, auth, clients, health, public, subscriptions
    from app.core.rate_limit import PublicRateLimitMiddleware
    from fastapi.middleware.cors import CORSMiddleware

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Path(get_settings().cache_dir).mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title="test", lifespan=lifespan)
    app.add_middleware(PublicRateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(public.router)
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


@pytest.mark.asyncio
async def test_login(app_client):
    client, _ = app_client
    res = await client.post("/api/admin/auth/login", json={"username": "admin", "password": "admin12345"})
    assert res.status_code == 200
    assert res.json()["username"] == "admin"
    assert "iptv_admin_token" in res.cookies


@pytest.mark.asyncio
async def test_create_client_and_public_m3u(app_client, httpx_mock=None):
    client, _ = app_client
    await login(client)

    # Mock upstream via monkeypatch on provider would be cleaner; use encrypted local fake by patching PlaylistService
    from unittest.mock import AsyncMock, patch
    from app.providers.base import FetchResult

    fake = FetchResult(
        content=b"#EXTM3U\n#EXTINF:-1,Test\nhttp://example.com/stream.ts\n",
        content_type="application/x-mpegURL",
        http_status=200,
        duration_ms=12,
    )

    expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with patch("app.providers.m3u.M3UProvider.get_playlist", new=AsyncMock(return_value=fake)):
        with patch("app.providers.m3u.M3UProvider.get_epg", new=AsyncMock(return_value=fake)):
            res = await client.post(
                "/api/admin/clients",
                json={
                    "name": "João Silva",
                    "email": "joao@email.pt",
                    "phone": "912345678",
                    "notes": "Cliente anual",
                    "subscription": {
                        "source_m3u_url": "https://provider.example/get.php?username=x&password=y",
                        "source_epg_url": "https://provider.example/epg.xml",
                        "expires_at": expires,
                        "max_devices": 2,
                    },
                    "device": {
                        "name": "TV Sala",
                        "device_type": "MAG",
                        "mac_address": "00-1a-79-12-34-56",
                    },
                },
            )
            assert res.status_code == 201, res.text
            body = res.json()
            assert body["name"] == "João Silva"
            assert body["current_subscription"]["status"] in {"ACTIVE", "EXPIRING_SOON"}
            assert body["devices"][0]["mac_address"] == "00:1A:79:12:34:56"
            token = body["current_subscription"]["public_token"]
            # Public API must not leak source URLs on list/detail without auth - detail is admin so sources ok
            assert "source_m3u_url" in body["current_subscription"]

            m3u = await client.get(f"/m3u/{token}")
            assert m3u.status_code == 200
            assert b"#EXTM3U" in m3u.content

            epg = await client.get(f"/epg/{token}")
            assert epg.status_code == 200


@pytest.mark.asyncio
async def test_invalid_token(app_client):
    client, _ = app_client
    res = await client.get("/m3u/does-not-exist")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_expired_and_disabled(app_client):
    client, _ = app_client
    await login(client)

    from unittest.mock import AsyncMock, patch
    from app.providers.base import FetchResult

    fake = FetchResult(content=b"#EXTM3U\n", content_type="application/x-mpegURL", http_status=200, duration_ms=1)
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    with patch("app.providers.m3u.M3UProvider.get_playlist", new=AsyncMock(return_value=fake)):
        expired = await client.post(
            "/api/admin/clients",
            json={
                "name": "Expired User",
                "subscription": {
                    "source_m3u_url": "https://provider.example/a.m3u",
                    "expires_at": past,
                },
            },
        )
        assert expired.status_code == 201
        token_expired = expired.json()["current_subscription"]["public_token"]
        res = await client.get(f"/m3u/{token_expired}")
        assert res.status_code == 403

        active = await client.post(
            "/api/admin/clients",
            json={
                "name": "Active User",
                "subscription": {
                    "source_m3u_url": "https://provider.example/b.m3u",
                    "expires_at": future,
                },
            },
        )
        client_id = active.json()["id"]
        token = active.json()["current_subscription"]["public_token"]
        await client.patch(f"/api/admin/clients/{client_id}", json={"active": False})
        res = await client.get(f"/m3u/{token}")
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_renew_and_regenerate(app_client):
    client, _ = app_client
    await login(client)
    from unittest.mock import AsyncMock, patch
    from app.providers.base import FetchResult

    fake = FetchResult(content=b"#EXTM3U\n", content_type="application/x-mpegURL", http_status=200, duration_ms=1)
    expires = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    with patch("app.providers.m3u.M3UProvider.get_playlist", new=AsyncMock(return_value=fake)):
        created = await client.post(
            "/api/admin/clients",
            json={
                "name": "Renew User",
                "subscription": {"source_m3u_url": "https://provider.example/c.m3u", "expires_at": expires},
            },
        )
        sub = created.json()["current_subscription"]
        old_token = sub["public_token"]
        renewed = await client.post(f"/api/admin/subscriptions/{sub['id']}/renew", json={"months": 3})
        assert renewed.status_code == 200
        new_exp = datetime.fromisoformat(renewed.json()["expires_at"].replace("Z", "+00:00"))
        old_exp = datetime.fromisoformat(sub["expires_at"].replace("Z", "+00:00"))
        assert new_exp > old_exp

        regen = await client.post(f"/api/admin/subscriptions/{sub['id']}/regenerate-token")
        assert regen.status_code == 200
        new_token = regen.json()["public_token"]
        assert new_token != old_token
        assert (await client.get(f"/m3u/{old_token}")).status_code == 404
        assert (await client.get(f"/m3u/{new_token}")).status_code == 200


@pytest.mark.asyncio
async def test_xtream_endpoints(app_client):
    client, _ = app_client
    await login(client)
    from unittest.mock import AsyncMock, patch
    from app.providers.base import FetchResult

    fake = FetchResult(content=b"#EXTM3U\nchannel\n", content_type="application/x-mpegURL", http_status=200, duration_ms=1)
    expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with patch("app.providers.m3u.M3UProvider.get_playlist", new=AsyncMock(return_value=fake)):
        created = await client.post(
            "/api/admin/clients",
            json={
                "name": "Xtream User",
                "subscription": {"source_m3u_url": "https://provider.example/d.m3u", "expires_at": expires},
            },
        )
        sub = created.json()["current_subscription"]
        api = await client.get(
            "/player_api.php",
            params={"username": sub["xtream_username"], "password": sub["xtream_password"]},
        )
        assert api.status_code == 200
        assert api.json()["user_info"]["status"] == "Active"
        playlist = await client.get(
            "/get.php",
            params={
                "username": sub["xtream_username"],
                "password": sub["xtream_password"],
                "type": "m3u_plus",
                "output": "ts",
            },
        )
        assert playlist.status_code == 200
        assert b"#EXTM3U" in playlist.content


def test_encryption_roundtrip():
    svc = EncryptionService("unit-test-key")
    secret = "https://provider.example/get.php?username=x&password=y"
    assert svc.decrypt(svc.encrypt(secret)) == secret

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin_misc, auth, clients, health, public, stalker, subscriptions
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import setup_logging
from app.core.rate_limit import PublicRateLimitMiddleware
from app.services.auth import AuthService


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    settings = get_settings()
    Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
    async with AsyncSessionLocal() as session:
        await AuthService(session).ensure_bootstrap_admin(
            settings.admin_username, settings.admin_initial_password
        )
        await session.commit()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="IPTV Provisioning Panel", version="1.0.0", lifespan=lifespan)
    app.add_middleware(PublicRateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://127.0.0.1"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(public.router)
    app.include_router(stalker.router)
    app.include_router(auth.router, prefix="/api/admin")
    app.include_router(clients.router, prefix="/api/admin")
    app.include_router(subscriptions.router, prefix="/api/admin")
    app.include_router(admin_misc.router, prefix="/api/admin")

    @app.get("/api/admin/ping")
    async def ping() -> dict:
        return {"ok": True}

    return app


app = create_app()

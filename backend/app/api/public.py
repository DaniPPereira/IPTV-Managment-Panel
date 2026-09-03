from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import client_ip
from app.repositories import SubscriptionRepository
from app.schemas import SetupPageOut
from app.services.playlist import PlaylistService
from app.utils.status import status_for_subscription

router = APIRouter(tags=["public"])


def _playlist_response(content: bytes, meta: dict) -> Response:
    headers = {
        "Cache-Control": f"public, max-age={get_settings().m3u_cache_seconds}",
    }
    if meta.get("etag"):
        headers["ETag"] = meta["etag"]
    if meta.get("last_modified"):
        headers["Last-Modified"] = meta["last_modified"]
    return Response(content=content, media_type="application/x-mpegURL", headers=headers)


def _epg_response(content: bytes, meta: dict) -> Response:
    content_type = meta.get("content_type") or "application/xml"
    if "gzip" in content_type or content[:2] == b"\x1f\x8b":
        media = "application/xml+gzip"
    else:
        media = "application/xml"
    headers = {
        "Cache-Control": f"public, max-age={get_settings().epg_cache_seconds}",
    }
    if meta.get("etag"):
        headers["ETag"] = meta["etag"]
    if meta.get("last_modified"):
        headers["Last-Modified"] = meta["last_modified"]
    return Response(content=content, media_type=media, headers=headers)


@router.get("/m3u/{token}")
async def public_m3u(token: str, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    content, meta = await PlaylistService(db).get_m3u_by_token(
        token, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    return _playlist_response(content, meta)


@router.get("/epg/{token}")
async def public_epg(token: str, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    content, meta = await PlaylistService(db).get_epg_by_token(
        token, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    return _epg_response(content, meta)


@router.get("/get.php")
async def get_php(
    request: Request,
    username: str,
    password: str,
    type: str | None = None,
    output: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    _ = type, output
    content, meta = await PlaylistService(db).get_m3u_by_xtream(
        username, password, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    return _playlist_response(content, meta)


@router.get("/player_api.php")
async def player_api(
    username: str,
    password: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    payload = await PlaylistService(db).player_api(username, password)
    return JSONResponse(payload)


@router.get("/api/public/setup/{token}", response_model=SetupPageOut)
async def setup_page(token: str, db: AsyncSession = Depends(get_db)) -> SetupPageOut:
    from fastapi import HTTPException

    settings = get_settings()
    if not settings.setup_page_enabled:
        raise HTTPException(status_code=404, detail="Setup page disabled")
    sub = await SubscriptionRepository(db).get_by_token(token)
    if not sub or not sub.client:
        raise HTTPException(status_code=404, detail="Not found")
    base = settings.public_base_url.rstrip("/")
    return SetupPageOut(
        client_name=sub.client.name,
        status=status_for_subscription(sub),
        expires_at=sub.expires_at,
        m3u_url=f"{base}/m3u/{sub.public_token}",
        epg_url=f"{base}/epg/{sub.public_token}",
        xtream_server=base,
        xtream_username=sub.xtream_username,
        xtream_password=sub.xtream_password,
    )

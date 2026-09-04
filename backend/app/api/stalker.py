from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.stalker import StalkerService

router = APIRouter(tags=["stalker"])


@router.api_route("/stalker_portal/c/", methods=["GET", "POST"])
@router.api_route("/stalker_portal/c", methods=["GET", "POST"])
@router.api_route("/c/", methods=["GET", "POST"])
@router.api_route("/c", methods=["GET", "POST"])
async def stalker_portal_root() -> HTMLResponse:
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Stalker Portal</title></head>
<body>
<script>window.location='/stalker_portal/server/load.php?type=stb&action=handshake';</script>
<p>Stalker portal ready.</p>
</body></html>"""
    return HTMLResponse(content=html)


@router.api_route("/stalker_portal/server/load.php", methods=["GET", "POST"])
@router.api_route("/stalker_portal/load.php", methods=["GET", "POST"])
@router.api_route("/server/load.php", methods=["GET", "POST"])
@router.api_route("/portal.php", methods=["GET", "POST"])
async def stalker_load(request: Request, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    payload = await StalkerService(db).dispatch(request)
    return JSONResponse(payload)


@router.get("/stalker_portal/server/version.js")
async def stalker_version() -> PlainTextResponse:
    return PlainTextResponse("var ver = '5.5.0';")

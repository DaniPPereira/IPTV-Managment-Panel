from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.database import get_db
from app.core.security import clear_auth_cookie, client_ip, set_auth_cookie
from app.models import AdminUser
from app.schemas import AdminMe, ChangePasswordRequest, LoginRequest
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AdminMe)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AdminMe:
    admin, token = await AuthService(db).login(payload.username, payload.password, ip=client_ip(request))
    set_auth_cookie(response, token)
    return AdminMe.model_validate(admin)


@router.post("/logout")
async def logout(response: Response) -> dict:
    clear_auth_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=AdminMe)
async def me(admin: AdminUser = Depends(get_current_admin)) -> AdminMe:
    return AdminMe.model_validate(admin)


@router.post("/change-password", response_model=AdminMe)
async def change_password(
    payload: ChangePasswordRequest,
    admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminMe:
    updated = await AuthService(db).change_password(admin, payload.current_password, payload.new_password)
    return AdminMe.model_validate(updated)

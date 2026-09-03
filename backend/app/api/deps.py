from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token, get_token_from_request
from app.models import AdminUser
from app.services.auth import AuthService


async def get_current_admin(
    request: Request, db: AsyncSession = Depends(get_db)
) -> AdminUser:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_access_token(token)
    admin_id = UUID(payload["sub"])
    return await AuthService(db).get_admin(admin_id)

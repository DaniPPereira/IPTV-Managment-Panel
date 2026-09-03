from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models import AdminUser
from app.repositories import AdminRepository
from app.services.audit import AuditService


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AdminRepository(db)
        self.audit = AuditService(db)

    async def ensure_bootstrap_admin(self, username: str, password: str) -> None:
        if await self.repo.count() > 0:
            return
        admin = AdminUser(
            username=username,
            password_hash=hash_password(password),
            is_active=True,
            must_change_password=True,
        )
        await self.repo.create(admin)
        await self.audit.log(
            action="ADMIN_BOOTSTRAP",
            entity_type="admin_user",
            entity_id=admin.id,
            details={"username": username},
        )

    async def login(self, username: str, password: str, *, ip: str | None = None) -> tuple[AdminUser, str]:
        admin = await self.repo.get_by_username(username)
        if not admin or not admin.is_active or not verify_password(password, admin.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        admin.last_login_at = datetime.now(timezone.utc)
        token = create_access_token(subject=str(admin.id), extra={"username": admin.username})
        await self.audit.log(
            action="ADMIN_LOGIN",
            entity_type="admin_user",
            entity_id=admin.id,
            admin_user_id=admin.id,
            ip_address=ip,
        )
        return admin, token

    async def get_admin(self, admin_id: UUID) -> AdminUser:
        admin = await self.repo.get_by_id(admin_id)
        if not admin or not admin.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
        return admin

    async def change_password(self, admin: AdminUser, current_password: str, new_password: str) -> AdminUser:
        if not verify_password(current_password, admin.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
        admin.password_hash = hash_password(new_password)
        admin.must_change_password = False
        await self.audit.log(
            action="ADMIN_PASSWORD_CHANGED",
            entity_type="admin_user",
            entity_id=admin.id,
            admin_user_id=admin.id,
        )
        return admin

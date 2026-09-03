from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog
from app.repositories import AuditRepository


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = AuditRepository(db)

    async def log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str | UUID | None = None,
        admin_user_id: UUID | None = None,
        details: dict | str | None = None,
        ip_address: str | None = None,
    ) -> None:
        payload = details
        if isinstance(details, dict):
            payload = json.dumps(details, ensure_ascii=False, default=str)
        await self.repo.create(
            AuditLog(
                admin_user_id=admin_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                details=payload,
                ip_address=ip_address,
                created_at=datetime.now(timezone.utc),
            )
        )

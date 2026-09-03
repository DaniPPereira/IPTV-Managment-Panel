from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories import AccessLogRepository


class AccessService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = AccessLogRepository(db)
        self.settings = get_settings()

    async def purge_old_logs(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.settings.access_log_retention_days)
        return await self.repo.purge_older_than(cutoff)

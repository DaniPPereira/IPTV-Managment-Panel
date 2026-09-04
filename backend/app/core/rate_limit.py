from __future__ import annotations

from collections import defaultdict
from time import time

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import get_settings


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        now = time()
        bucket = self._hits[key]
        self._hits[key] = [t for t in bucket if now - t < window_seconds]
        if len(self._hits[key]) >= limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
        self._hits[key].append(now)


rate_limiter = InMemoryRateLimiter()

PUBLIC_PREFIXES = ("/m3u/", "/epg/", "/get.php", "/player_api.php", "/stalker_portal/", "/c/")


class PublicRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if any(path.startswith(prefix) or path == prefix.rstrip("/") for prefix in PUBLIC_PREFIXES):
            settings = get_settings()
            ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
                request.client.host if request.client else "unknown"
            )
            limit = settings.rate_limit_public_per_minute
            if path.startswith("/m3u/") or path.startswith("/epg/"):
                limit = max(10, limit // 2)
            rate_limiter.check(f"{ip}:{path.split('/')[1]}", limit=limit, window_seconds=60)
        return await call_next(request)

from __future__ import annotations

import time

import httpx

from app.core.config import get_settings
from app.providers.base import FetchResult, PlaylistProvider
from app.utils.ssrf import validate_public_url


class M3UProvider(PlaylistProvider):
    def __init__(self, *, allow_private: bool | None = None) -> None:
        settings = get_settings()
        self.timeout = settings.http_timeout_seconds
        self.max_bytes = settings.http_max_bytes
        self.max_redirects = settings.http_max_redirects
        self.allow_private = settings.allow_private_urls if allow_private is None else allow_private

    async def get_playlist(self, url: str) -> FetchResult:
        return await self._fetch(url, default_content_type="application/x-mpegURL")

    async def get_epg(self, url: str) -> FetchResult:
        return await self._fetch(url, default_content_type="application/xml")

    async def _fetch(self, url: str, *, default_content_type: str) -> FetchResult:
        validate_public_url(url, allow_private=self.allow_private)
        started = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            max_redirects=self.max_redirects,
        ) as client:
            async with client.stream("GET", url) as response:
                # Re-validate final URL after redirects
                validate_public_url(str(response.url), allow_private=self.allow_private)
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise ValueError("Remote content exceeds maximum allowed size")
                    chunks.append(chunk)
                content = b"".join(chunks)
                duration_ms = int((time.perf_counter() - started) * 1000)
                content_type = response.headers.get("content-type", default_content_type)
                return FetchResult(
                    content=content,
                    content_type=content_type,
                    http_status=response.status_code,
                    duration_ms=duration_ms,
                    etag=response.headers.get("etag"),
                    last_modified=response.headers.get("last-modified"),
                )

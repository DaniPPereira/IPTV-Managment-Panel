from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class ProviderResult:
    content: bytes
    content_type: str | None = None
    http_status: int = 200
    final_url: str | None = None
    etag: str | None = None
    last_modified: str | None = None


class M3UProvider:
    async def get_playlist(self, url: str) -> ProviderResult:
        return await self._fetch(
            url,
            default_content_type="application/x-mpegurl",
        )

    async def get_epg(self, url: str) -> ProviderResult:
        return await self._fetch(
            url,
            default_content_type="application/xml",
        )

    async def _fetch(self, url: str, default_content_type: str) -> ProviderResult:
        timeout = httpx.Timeout(
            connect=20.0,
            read=240.0,
            write=30.0,
            pool=20.0,
        )

        headers = {
            "User-Agent": "VLC/3.0.20 LibVLC/3.0.20",
            "Accept": "*/*",
            "Connection": "close",
        }

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)

            content = response.content

            if default_content_type == "application/x-mpegurl":
                content_type = "application/x-mpegurl"
            elif default_content_type == "application/xml":
                content_type = "application/xml"
            else:
                content_type = response.headers.get("content-type") or default_content_type

            return ProviderResult(
                content=content,
                content_type=content_type,
                http_status=response.status_code,
                final_url=str(response.url),
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
            )

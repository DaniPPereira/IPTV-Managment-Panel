from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class FetchResult:
    content: bytes
    content_type: str | None
    http_status: int
    duration_ms: int
    etag: str | None = None
    last_modified: str | None = None


class PlaylistProvider(ABC):
    @abstractmethod
    async def get_playlist(self, url: str) -> FetchResult:
        raise NotImplementedError

    @abstractmethod
    async def get_epg(self, url: str) -> FetchResult:
        raise NotImplementedError

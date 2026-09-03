from __future__ import annotations

import hashlib
import time
from pathlib import Path

from app.core.config import get_settings


class FileCache:
    def __init__(self, cache_dir: str | None = None) -> None:
        settings = get_settings()
        self.cache_dir = Path(cache_dir or settings.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str, kind: str) -> Path:
        digest = hashlib.sha256(f"{kind}:{key}".encode()).hexdigest()
        return self.cache_dir / f"{digest}.{kind}.cache"

    def get(self, key: str, kind: str, ttl_seconds: int) -> bytes | None:
        path = self._path(key, kind)
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > ttl_seconds:
            return None
        return path.read_bytes()

    def set(self, key: str, kind: str, content: bytes) -> None:
        path = self._path(key, kind)
        path.write_bytes(content)

    def invalidate(self, key: str, kind: str) -> None:
        path = self._path(key, kind)
        if path.exists():
            path.unlink()

    def meta_path(self, key: str, kind: str) -> Path:
        return self.cache_dir / f"{hashlib.sha256(f'{kind}:{key}'.encode()).hexdigest()}.{kind}.meta"

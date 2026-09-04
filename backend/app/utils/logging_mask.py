from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_KEYS = {
    "username",
    "user",
    "password",
    "pass",
    "pwd",
    "token",
    "auth",
    "key",
    "api_key",
    "apikey",
}


def mask_sensitive_url(url: str) -> str:
    """Mask credentials in query strings and basic-auth userinfo."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
        netloc = parts.netloc
        if "@" in netloc:
            host = netloc.rsplit("@", 1)[-1]
            netloc = f"***:***@{host}"
        query_pairs = []
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            if k.lower() in SENSITIVE_KEYS:
                query_pairs.append(f"{k}=***")
            else:
                query_pairs.append(urlencode([(k, v)]))
        return urlunsplit((parts.scheme, netloc, parts.path, "&".join(query_pairs), parts.fragment))
    except Exception:  # noqa: BLE001
        return re.sub(
            r"(?i)(username|password|token|pass|pwd|user)=([^&\s]+)",
            r"\1=***",
            url,
        )

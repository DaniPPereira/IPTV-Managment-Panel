from __future__ import annotations

import re
from dataclasses import dataclass


EXTINF_RE = re.compile(
    r'#EXTINF:-?\d+(?:\s+([^,]*))?,\s*(.*)$',
    re.IGNORECASE,
)
ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


@dataclass
class M3UChannel:
    id: str
    number: int
    name: str
    logo: str
    group: str
    url: str
    tvg_id: str = ""


def parse_m3u_channels(content: bytes | str, *, max_channels: int = 50_000) -> list[M3UChannel]:
    """Parse #EXTINF + URL pairs from an M3U playlist."""
    text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    channels: list[M3UChannel] = []
    pending_name = "Channel"
    pending_logo = ""
    pending_group = "General"
    pending_tvg = ""
    idx = 0

    for line in lines:
        if line.startswith("#EXTINF"):
            match = EXTINF_RE.match(line)
            attrs = ""
            name = "Channel"
            if match:
                attrs = match.group(1) or ""
                name = (match.group(2) or "Channel").strip() or "Channel"
            else:
                # Fallback: take text after last comma
                if "," in line:
                    name = line.split(",", 1)[1].strip() or "Channel"
            attr_map = dict(ATTR_RE.findall(attrs))
            pending_name = name
            pending_logo = attr_map.get("tvg-logo") or attr_map.get("logo") or ""
            pending_group = attr_map.get("group-title") or attr_map.get("group") or "General"
            pending_tvg = attr_map.get("tvg-id") or ""
            continue

        if line.startswith("#"):
            continue

        idx += 1
        channels.append(
            M3UChannel(
                id=str(idx),
                number=idx,
                name=pending_name,
                logo=pending_logo,
                group=pending_group,
                url=line,
                tvg_id=pending_tvg,
            )
        )
        pending_name = "Channel"
        pending_logo = ""
        pending_group = "General"
        pending_tvg = ""
        if len(channels) >= max_channels:
            break

    return channels

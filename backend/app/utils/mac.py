from __future__ import annotations

import re

MAC_PATTERN = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def normalize_mac(value: str) -> str:
    cleaned = value.strip().upper().replace("-", ":").replace(".", ":")
    if ":" not in cleaned and len(cleaned) == 12:
        cleaned = ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))
    # Collapse accidental double separators
    parts = [p for p in cleaned.split(":") if p]
    if len(parts) == 6 and all(len(p) == 2 for p in parts):
        normalized = ":".join(parts)
        if MAC_PATTERN.match(normalized):
            return normalized
    raise ValueError("Invalid MAC address format")


def is_valid_mac(value: str) -> bool:
    try:
        normalize_mac(value)
        return True
    except ValueError:
        return False

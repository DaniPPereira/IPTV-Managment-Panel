from __future__ import annotations

import pytest
from app.utils.mac import normalize_mac, is_valid_mac
from app.utils.status import compute_subscription_status
from app.models import SubscriptionStatus
from datetime import datetime, timedelta, timezone


def test_normalize_mac_hyphen():
    assert normalize_mac("00-1a-79-aa-bb-cc") == "00:1A:79:AA:BB:CC"


def test_normalize_mac_plain():
    assert normalize_mac("001a79aabbcc") == "00:1A:79:AA:BB:CC"


def test_invalid_mac():
    assert is_valid_mac("not-a-mac") is False
    with pytest.raises(ValueError):
        normalize_mac("zz:zz:zz:zz:zz:zz")


def test_status_active_expiring_expired_disabled():
    now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    assert (
        compute_subscription_status(
            client_active=True,
            subscription_active=True,
            expires_at=now + timedelta(days=30),
            now=now,
        )
        == SubscriptionStatus.ACTIVE
    )
    assert (
        compute_subscription_status(
            client_active=True,
            subscription_active=True,
            expires_at=now + timedelta(days=3),
            now=now,
        )
        == SubscriptionStatus.EXPIRING_SOON
    )
    assert (
        compute_subscription_status(
            client_active=True,
            subscription_active=True,
            expires_at=now - timedelta(days=1),
            now=now,
        )
        == SubscriptionStatus.EXPIRED
    )
    assert (
        compute_subscription_status(
            client_active=False,
            subscription_active=True,
            expires_at=now + timedelta(days=30),
            now=now,
        )
        == SubscriptionStatus.DISABLED
    )

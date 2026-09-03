from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.models import Client, Subscription, SubscriptionStatus


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def compute_subscription_status(
    *,
    client_active: bool,
    subscription_active: bool,
    expires_at: datetime,
    now: datetime | None = None,
    expiring_soon_days: int | None = None,
) -> SubscriptionStatus:
    current = ensure_utc(now or datetime.now(timezone.utc))
    expires_at = ensure_utc(expires_at)

    if not client_active or not subscription_active:
        return SubscriptionStatus.DISABLED
    if expires_at <= current:
        return SubscriptionStatus.EXPIRED

    days = expiring_soon_days if expiring_soon_days is not None else get_settings().expiring_soon_days
    if expires_at <= current + timedelta(days=days):
        return SubscriptionStatus.EXPIRING_SOON
    return SubscriptionStatus.ACTIVE


def status_for_subscription(subscription: Subscription, client: Client | None = None) -> SubscriptionStatus:
    if client is not None:
        client_active = client.active
    else:
        # Use already-loaded relationship only — avoid lazy IO in async context
        loaded = subscription.__dict__.get("client")
        client_active = loaded.active if loaded is not None else True
    return compute_subscription_status(
        client_active=client_active,
        subscription_active=subscription.active,
        expires_at=subscription.expires_at,
    )

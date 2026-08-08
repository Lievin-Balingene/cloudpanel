"""Rate-limit simple des messages assistant (anti-abus)."""
from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

from apps.core.exceptions import VZoneAPIException


def assert_ai_rate_limit(user_id: int) -> None:
    limit = int(getattr(settings, "VZONE_AI_RATE_LIMIT_PER_MIN", 20) or 20)
    if limit <= 0:
        return
    key = f"vzone:ai:rl:{user_id}"
    count = cache.get(key)
    if count is None:
        cache.set(key, 1, timeout=60)
        return
    if int(count) >= limit:
        raise VZoneAPIException(
            detail=f"Trop de messages IA ({limit}/min). Réessayez dans une minute.",
            code="ai_rate_limited",
            status_code=429,
        )
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, int(count) + 1, timeout=60)

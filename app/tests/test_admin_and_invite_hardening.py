"""
Tests admin-route protection (require_admin) and invite-redemption rate
limiting's fail-closed behavior.

NOT EXECUTED in this sandbox: needs sqlalchemy (User is a SQLAlchemy
model) and redis, neither installed offline. Syntax-checked only.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.deps import require_admin
from app.core.rate_limit import RateLimiterUnavailable, is_rate_limited
from app.models.user import User


def _make_user(role: str) -> User:
    return User(
        id="user-1", email="test@example.com", password_hash="x",
        display_name="Test", role=role, status="active",
    )


@pytest.mark.asyncio
async def test_require_admin_allows_admin_role():
    admin = _make_user("admin")
    result = await require_admin(user=admin)
    assert result is admin


@pytest.mark.asyncio
async def test_require_admin_rejects_member_role():
    member = _make_user("member")
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user=member)
    assert exc_info.value.status_code == 403


class _BrokenRedis:
    async def incr(self, key):
        raise RedisConnectionError("connection refused")


@pytest.mark.asyncio
async def test_invite_validation_rate_limit_fails_closed_on_redis_outage():
    """Invite-code validation must fail closed - an attacker enumerating
    codes during a Redis outage must be blocked, not waved through."""
    with patch("app.core.rate_limit.get_redis", return_value=_BrokenRedis()):
        with pytest.raises(RateLimiterUnavailable):
            await is_rate_limited("invite-validate:1.2.3.4", max_requests=10)


@pytest.mark.asyncio
async def test_signup_rate_limit_fails_closed_on_redis_outage():
    """Signup (where invite redemption actually happens) must also fail
    closed - same reasoning as invite validation above."""
    with patch("app.core.rate_limit.get_redis", return_value=_BrokenRedis()):
        with pytest.raises(RateLimiterUnavailable):
            await is_rate_limited("signup:1.2.3.4", max_requests=5)

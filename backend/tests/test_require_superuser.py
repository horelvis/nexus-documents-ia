"""Tests for require_superuser FastAPI dependency.

Validates that the centralized superuser gate (used by every admin-only
endpoint, starting with the agents catalog) returns the profile when
is_superuser is True and raises HTTPException(403) otherwise.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.auth.base import UserProfile
from app.core.auth.superuser import require_superuser


def _profile(*, is_superuser: bool) -> UserProfile:
    return UserProfile(
        sub="00000000-0000-0000-0000-000000000001",
        email="user@example.com",
        name="Test User",
        roles=[],
        is_superuser=is_superuser,
    )


@pytest.mark.asyncio
async def test_require_superuser_passes_for_admin() -> None:
    profile = _profile(is_superuser=True)
    result = await require_superuser(current_user=profile)
    assert result is profile


@pytest.mark.asyncio
async def test_require_superuser_rejects_non_admin() -> None:
    profile = _profile(is_superuser=False)
    with pytest.raises(HTTPException) as exc:
        await require_superuser(current_user=profile)
    assert exc.value.status_code == 403
    assert "superuser" in exc.value.detail.lower()

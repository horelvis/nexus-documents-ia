"""
Tests for security module – API key validation and tenant context.
"""

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.core.security import verify_api_key


# Read the actual API key from the environment
REAL_API_KEY = os.environ.get("MICROSERVICES_API_KEY", "test-api-key")


class TestVerifyAPIKey:
    """Test API key verification."""

    @pytest.mark.asyncio
    async def test_valid_key(self):
        result = await verify_api_key(x_api_key=REAL_API_KEY)
        assert result is True

    @pytest.mark.asyncio
    async def test_missing_key(self):
        with pytest.raises(HTTPException) as exc:
            await verify_api_key(x_api_key=None)
        assert exc.value.status_code == 401
        assert "Missing" in exc.value.detail

    @pytest.mark.asyncio
    async def test_invalid_key(self):
        with pytest.raises(HTTPException) as exc:
            await verify_api_key(x_api_key="wrong-key")
        assert exc.value.status_code == 401
        assert "Invalid" in exc.value.detail

    @pytest.mark.asyncio
    async def test_no_key_configured_allows_all(self):
        """When MICROSERVICES_API_KEY is empty, all requests are allowed (dev mode)."""
        with patch("app.core.security.settings") as mock_settings:
            mock_settings.MICROSERVICES_API_KEY = ""
            result = await verify_api_key(x_api_key=None)
            assert result is True

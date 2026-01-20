#!/usr/bin/env python3
"""
Test Alfresco connector health check.

Usage:
    python scripts/test_alfresco_health.py
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.connector_health_service import ConnectorHealthService


async def main():
    """Test Alfresco health check."""
    # Alfresco configuration from database
    config = {
        "url": "http://gestordocumental-des.apml.local",
        "username": "admin",
        "password": "admin",
        "default_site_id": "gdapm",
        "api_path": "/alfresco/api/-default-/public/alfresco/versions/1",
        "search_api_path": "/alfresco/api/-default-/public/search/versions/1"
    }

    print("=" * 60)
    print("Testing Alfresco Health Check")
    print("=" * 60)
    print(f"URL: {config['url']}")
    print(f"User: {config['username']}")
    print(f"Site: {config['default_site_id']}")
    print("-" * 60)

    health_service = ConnectorHealthService(timeout=30)
    result = await health_service.check_health("alfresco", config)

    print(f"\nStatus: {result.status.upper()}")
    print(f"Message: {result.message}")
    print(f"Response Time: {result.response_time_ms:.2f} ms")
    print("\nDetails:")
    for key, value in result.details.items():
        print(f"  {key}: {value}")

    print("=" * 60)

    return result.status


if __name__ == "__main__":
    status = asyncio.run(main())
    sys.exit(0 if status in ["healthy", "degraded"] else 1)

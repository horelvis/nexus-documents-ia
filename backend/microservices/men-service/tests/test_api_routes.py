"""
Tests for main API routes – /men/query, /men/decide, /men/health, /men/status.
"""

import pytest

from tests.conftest import auth_headers


class TestHealthEndpoint:
    """GET /men/health – no auth required."""

    def test_health_returns_200(self, client):
        r = client.get("/men/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert data["loaded"] is True
        assert data["orchestrator_loaded"] is True
        assert data["modeler_loaded"] is True

    def test_health_includes_service_info(self, client):
        r = client.get("/men/health")
        data = r.json()
        assert data["service"] == "men-service"
        assert "version" in data


class TestStatusEndpoint:
    """GET /men/status – requires auth."""

    def test_status_requires_api_key(self, client):
        r = client.get("/men/status")
        assert r.status_code == 401

    def test_status_returns_details(self, client):
        r = client.get("/men/status", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()
        assert data["loaded"] is True
        assert "loaded_experts" in data
        assert "active_sessions" in data
        assert "vram_estimate" in data
        assert data["vram_estimate"]["base_total"] == 4.0


class TestQueryEndpoint:
    """POST /men/query – full pipeline."""

    def test_query_requires_api_key(self, client):
        r = client.post("/men/query", json={"query": "test", "tenant_id": "t1"})
        assert r.status_code == 401

    def test_query_basic(self, client):
        r = client.post(
            "/men/query",
            headers=auth_headers(),
            json={
                "query": "¿Qué dice la ley sobre arrendamientos?",
                "tenant_id": "tenant-test",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "response" in data
        assert data["domain"] == "legal"
        assert data["tenant_id"] == "tenant-test"
        assert data["session_id"] == "default"

    def test_query_with_session(self, client):
        r = client.post(
            "/men/query",
            headers=auth_headers(),
            json={
                "query": "Consulta 1",
                "tenant_id": "t1",
                "session_id": "custom-session",
            },
        )
        assert r.status_code == 200
        assert r.json()["session_id"] == "custom-session"

    def test_query_with_tenant_schema(self, client):
        r = client.post(
            "/men/query",
            headers=auth_headers(),
            json={
                "query": "¿Cuántos contratos tiene ACME?",
                "tenant_id": "t1",
                "tenant_schema": {
                    "tenant_name": "TestCorp",
                    "document_types": ["contrato"],
                },
            },
        )
        assert r.status_code == 200

    def test_query_validation_empty_query(self, client):
        r = client.post(
            "/men/query",
            headers=auth_headers(),
            json={"query": "", "tenant_id": "t1"},
        )
        assert r.status_code == 422  # validation error

    def test_query_validation_missing_tenant(self, client):
        r = client.post(
            "/men/query",
            headers=auth_headers(),
            json={"query": "test"},
        )
        assert r.status_code == 422


class TestDecideEndpoint:
    """POST /men/decide – classification only."""

    def test_decide_requires_api_key(self, client):
        r = client.post("/men/decide", json={"query": "test"})
        assert r.status_code == 401

    def test_decide_basic(self, client):
        r = client.post(
            "/men/decide",
            headers=auth_headers(),
            json={"query": "¿Es legal este contrato?"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["domain"] == "legal"
        assert 0 <= data["confidence"] <= 1
        assert isinstance(data["requires_expert"], bool)

    def test_decide_validation_empty(self, client):
        r = client.post(
            "/men/decide",
            headers=auth_headers(),
            json={"query": ""},
        )
        assert r.status_code == 422


class TestRootEndpoint:
    """GET / – service info."""

    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "men-service"
        assert "endpoints" in data

    def test_root_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] in ("healthy", "starting")

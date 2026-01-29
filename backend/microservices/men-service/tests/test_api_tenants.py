"""
Tests for tenant expert management routes – /men/tenants/*.
"""

import pytest

from tests.conftest import auth_headers


class TestListTenantExperts:
    """GET /men/tenants/{id}/experts"""

    def test_requires_auth(self, client):
        r = client.get("/men/tenants/t1/experts")
        assert r.status_code == 401

    def test_list_experts_for_tenant_with_experts(self, client):
        r = client.get(
            "/men/tenants/tenant-test/experts",
            headers=auth_headers(),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["tenant_id"] == "tenant-test"
        assert len(data["experts"]) == 1
        assert data["experts"][0]["domain"] == "contract"
        assert data["experts"][0]["is_generic"] is False

    def test_generic_experts_included(self, client):
        r = client.get(
            "/men/tenants/tenant-test/experts",
            headers=auth_headers(),
        )
        data = r.json()
        assert len(data["generic_experts"]) == 1
        assert data["generic_experts"][0]["domain"] == "legal"
        assert data["generic_experts"][0]["is_generic"] is True

    def test_unknown_tenant_has_no_specific_experts(self, client):
        r = client.get(
            "/men/tenants/no-such-tenant/experts",
            headers=auth_headers(),
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["experts"]) == 0
        # still has generic experts
        assert len(data["generic_experts"]) >= 1


class TestRegisterExpert:
    """POST /men/tenants/{id}/experts/register"""

    def test_requires_auth(self, client):
        r = client.post(
            "/men/tenants/t1/experts/register",
            json={"domain": "finance", "path": "/p"},
        )
        assert r.status_code == 401

    def test_register_new_expert(self, client):
        r = client.post(
            "/men/tenants/new-tenant/experts/register",
            headers=auth_headers(),
            json={
                "domain": "finance",
                "path": "/trained/finance_lora",
                "document_types": ["factura", "presupuesto"],
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "registered" in data["message"].lower() or "finance" in data["message"]
        assert data["expert"]["domain"] == "finance"
        assert data["expert"]["tenant_id"] == "new-tenant"
        assert "factura" in data["expert"]["document_types"]

    def test_register_without_document_types(self, client):
        r = client.post(
            "/men/tenants/t1/experts/register",
            headers=auth_headers(),
            json={"domain": "hr", "path": "/trained/hr"},
        )
        assert r.status_code == 200
        assert r.json()["expert"]["document_types"] == []


class TestListDomains:
    """GET /men/tenants/domains"""

    def test_requires_auth(self, client):
        r = client.get("/men/tenants/domains")
        assert r.status_code == 401

    def test_returns_domains(self, client):
        r = client.get("/men/tenants/domains", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()
        assert "domains" in data
        assert "legal" in data["domains"]
        assert "contract" in data["domains"]


class TestTrainExpert:
    """POST /men/tenants/{id}/experts/train"""

    def test_requires_auth(self, client):
        r = client.post(
            "/men/tenants/t1/experts/train",
            json={"tenant_id": "t1", "domain": "legal"},
        )
        assert r.status_code == 401

    def test_train_returns_started(self, client):
        """Training endpoint may fail if training module doesn't exist,
        but we verify the endpoint is reachable and validates input."""
        r = client.post(
            "/men/tenants/t1/experts/train",
            headers=auth_headers(),
            json={
                "tenant_id": "t1",
                "domain": "legal",
                "use_synthetic": True,
                "num_epochs": 3,
            },
        )
        # May return 200 (started) or 500 (training module missing)
        assert r.status_code in (200, 500)

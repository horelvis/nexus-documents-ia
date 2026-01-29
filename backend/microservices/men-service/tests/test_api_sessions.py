"""
Tests for session management routes – /men/sessions/*.
"""

import pytest

from tests.conftest import auth_headers


class TestSessionHistory:
    """GET /men/sessions/{id}/history"""

    def test_requires_auth(self, client):
        r = client.get("/men/sessions/s1/history?tenant_id=t1")
        assert r.status_code == 401

    def test_empty_history(self, client):
        r = client.get(
            "/men/sessions/new-session/history?tenant_id=t1",
            headers=auth_headers(),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == "new-session"
        assert data["tenant_id"] == "t1"
        assert data["history"] == []
        assert data["message_count"] == 0

    def test_history_after_query(self, client):
        # First, make a query to populate history
        client.post(
            "/men/query",
            headers=auth_headers(),
            json={
                "query": "Pregunta de prueba",
                "tenant_id": "t1",
                "session_id": "hist-test",
            },
        )

        # Then fetch history
        r = client.get(
            "/men/sessions/hist-test/history?tenant_id=t1",
            headers=auth_headers(),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["message_count"] == 2
        assert data["history"][0]["role"] == "user"
        assert data["history"][1]["role"] == "assistant"

    def test_requires_tenant_id(self, client):
        r = client.get(
            "/men/sessions/s1/history",
            headers=auth_headers(),
        )
        assert r.status_code == 422  # missing required query param


class TestClearSession:
    """POST /men/sessions/{id}/clear"""

    def test_requires_auth(self, client):
        r = client.post("/men/sessions/s1/clear?tenant_id=t1")
        assert r.status_code == 401

    def test_clear_existing_session(self, client):
        # Create session
        client.post(
            "/men/query",
            headers=auth_headers(),
            json={"query": "test", "tenant_id": "t1", "session_id": "to-clear"},
        )

        # Clear it
        r = client.post(
            "/men/sessions/to-clear/clear?tenant_id=t1",
            headers=auth_headers(),
        )
        assert r.status_code == 200
        data = r.json()
        assert data["cleared"] is True
        assert data["session_id"] == "to-clear"

    def test_clear_nonexistent_session(self, client):
        r = client.post(
            "/men/sessions/no-existe/clear?tenant_id=t1",
            headers=auth_headers(),
        )
        assert r.status_code == 200
        assert r.json()["cleared"] is False


class TestActiveSessions:
    """GET /men/sessions/active"""

    def test_requires_auth(self, client):
        r = client.get("/men/sessions/active")
        assert r.status_code == 401

    def test_no_active_sessions(self, client):
        r = client.get("/men/sessions/active", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["sessions"] == []

    def test_lists_sessions_after_queries(self, client):
        for sid in ["a", "b"]:
            client.post(
                "/men/query",
                headers=auth_headers(),
                json={"query": "test", "tenant_id": "t1", "session_id": sid},
            )

        r = client.get("/men/sessions/active", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2

    def test_filter_by_tenant(self, client):
        for tid, sid in [("t1", "s1"), ("t2", "s2")]:
            client.post(
                "/men/query",
                headers=auth_headers(),
                json={"query": "test", "tenant_id": tid, "session_id": sid},
            )

        r = client.get(
            "/men/sessions/active?tenant_id=t1",
            headers=auth_headers(),
        )
        assert r.status_code == 200
        sessions = r.json()["sessions"]
        assert all("t1:" in s for s in sessions)

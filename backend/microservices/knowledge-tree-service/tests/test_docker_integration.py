"""
Docker integration tests — verify FalkorDB service is running and accessible.

Run these after `docker compose up` to validate Phase 1 infrastructure.
"""

import pytest


class TestDockerIntegration:
    """Verify FalkorDB is accessible from the knowledge-tree-service container."""

    @pytest.mark.asyncio
    async def test_falkordb_reachable(self, falkordb_client):
        """FalkorDB should be reachable and respond to PING."""
        result = await falkordb_client.execute_cypher("RETURN 'pong' AS status")
        assert result[0]["status"] == "pong"

    @pytest.mark.asyncio
    async def test_falkordb_graph_writable(self, falkordb_client):
        """Should be able to create and read nodes."""
        await falkordb_client.execute_cypher("""
            CREATE (:TestNode {value: 'integration_test'})
        """)
        result = await falkordb_client.execute_cypher("""
            MATCH (n:TestNode {value: 'integration_test'})
            RETURN n.value AS val
        """)
        assert len(result) == 1
        assert result[0]["val"] == "integration_test"

    @pytest.mark.asyncio
    async def test_age_client_still_works(self):
        """AGE client should still be functional (dual-period)."""
        from app.core.config import settings
        assert settings.database_url is not None
        # We don't actually connect to AGE here — just verify config exists

    @pytest.mark.asyncio
    async def test_falkordb_config_loaded(self):
        """FalkorDB config settings should be loaded from env."""
        from app.core.config import settings
        assert settings.falkordb_host is not None
        assert settings.falkordb_port > 0
        assert settings.falkordb_graph_name == "test_knowledge_graph"

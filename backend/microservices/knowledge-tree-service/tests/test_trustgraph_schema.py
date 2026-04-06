"""
Tests for TrustGraph schema bootstrap — Phase 1.

Verifies that the trustgraph_schema.cypher indexes are created correctly
on the :Node, :Literal, :Rel, and :CollectionMetadata labels.

Requires a running FalkorDB instance (docker-compose.onpremise.yml, port 6380).
"""

import pytest


# ---------------------------------------------------------------------------
# 1. Schema bootstrap
# ---------------------------------------------------------------------------


class TestTrustGraphSchema:
    """Verify the TrustGraph schema bootstraps correctly."""

    @pytest.mark.asyncio
    async def test_bootstrap_schema_creates_indexes(self, falkordb_client):
        """bootstrap_schema() should create indexes for all TrustGraph labels.

        FalkorDB consolidates multiple CREATE INDEX statements for the same label
        into a single compound index entry, so 9 schema statements produce 4
        distinct index entries (one per label: Node, Literal, Rel, CollectionMetadata).
        """
        await falkordb_client.bootstrap_schema()

        result = await falkordb_client.execute_cypher("CALL db.indexes()")
        assert len(result) >= 4, (
            f"Expected >= 4 indexes after bootstrap, got {len(result)}: {result}"
        )

        # Verify each expected label has an index entry
        indexed_labels = {row["label"] for row in result}
        for expected_label in ("Node", "Literal", "Rel", "CollectionMetadata"):
            assert expected_label in indexed_labels, (
                f"Missing index for label '{expected_label}'. Found: {indexed_labels}"
            )

    @pytest.mark.asyncio
    async def test_bootstrap_schema_idempotent(self, falkordb_client):
        """Running bootstrap_schema() twice should not raise an error."""
        await falkordb_client.bootstrap_schema()
        # Second call must not raise
        await falkordb_client.bootstrap_schema()

        result = await falkordb_client.execute_cypher("CALL db.indexes()")
        assert len(result) >= 4

    # ---------------------------------------------------------------------------
    # 2. Functional index verification
    # ---------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_node_uri_index_works(self, falkordb_client):
        """CREATE + MATCH by uri should work after schema bootstrap."""
        await falkordb_client.bootstrap_schema()

        # Create a :Node with a uri
        await falkordb_client.execute_cypher(
            "CREATE (n:Node {uri: $uri, user: $user, collection: $collection})",
            params={"uri": "urn:test:node:001", "user": "user1", "collection": "col1"},
        )

        # Match by uri — should return exactly one result
        rows = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri}) RETURN n.uri AS uri",
            params={"uri": "urn:test:node:001"},
        )
        assert len(rows) == 1
        assert rows[0]["uri"] == "urn:test:node:001"

    @pytest.mark.asyncio
    async def test_literal_dedup_key(self, falkordb_client):
        """Two MERGEs with same (value, user, collection) produce one :Literal node."""
        await falkordb_client.bootstrap_schema()

        merge_query = (
            "MERGE (l:Literal {value: $value, user: $user, collection: $collection})"
        )
        params = {"value": "hello world", "user": "user1", "collection": "col1"}

        await falkordb_client.execute_cypher(merge_query, params=params)
        await falkordb_client.execute_cypher(merge_query, params=params)

        rows = await falkordb_client.execute_cypher(
            "MATCH (l:Literal {value: $value, user: $user, collection: $collection}) "
            "RETURN count(l) AS cnt",
            params=params,
        )
        assert rows[0]["cnt"] == 1, (
            f"Expected 1 :Literal node after two identical MERGEs, got {rows[0]['cnt']}"
        )

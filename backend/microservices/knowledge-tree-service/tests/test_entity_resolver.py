"""Pure-logic tests for EntityResolver helpers.

Excludes the FalkorDB-backed flows (resolve_entities_of_type, _merge_node)
which are exercised in test_integration_pipeline.py with a live graph.
"""

from app.services.entity_resolver import EntityResolver


class TestRejectDistinctNumericMembers:
    """Address-level disambiguation for places.

    Two place labels with different numeric tokens (street numbers) must
    not be fused even if the LLM phase or fuzzy heuristics suggested it.
    """

    def test_keeps_cluster_when_numbers_match(self):
        clusters = [{
            "canonical_uri": "nouxcube://entity/default/calle-mayor-5",
            "member_uris": [
                "nouxcube://entity/default/calle-mayor-5",
                "nouxcube://entity/default/calle-mayor-numero-5",
            ],
        }]
        uri_to_label = {
            "nouxcube://entity/default/calle-mayor-5": "Calle Mayor 5",
            "nouxcube://entity/default/calle-mayor-numero-5": "Calle Mayor número 5",
        }
        out = EntityResolver._reject_distinct_numeric_members(clusters, uri_to_label)
        assert len(out) == 1
        assert len(out[0]["member_uris"]) == 2

    def test_drops_member_with_different_number(self):
        clusters = [{
            "canonical_uri": "nouxcube://entity/default/calle-mayor-5",
            "member_uris": [
                "nouxcube://entity/default/calle-mayor-5",
                "nouxcube://entity/default/calle-mayor-47",
            ],
        }]
        uri_to_label = {
            "nouxcube://entity/default/calle-mayor-5": "Calle Mayor 5",
            "nouxcube://entity/default/calle-mayor-47": "Calle Mayor 47",
        }
        out = EntityResolver._reject_distinct_numeric_members(clusters, uri_to_label)
        # Cluster collapses to canonical-only → no merge to perform.
        assert out == []

    def test_keeps_member_when_only_one_has_number(self):
        clusters = [{
            "canonical_uri": "nouxcube://entity/default/avenida-america",
            "member_uris": [
                "nouxcube://entity/default/avenida-america",
                "nouxcube://entity/default/avenida-america-12",
            ],
        }]
        uri_to_label = {
            "nouxcube://entity/default/avenida-america": "Avenida América",
            "nouxcube://entity/default/avenida-america-12": "Avenida América 12",
        }
        out = EntityResolver._reject_distinct_numeric_members(clusters, uri_to_label)
        # Conservative: missing number on one side does not block the merge.
        assert len(out) == 1
        assert len(out[0]["member_uris"]) == 2

    def test_partial_drop_keeps_compatible_members(self):
        clusters = [{
            "canonical_uri": "nouxcube://entity/default/calle-mayor-5",
            "member_uris": [
                "nouxcube://entity/default/calle-mayor-5",
                "nouxcube://entity/default/calle-mayor-numero-5",
                "nouxcube://entity/default/calle-mayor-47",
            ],
        }]
        uri_to_label = {
            "nouxcube://entity/default/calle-mayor-5": "Calle Mayor 5",
            "nouxcube://entity/default/calle-mayor-numero-5": "Calle Mayor número 5",
            "nouxcube://entity/default/calle-mayor-47": "Calle Mayor 47",
        }
        out = EntityResolver._reject_distinct_numeric_members(clusters, uri_to_label)
        assert len(out) == 1
        members = out[0]["member_uris"]
        assert "nouxcube://entity/default/calle-mayor-5" in members
        assert "nouxcube://entity/default/calle-mayor-numero-5" in members
        assert "nouxcube://entity/default/calle-mayor-47" not in members

    def test_no_labels_falls_back_to_passthrough(self):
        clusters = [{
            "canonical_uri": "nouxcube://entity/default/x",
            "member_uris": [
                "nouxcube://entity/default/x",
                "nouxcube://entity/default/y",
            ],
        }]
        # Empty label map — no numeric info to compare, must not block.
        out = EntityResolver._reject_distinct_numeric_members(clusters, {})
        assert len(out) == 1
        assert len(out[0]["member_uris"]) == 2

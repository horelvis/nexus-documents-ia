"""Tests for Cypher template executor."""

import pytest
from app.services.template_executor import TemplateExecutor


class TestTemplateLoading:
    def test_loads_templates_from_yaml(self):
        executor = TemplateExecutor()
        assert "entity_relations" in executor.templates
        assert "corporate_chain" in executor.templates
        assert "org_people" in executor.templates
        assert "count_by_predicate" in executor.templates
        assert "applicable_regulations" in executor.templates

    def test_template_has_required_fields(self):
        executor = TemplateExecutor()
        tmpl = executor.templates["entity_relations"]
        assert "pattern" in tmpl
        assert "description" in tmpl
        assert "hops" in tmpl

    def test_list_templates_returns_metadata(self):
        executor = TemplateExecutor()
        listing = executor.list_templates()
        assert len(listing) >= 5
        assert all("name" in t and "description" in t and "hops" in t for t in listing)

    def test_unknown_template_raises(self):
        executor = TemplateExecutor()
        with pytest.raises(KeyError, match="nonexistent"):
            executor.get_template("nonexistent")


class TestTemplateBuilding:
    def test_build_query_returns_cypher(self):
        executor = TemplateExecutor()
        query = executor.build_query("entity_relations")
        assert "MATCH" in query
        assert "$entity_uri" in query or "$user" in query

    def test_build_params_includes_defaults(self):
        executor = TemplateExecutor()
        params = executor.build_params(
            "entity_relations",

            entity_uri="nouxcube://entity/default/juan",
        )
        assert params["user"] == "test-user"
        assert params["entity_uri"] == "nouxcube://entity/default/juan"
        assert "query_limit" in params

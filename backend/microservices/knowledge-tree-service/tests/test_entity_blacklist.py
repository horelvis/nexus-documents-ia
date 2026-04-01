"""Tests for entity blacklist loading and matching."""

import pytest
import app.services.entity_blacklist as _blacklist_module
from app.services.entity_blacklist import EntityBlacklist


@pytest.fixture(autouse=True)
def reset_blacklist_singleton():
    """Reset the module-level singleton before each test to ensure a clean load."""
    _blacklist_module._loaded_terms = None
    yield
    _blacklist_module._loaded_terms = None


class TestEntityBlacklistLoad:
    def test_loads_from_yaml(self):
        bl = EntityBlacklist()
        assert len(bl.terms) > 0

    def test_contains_known_generic_terms(self):
        bl = EntityBlacklist()
        assert bl.is_blacklisted("mayor de edad")
        assert bl.is_blacklisted("conyuge")
        assert bl.is_blacklisted("herederos forzosos")

    def test_case_insensitive(self):
        bl = EntityBlacklist()
        assert bl.is_blacklisted("Mayor de Edad")
        assert bl.is_blacklisted("CONYUGE")

    def test_accent_insensitive(self):
        bl = EntityBlacklist()
        assert bl.is_blacklisted("cónyuge")

    def test_does_not_match_real_entities(self):
        bl = EntityBlacklist()
        assert not bl.is_blacklisted("Juan García López")
        assert not bl.is_blacklisted("ACME S.L.")
        assert not bl.is_blacklisted("Ley 31/1995")

    def test_does_not_match_empty_string(self):
        bl = EntityBlacklist()
        assert not bl.is_blacklisted("")
        assert not bl.is_blacklisted("   ")


class TestEntityBlacklistSingleton:
    def test_same_instance(self):
        bl1 = EntityBlacklist()
        bl2 = EntityBlacklist()
        # Both should use the same loaded terms set
        assert bl1.terms is bl2.terms

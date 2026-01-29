"""
Tests for LLMModeler – response synthesis and conversational memory.

The actual model is NOT loaded; we test memory management,
session handling, and state.
"""

import pytest

from app.services.llm_modeler import LLMModeler


class TestModelerInit:
    """Test initialization and defaults."""

    def test_default_values(self):
        m = LLMModeler()
        assert m.model_name == "Qwen/Qwen2.5-3B-Instruct"
        assert m.max_history_turns == 5
        assert m.max_tokens == 500
        assert m.temperature == 0.7
        assert m.is_loaded is False

    def test_custom_values(self):
        m = LLMModeler(max_history_turns=10, max_tokens=1024, temperature=0.3)
        assert m.max_history_turns == 10
        assert m.max_tokens == 1024
        assert m.temperature == 0.3


class TestHistoryManagement:
    """Test in-memory conversation history (no model needed)."""

    @pytest.fixture(autouse=True)
    def _modeler(self):
        self.m = LLMModeler()
        # Directly manipulate history without loading model
        self.m._history = {}

    def test_empty_history(self):
        assert self.m.get_history("nonexistent") == []

    def test_add_and_retrieve_history(self):
        self.m._history["s1"] = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Buenos días"},
        ]
        h = self.m.get_history("s1")
        assert len(h) == 2
        assert h[0]["role"] == "user"

    def test_get_history_returns_copy(self):
        self.m._history["s1"] = [{"role": "user", "content": "X"}]
        h = self.m.get_history("s1")
        h.append({"role": "assistant", "content": "Y"})
        assert len(self.m._history["s1"]) == 1  # original unchanged

    def test_clear_history(self):
        self.m._history["s1"] = [{"role": "user", "content": "X"}]
        assert self.m.clear_history("s1") is True
        assert self.m.get_history("s1") == []

    def test_clear_nonexistent(self):
        assert self.m.clear_history("nope") is False

    def test_get_all_sessions(self):
        self.m._history["a"] = []
        self.m._history["b"] = []
        sessions = self.m.get_all_sessions()
        assert set(sessions) == {"a", "b"}

    def test_get_session_count(self):
        self.m._history["a"] = []
        self.m._history["b"] = []
        self.m._history["c"] = []
        assert self.m.get_session_count() == 3


class TestModelerState:
    """Test load/unload state transitions."""

    def test_not_loaded_initially(self):
        m = LLMModeler()
        assert m.is_loaded is False
        assert m.model is None
        assert m.tokenizer is None

    def test_unload_when_not_loaded(self):
        m = LLMModeler()
        m.unload()  # should not raise
        assert m.is_loaded is False


class TestSystemPrompt:
    """Test system prompt template."""

    def test_prompt_is_spanish(self):
        assert "Emma" in LLMModeler.SYSTEM_PROMPT_BASE
        assert "gestión documental" in LLMModeler.SYSTEM_PROMPT_BASE

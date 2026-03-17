"""Tests for phase_update event mapping in the langgraph adapter."""

import pytest
from app.services.langgraph_adapter import PHASE_MAP, PHASE_ORDER, PHASE_LABELS


class TestPhaseMapping:
    def test_all_phases_have_labels(self):
        for phase in PHASE_ORDER:
            assert phase in PHASE_LABELS

    def test_tool_call_maps_to_searching(self):
        assert PHASE_MAP["tool_call"] == "searching"

    def test_token_maps_to_responding(self):
        assert PHASE_MAP["token"] == "responding"

    def test_started_maps_to_understanding(self):
        assert PHASE_MAP["started"] == "understanding"

    def test_swarm_started_maps_to_analyzing(self):
        assert PHASE_MAP["swarm_started"] == "analyzing"

    def test_phase_order_has_four_phases(self):
        assert len(PHASE_ORDER) == 4

    def test_fast_path_uses_two_phases(self):
        """Fast path only goes through understanding → responding."""
        fast_path_events = ["started", "token"]
        phases = [PHASE_MAP[e] for e in fast_path_events]
        assert phases == ["understanding", "responding"]

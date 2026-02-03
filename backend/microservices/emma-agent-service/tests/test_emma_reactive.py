"""
Tests for Emma Reactive System — Event-Driven Proactive AI

Covers:
1. Event schemas (EmmaEvent serialization roundtrip, EventFilter matching)
2. Event pattern parsing and matching (pure functions)
3. EventBus publish/subscribe/ack (mocked Redis)
4. TriggerEngine CRUD + evaluate_event (mocked Redis)
5. NotificationService create/read/mark (mocked Redis)
6. PairingService generate/confirm/revoke (mocked Redis)
7. ChannelRouter inbound flow with mocked channels
8. End-to-end scenario: event → trigger → notification
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime, timezone

from app.schemas.events import EmmaEvent, EventFilter, EventType
from app.services.trigger_engine import (
    parse_event_pattern,
    event_matches_pattern,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────


def _make_event(**kwargs) -> EmmaEvent:
    """Create an EmmaEvent with sensible defaults."""
    defaults = {
        "event_type": "document.indexed",
        "tenant_id": "tenant-001",
        "payload": {"doc_id": "doc-123", "collection": "contracts"},
        "source_service": "weaviate-service",
    }
    defaults.update(kwargs)
    return EmmaEvent(**defaults)


class FakeRedis:
    """In-memory Redis mock that supports the async API used by services."""

    def __init__(self):
        self._store: dict = {}
        self._lists: dict = {}
        self._sets: dict = {}
        self._published: list = []

    async def set(self, key, value, ex=None):
        self._store[key] = value

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                count += 1
        return count

    async def sadd(self, key, *values):
        if key not in self._sets:
            self._sets[key] = set()
        self._sets[key].update(values)

    async def smembers(self, key):
        return self._sets.get(key, set())

    async def srem(self, key, *values):
        s = self._sets.get(key, set())
        for v in values:
            s.discard(v)

    async def lpush(self, key, *values):
        if key not in self._lists:
            self._lists[key] = []
        for v in values:
            self._lists[key].insert(0, v)

    async def ltrim(self, key, start, end):
        if key in self._lists:
            self._lists[key] = self._lists[key][start:end + 1]

    async def lrange(self, key, start, end):
        lst = self._lists.get(key, [])
        if end == -1:
            return lst[start:]
        return lst[start:end + 1]

    async def lset(self, key, index, value):
        self._lists[key][index] = value

    async def publish(self, channel, message):
        self._published.append((channel, message))

    async def scan_iter(self, match=None, count=100):
        import fnmatch
        for key in list(self._store.keys()):
            if match and not fnmatch.fnmatch(key, match):
                continue
            yield key

    async def xadd(self, stream, data, maxlen=None, approximate=False):
        return b"1234567890-0"

    async def xreadgroup(self, group, consumer, streams, count=10, block=5000):
        return []

    async def xack(self, stream, group, *msg_ids):
        pass

    async def xgroup_create(self, stream, group, id="0", mkstream=False):
        pass

    async def xinfo_stream(self, stream):
        return {b"length": 0}

    async def xinfo_groups(self, stream):
        return []

    async def ping(self):
        return True

    async def aclose(self):
        pass


# ─── 1. Event Schemas ──────────────────────────────────────────────────────


class TestEmmaEvent:
    def test_create_with_defaults(self):
        event = _make_event()
        assert event.event_type == "document.indexed"
        assert event.tenant_id == "tenant-001"
        assert event.event_id  # auto-generated UUID
        assert event.timestamp  # auto-generated ISO timestamp

    def test_serialization_roundtrip(self):
        """to_stream_dict → from_stream_dict should preserve all fields."""
        original = _make_event(
            payload={"doc_id": "abc", "tags": ["labor", "hr"]},
            source_service="weaviate-service",
            correlation_id="corr-001",
        )
        stream_dict = original.to_stream_dict()

        # All values must be strings (Redis XADD requirement)
        for v in stream_dict.values():
            assert isinstance(v, str)

        # Simulate bytes from Redis
        bytes_dict = {k.encode(): v.encode() for k, v in stream_dict.items()}
        restored = EmmaEvent.from_stream_dict(bytes_dict)

        assert restored.event_id == original.event_id
        assert restored.event_type == original.event_type
        assert restored.tenant_id == original.tenant_id
        assert restored.payload == original.payload
        assert restored.source_service == original.source_service
        assert restored.correlation_id == original.correlation_id

    def test_from_stream_dict_with_empty_optionals(self):
        data = {
            b"event_id": b"e1",
            b"event_type": b"document.indexed",
            b"tenant_id": b"t1",
            b"payload": b"{}",
            b"timestamp": b"2026-01-01T00:00:00",
            b"source_service": b"",
            b"correlation_id": b"",
        }
        event = EmmaEvent.from_stream_dict(data)
        assert event.source_service is None
        assert event.correlation_id is None

    def test_event_type_enum_values(self):
        assert EventType.DOCUMENT_INDEXED == "document.indexed"
        assert EventType.CONNECTOR_SYNCED == "connector.synced"
        assert EventType.TRIGGER_EXECUTED == "trigger.executed"


class TestEventFilter:
    def test_matches_event_type(self):
        f = EventFilter(event_type="document.indexed")
        event = _make_event()
        assert f.matches(event) is True

    def test_rejects_different_event_type(self):
        f = EventFilter(event_type="connector.synced")
        event = _make_event(event_type="document.indexed")
        assert f.matches(event) is False

    def test_matches_with_tenant(self):
        f = EventFilter(event_type="document.indexed", tenant_id="tenant-001")
        assert f.matches(_make_event(tenant_id="tenant-001")) is True
        assert f.matches(_make_event(tenant_id="tenant-002")) is False

    def test_matches_with_payload_filters(self):
        f = EventFilter(
            event_type="document.indexed",
            payload_filters={"collection": "contracts"},
        )
        assert f.matches(_make_event(payload={"collection": "contracts"})) is True
        assert f.matches(_make_event(payload={"collection": "reports"})) is False

    def test_rejects_missing_payload_key(self):
        f = EventFilter(
            event_type="document.indexed",
            payload_filters={"collection": "contracts"},
        )
        assert f.matches(_make_event(payload={})) is False


# ─── 2. Event Pattern Parsing ──────────────────────────────────────────────


class TestParseEventPattern:
    def test_simple_event_type(self):
        event_type, filters = parse_event_pattern("document.indexed")
        assert event_type == "document.indexed"
        assert filters == {}

    def test_single_filter(self):
        event_type, filters = parse_event_pattern("document.indexed:collection=contracts")
        assert event_type == "document.indexed"
        assert filters == {"collection": "contracts"}

    def test_multiple_filters(self):
        event_type, filters = parse_event_pattern(
            "document.indexed:collection=contracts,tags=labor"
        )
        assert event_type == "document.indexed"
        assert filters == {"collection": "contracts", "tags": "labor"}

    def test_whitespace_trimming(self):
        event_type, filters = parse_event_pattern(
            " document.indexed : collection = contracts , tags = labor "
        )
        assert event_type == "document.indexed"
        assert filters == {"collection": "contracts", "tags": "labor"}


class TestEventMatchesPattern:
    def test_matches_type_only(self):
        event = _make_event()
        assert event_matches_pattern(event, "document.indexed") is True
        assert event_matches_pattern(event, "connector.synced") is False

    def test_matches_with_filter(self):
        event = _make_event(payload={"collection": "contracts"})
        assert event_matches_pattern(event, "document.indexed:collection=contracts") is True
        assert event_matches_pattern(event, "document.indexed:collection=reports") is False

    def test_list_membership(self):
        """tags=labor should match when tags is ['labor', 'hr']."""
        event = _make_event(payload={"tags": ["labor", "hr"]})
        assert event_matches_pattern(event, "document.indexed:tags=labor") is True
        assert event_matches_pattern(event, "document.indexed:tags=finance") is False

    def test_missing_key_in_payload(self):
        event = _make_event(payload={})
        assert event_matches_pattern(event, "document.indexed:collection=contracts") is False

    def test_string_coercion(self):
        """Numeric payload values are coerced to strings for comparison."""
        event = _make_event(payload={"count": 42})
        assert event_matches_pattern(event, "document.indexed:count=42") is True


# ─── 3. EventBus (mocked Redis) ────────────────────────────────────────────


class TestEventBus:
    @pytest.mark.asyncio
    async def test_publish(self):
        from app.services.event_bus import EventBus

        bus = EventBus()
        bus._redis = FakeRedis()
        event = _make_event()
        msg_id = await bus.publish(event)
        assert msg_id == "1234567890-0"

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        from app.services.event_bus import EventBus

        bus = EventBus()
        bus._redis = FakeRedis()
        result = await bus.health_check()
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_close(self):
        from app.services.event_bus import EventBus

        bus = EventBus()
        bus._redis = FakeRedis()
        await bus.close()
        assert bus._redis is None


# ─── 4. TriggerEngine (mocked Redis) ───────────────────────────────────────


class TestTriggerEngine:
    @pytest.fixture
    def engine(self):
        from app.services.trigger_engine import TriggerEngine
        e = TriggerEngine()
        e._redis = FakeRedis()
        return e

    @pytest.mark.asyncio
    async def test_create_and_get_trigger(self, engine):
        trigger = await engine.create_trigger("t1", {
            "name": "Test Trigger",
            "trigger_type": "event",
            "event_pattern": "document.indexed",
            "action_type": "analyze",
            "action_config": {"agent": "general"},
            "is_active": True,
            "priority": 3,
        })
        assert trigger["tenant_id"] == "t1"
        assert trigger["name"] == "Test Trigger"

        fetched = await engine.get_trigger("t1", trigger["id"])
        assert fetched is not None
        assert fetched["name"] == "Test Trigger"

    @pytest.mark.asyncio
    async def test_list_triggers_sorted_by_priority(self, engine):
        await engine.create_trigger("t1", {"name": "Low", "priority": 10, "trigger_type": "event", "event_pattern": "x", "action_type": "analyze", "action_config": {}, "is_active": True})
        await engine.create_trigger("t1", {"name": "High", "priority": 1, "trigger_type": "event", "event_pattern": "x", "action_type": "analyze", "action_config": {}, "is_active": True})

        triggers = await engine.list_triggers("t1")
        assert len(triggers) == 2
        assert triggers[0]["name"] == "High"
        assert triggers[1]["name"] == "Low"

    @pytest.mark.asyncio
    async def test_update_trigger(self, engine):
        trigger = await engine.create_trigger("t1", {"name": "Old", "trigger_type": "event", "event_pattern": "x", "action_type": "analyze", "action_config": {}, "is_active": True, "priority": 5})
        updated = await engine.update_trigger("t1", trigger["id"], {"name": "New"})
        assert updated["name"] == "New"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self, engine):
        result = await engine.update_trigger("t1", "nonexistent", {"name": "X"})
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_trigger(self, engine):
        trigger = await engine.create_trigger("t1", {"name": "Del", "trigger_type": "event", "event_pattern": "x", "action_type": "analyze", "action_config": {}, "is_active": True, "priority": 5})
        assert await engine.delete_trigger("t1", trigger["id"]) is True
        assert await engine.get_trigger("t1", trigger["id"]) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, engine):
        assert await engine.delete_trigger("t1", "nonexistent") is False

    @pytest.mark.asyncio
    async def test_evaluate_event_matches_and_dispatches(self, engine):
        """Event matching a trigger should call _execute_trigger."""
        await engine.create_trigger("tenant-001", {
            "name": "Contract Trigger",
            "trigger_type": "event",
            "event_pattern": "document.indexed:collection=contracts",
            "action_type": "notify",
            "action_config": {},
            "notification_channels": ["in_app"],
            "is_active": True,
            "priority": 5,
        })

        event = _make_event(payload={"doc_id": "d1", "collection": "contracts"})

        with patch.object(engine, "_execute_trigger", new_callable=AsyncMock) as mock_exec:
            await engine.evaluate_event(event)
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_event_skips_inactive(self, engine):
        await engine.create_trigger("tenant-001", {
            "name": "Inactive",
            "trigger_type": "event",
            "event_pattern": "document.indexed",
            "action_type": "analyze",
            "action_config": {},
            "is_active": False,
            "priority": 5,
        })
        event = _make_event()
        with patch.object(engine, "_execute_trigger", new_callable=AsyncMock) as mock_exec:
            await engine.evaluate_event(event)
            mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_evaluate_event_skips_non_event_type(self, engine):
        await engine.create_trigger("tenant-001", {
            "name": "Schedule",
            "trigger_type": "schedule",
            "event_pattern": "document.indexed",
            "action_type": "analyze",
            "action_config": {},
            "is_active": True,
            "priority": 5,
        })
        event = _make_event()
        with patch.object(engine, "_execute_trigger", new_callable=AsyncMock) as mock_exec:
            await engine.evaluate_event(event)
            mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_evaluate_event_no_match(self, engine):
        await engine.create_trigger("tenant-001", {
            "name": "Reports Only",
            "trigger_type": "event",
            "event_pattern": "document.indexed:collection=reports",
            "action_type": "analyze",
            "action_config": {},
            "is_active": True,
            "priority": 5,
        })
        event = _make_event(payload={"collection": "contracts"})
        with patch.object(engine, "_execute_trigger", new_callable=AsyncMock) as mock_exec:
            await engine.evaluate_event(event)
            mock_exec.assert_not_called()


# ─── 5. NotificationService (mocked Redis) ─────────────────────────────────


class TestNotificationService:
    @pytest.fixture
    def svc(self):
        from app.services.notification_service import NotificationService
        s = NotificationService()
        s._redis = FakeRedis()
        return s

    @pytest.mark.asyncio
    async def test_create_notification(self, svc):
        notif = await svc.create_notification(
            tenant_id="t1", user_id="u1",
            title="Test", body="Hello",
        )
        assert notif["title"] == "Test"
        assert notif["is_read"] is False
        assert notif["id"]

    @pytest.mark.asyncio
    async def test_get_notifications(self, svc):
        await svc.create_notification("t1", "u1", "A", "Body A")
        await svc.create_notification("t1", "u1", "B", "Body B")

        notifications = await svc.get_notifications("t1", "u1")
        assert len(notifications) == 2
        # Most recent first (lpush)
        assert notifications[0]["title"] == "B"

    @pytest.mark.asyncio
    async def test_get_notifications_unread_only(self, svc):
        await svc.create_notification("t1", "u1", "A", "Body A")
        n2 = await svc.create_notification("t1", "u1", "B", "Body B")

        await svc.mark_read("t1", "u1", n2["id"])
        unread = await svc.get_notifications("t1", "u1", unread_only=True)
        assert len(unread) == 1
        assert unread[0]["title"] == "A"

    @pytest.mark.asyncio
    async def test_mark_read(self, svc):
        notif = await svc.create_notification("t1", "u1", "Test", "Body")
        result = await svc.mark_read("t1", "u1", notif["id"])
        assert result is True

        notifications = await svc.get_notifications("t1", "u1")
        assert notifications[0]["is_read"] is True

    @pytest.mark.asyncio
    async def test_mark_read_nonexistent(self, svc):
        result = await svc.mark_read("t1", "u1", "nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_mark_all_read(self, svc):
        await svc.create_notification("t1", "u1", "A", "A")
        await svc.create_notification("t1", "u1", "B", "B")

        count = await svc.mark_all_read("t1", "u1")
        assert count == 2

        unread = await svc.get_notifications("t1", "u1", unread_only=True)
        assert len(unread) == 0

    @pytest.mark.asyncio
    async def test_unread_count(self, svc):
        await svc.create_notification("t1", "u1", "A", "A")
        await svc.create_notification("t1", "u1", "B", "B")

        assert await svc.get_unread_count("t1", "u1") == 2

        n = await svc.get_notifications("t1", "u1")
        await svc.mark_read("t1", "u1", n[0]["id"])
        assert await svc.get_unread_count("t1", "u1") == 1

    @pytest.mark.asyncio
    async def test_websocket_publish_on_create(self, svc):
        """Creating a notification should publish to the WebSocket channel."""
        await svc.create_notification("t1", "u1", "WS Test", "Body")
        redis = svc._redis
        assert len(redis._published) == 1
        channel, msg = redis._published[0]
        assert channel == "emma:notifications:realtime"
        data = json.loads(msg)
        assert data["title"] == "WS Test"

    @pytest.mark.asyncio
    async def test_send_trigger_notification(self, svc):
        event = _make_event()
        await svc.send_trigger_notification(
            tenant_id="t1",
            trigger_name="Contract Trigger",
            event=event,
            channels=["in_app"],
        )
        notifications = await svc.get_notifications("t1", "system")
        assert len(notifications) == 1
        assert "Contract Trigger" in notifications[0]["title"]


# ─── 6. PairingService (mocked Redis) ──────────────────────────────────────


class TestPairingService:
    @pytest.fixture
    def svc(self):
        from app.services.pairing_service import PairingService
        s = PairingService()
        s._redis = FakeRedis()
        return s

    @pytest.mark.asyncio
    async def test_generate_pairing_code(self, svc):
        code = await svc.generate_pairing_code("t1", "telegram", "ext-123")
        assert len(code) == 6
        assert code.isdigit()

    @pytest.mark.asyncio
    async def test_confirm_pairing(self, svc):
        code = await svc.generate_pairing_code("t1", "telegram", "ext-123")
        result = await svc.confirm_pairing(code, "user-abc")

        assert result is not None
        assert result["user_id"] == "user-abc"
        assert result["external_id"] == "ext-123"
        assert result["channel_type"] == "telegram"

    @pytest.mark.asyncio
    async def test_confirm_invalid_code(self, svc):
        result = await svc.confirm_pairing("999999", "user-abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_pairing_after_confirm(self, svc):
        code = await svc.generate_pairing_code("t1", "telegram", "ext-123")
        await svc.confirm_pairing(code, "user-abc")

        pairing = await svc.get_pairing("t1", "telegram", "ext-123")
        assert pairing is not None
        assert pairing["user_id"] == "user-abc"

    @pytest.mark.asyncio
    async def test_get_pairing_before_confirm(self, svc):
        assert await svc.get_pairing("t1", "telegram", "ext-123") is None

    @pytest.mark.asyncio
    async def test_revoke_pairing(self, svc):
        code = await svc.generate_pairing_code("t1", "telegram", "ext-123")
        await svc.confirm_pairing(code, "user-abc")

        assert await svc.revoke_pairing("t1", "telegram", "ext-123") is True
        assert await svc.get_pairing("t1", "telegram", "ext-123") is None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent(self, svc):
        assert await svc.revoke_pairing("t1", "telegram", "no-one") is False

    @pytest.mark.asyncio
    async def test_code_consumed_after_confirm(self, svc):
        """After confirming, the same code cannot be reused."""
        code = await svc.generate_pairing_code("t1", "telegram", "ext-123")
        await svc.confirm_pairing(code, "user-abc")

        result = await svc.confirm_pairing(code, "user-xyz")
        assert result is None


# ─── 7. ChannelRouter (mocked channels) ────────────────────────────────────


class TestChannelRouter:
    @pytest.fixture
    def router(self):
        from app.services.channel_router import ChannelRouter
        return ChannelRouter()

    def test_get_channel_unknown_type(self, router):
        with pytest.raises(ValueError, match="Unknown channel type"):
            router.get_channel_instance("ch-1", "carrier_pigeon", {})

    def test_get_channel_caches(self, router):
        """Same channel_id should return the same instance."""
        ch1 = router.get_channel_instance("ch-1", "telegram", {"bot_token": "x"})
        ch2 = router.get_channel_instance("ch-1", "telegram", {"bot_token": "x"})
        assert ch1 is ch2

    @pytest.mark.asyncio
    async def test_route_inbound_unpaired_user(self, router):
        """Unpaired user should get a pairing code response."""
        mock_channel = AsyncMock()
        mock_channel.parse_inbound.return_value = {
            "sender_id": "ext-user",
            "content": "Hola Emma",
            "chat_id": "chat-1",
        }
        mock_channel.send_message.return_value = {"success": True}

        router._active_channels["ch-1"] = mock_channel

        with patch("app.services.channel_router.pairing_service") as mock_ps:
            mock_ps.get_pairing = AsyncMock(return_value=None)
            mock_ps.generate_pairing_code = AsyncMock(return_value="123456")

            result = await router.route_inbound(
                channel_id="ch-1",
                channel_type="telegram",
                config={},
                credentials=None,
                webhook_data={"message": "Hola"},
                tenant_id="t1",
            )

        assert result["status"] == "pairing_required"
        assert result["code"] == "123456"
        mock_channel.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_inbound_paired_user(self, router):
        """Paired user should get Emma's response."""
        mock_channel = AsyncMock()
        mock_channel.parse_inbound.return_value = {
            "sender_id": "ext-user",
            "content": "¿Cuáles son mis contratos?",
            "chat_id": "chat-1",
        }
        mock_channel.send_message.return_value = {"success": True}

        router._active_channels["ch-1"] = mock_channel

        with patch("app.services.channel_router.pairing_service") as mock_ps, \
             patch("app.services.emma_background_service.emma_background_service") as mock_emma:
            mock_ps.get_pairing = AsyncMock(return_value={"user_id": "user-abc", "tenant_id": "t1"})
            mock_emma.proactive_analysis = AsyncMock(return_value={"answer": "Tienes 3 contratos activos."})

            result = await router.route_inbound(
                channel_id="ch-1",
                channel_type="telegram",
                config={},
                credentials=None,
                webhook_data={},
                tenant_id="t1",
            )

        assert result["status"] == "responded"
        assert result["user_id"] == "user-abc"
        mock_channel.send_message.assert_called_once()
        call_kwargs = mock_channel.send_message.call_args
        assert "3 contratos" in call_kwargs.kwargs.get("content", call_kwargs[1].get("content", ""))

    @pytest.mark.asyncio
    async def test_route_inbound_empty_message(self, router):
        mock_channel = AsyncMock()
        mock_channel.parse_inbound.return_value = {
            "sender_id": "ext-user",
            "content": "",
            "chat_id": "chat-1",
        }
        router._active_channels["ch-1"] = mock_channel

        result = await router.route_inbound(
            channel_id="ch-1", channel_type="telegram",
            config={}, credentials=None,
            webhook_data={}, tenant_id="t1",
        )
        assert result["status"] == "ignored"


# ─── 8. End-to-End Scenario ────────────────────────────────────────────────


class TestEndToEndReactive:
    @pytest.mark.asyncio
    async def test_event_triggers_analysis_and_notification(self):
        """
        Scenario: document.indexed → trigger matches → analyze dispatched → notification sent.
        """
        from app.services.trigger_engine import TriggerEngine
        from app.services.notification_service import NotificationService

        engine = TriggerEngine()
        engine._redis = FakeRedis()
        notif_svc = NotificationService()
        notif_svc._redis = FakeRedis()

        # Create a trigger
        await engine.create_trigger("tenant-001", {
            "name": "Analyze Contracts",
            "trigger_type": "event",
            "event_pattern": "document.indexed:collection=contracts",
            "action_type": "notify",
            "action_config": {},
            "notification_channels": ["in_app"],
            "is_active": True,
            "priority": 1,
        })

        event = _make_event(payload={"doc_id": "doc-999", "collection": "contracts"})

        # Patch notification_service import inside trigger_engine
        with patch(
            "app.services.trigger_engine.TriggerEngine._dispatch_notify",
            new_callable=AsyncMock,
            return_value={"notified": True},
        ), patch(
            "app.services.trigger_engine.TriggerEngine._send_notifications",
            new_callable=AsyncMock,
        ):
            await engine.evaluate_event(event)

        # Verify execution was recorded
        executions = await engine.list_executions("tenant-001")
        assert len(executions) == 1
        assert executions[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_multiple_triggers_match_same_event(self):
        """Multiple triggers can match the same event."""
        from app.services.trigger_engine import TriggerEngine

        engine = TriggerEngine()
        engine._redis = FakeRedis()

        for i in range(3):
            await engine.create_trigger("tenant-001", {
                "name": f"Trigger {i}",
                "trigger_type": "event",
                "event_pattern": "document.indexed",
                "action_type": "notify",
                "action_config": {},
                "is_active": True,
                "priority": 5,
            })

        event = _make_event()
        call_count = 0

        async def count_exec(trigger, event):
            nonlocal call_count
            call_count += 1

        with patch.object(engine, "_execute_trigger", side_effect=count_exec):
            await engine.evaluate_event(event)

        assert call_count == 3

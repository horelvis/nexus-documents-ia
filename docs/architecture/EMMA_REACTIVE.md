# Emma Reactive — Event-Driven Proactive AI System

Emma Reactive transforms Emma from a **request-response chatbot** into a **proactive, event-driven, multi-channel AI assistant**. Inspired by event-driven architectures like OpenClaw, it enables Emma to:

- **React** to system events (new documents, connector syncs, graph updates)
- **Execute** proactive analyses via configurable triggers
- **Notify** users via in-app WebSocket, email, and webhooks
- **Communicate** through external channels (Telegram, WhatsApp, Slack, Email)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│              EVENT BUS (Redis Streams)                     │
│  document.indexed | connector.synced | knowledge.updated  │
│  session.idle | analysis.completed | schedule.triggered   │
└────────┬──────────────┬──────────────┬───────────────────┘
         │              │              │
   ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼──────┐
   │ Event     │ │ Celery    │ │ Channel    │
   │ Listener  │ │ Beat      │ │ Router     │
   └─────┬─────┘ └─────┬─────┘ └─────┬──────┘
         │              │              │
   ┌─────▼──────────────▼──────────────▼──────┐
   │           Trigger Engine                  │
   │  (evaluate rules → dispatch actions)      │
   └─────┬────────────────────────────────────┘
         │
   ┌─────▼──────────────────────────────────┐
   │  Emma Background Service               │
   │  (LangGraph proactive + Agent Registry)│
   └─────┬──────────────────────────────────┘
         │
   ┌─────▼───┬────────┬────────┬──────────┐
   │WhatsApp │Telegram│ Slack  │ WebSocket│
   └─────────┴────────┴────────┴──────────┘
```

---

## Phase 1: Event Bus (Redis Streams)

### Purpose
Inter-service event communication. When a document is indexed, a connector syncs, or the knowledge graph updates, an event is published to the Redis Streams bus.

### Event Schema (`EmmaEvent`)

```python
class EmmaEvent(BaseModel):
    event_id: str          # UUID
    event_type: str        # "document.indexed", "connector.synced", etc.
    tenant_id: str         # Tenant isolation
    payload: Dict[str, Any]  # Flexible event data
    timestamp: str         # ISO 8601
    source_service: str    # "weaviate-service", "background-worker", etc.
    correlation_id: str    # For distributed tracing
```

### Events

| Event | Emitter | Payload |
|-------|---------|---------|
| `document.indexed` | weaviate-service | doc_id, collection, title, chunks_count, tags |
| `document.updated` | weaviate-service | doc_id, changes |
| `connector.synced` | background-worker | connector_id, connector_type, docs_new, status |
| `knowledge.graph_updated` | knowledge-tree-service | entity_id, relationships |
| `analysis.completed` | background-worker | document_id, success, session_id |

### Key Files

| File | Service | Purpose |
|------|---------|---------|
| `emma-agent-service/app/schemas/events.py` | Emma | Event model + serialization |
| `emma-agent-service/app/services/event_bus.py` | Emma | Redis Streams publish/subscribe/ack |
| `emma-agent-service/app/workers/event_listener.py` | Emma | Standalone async consumer |
| `weaviate-service/app/services/event_publisher.py` | Weaviate | Lightweight async publisher |
| `background-worker/worker_app/services/event_publisher.py` | Worker | Sync publisher for Celery |

### Redis Streams Details

- **Stream key**: `emma:events`
- **Max length**: 10,000 entries (auto-trimmed)
- **Consumer group**: `emma_reactive`
- **Delivery**: At-least-once via XREADGROUP + XACK
- **No DB changes** — Redis Streams is ephemeral

### Testing

```bash
# Publish event manually
redis-cli XADD emma:events '*' \
  event_type document.indexed \
  tenant_id 00000000-0000-0000-0000-000000000001 \
  payload '{"doc_id":"123","collection":"contracts"}'

# Check stream
redis-cli XLEN emma:events
redis-cli XINFO GROUPS emma:events
```

---

## Phase 2: Background Tasks for Emma

### Purpose
Connect Emma with Celery for proactive LangGraph execution without an HTTP request.

### Celery Tasks

| Task | Queue | Schedule | Purpose |
|------|-------|----------|---------|
| `emma.analyze_new_document` | `emma_reactive` | Event-driven | Analyze newly indexed documents |
| `emma.daily_summary` | `emma_reactive` | 8 AM daily (Beat) | Generate daily activity summary |
| `emma.proactive_analysis` | `emma_reactive` | Trigger-driven | Custom proactive analysis |

### Emma Background Service

Orchestrates LangGraph execution from background context:

```python
from app.services.emma_background_service import emma_background_service

# Analyze a document
result = await emma_background_service.analyze_document(
    document_id="doc-123",
    tenant_id="tenant-abc",
    prompt_template="Analiza riesgos de compliance en: {document_title}",
    agent="labor_agent",
)

# Generate daily summary
result = await emma_background_service.generate_daily_summary(tenant_id="tenant-abc")
```

### Background API (Internal)

Secured by `MICROSERVICES_API_KEY`, called by Celery tasks:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/emma/background/analyze_document` | POST | Analyze a document |
| `/emma/background/daily_summary` | POST | Generate daily summary |
| `/emma/background/proactive_analysis` | POST | Custom analysis |

### Key Files

| File | Purpose |
|------|---------|
| `emma-agent-service/app/services/emma_background_service.py` | LangGraph without HTTP |
| `emma-agent-service/app/api/background.py` | Internal REST endpoints |
| `background-worker/worker_app/tasks/emma_tasks.py` | Celery task definitions |

### Testing

```bash
# Test celery task
celery -A worker_app.celery_app call emma.analyze_new_document \
  --args='["doc_123","tenant_123"]' --queue=emma_reactive

# Test daily summary
celery -A worker_app.celery_app call emma.daily_summary \
  --queue=emma_reactive
```

---

## Phase 3: Trigger System

### Purpose
Configurable rules per tenant that connect events with Emma actions.

### Trigger Model

```python
class TriggerCreate(BaseModel):
    name: str                    # "Analizar Contratos Laborales"
    trigger_type: TriggerType    # event | schedule | condition
    event_pattern: str           # "document.indexed:collection=contracts,tags=labor"
    action_type: ActionType      # analyze | notify | workflow
    action_config: Dict          # {agent, prompt_template, ...}
    notification_channels: List  # ["email", "in_app"]
    priority: int                # 1-10 (lower = higher priority)
```

### Event Pattern Syntax

```
event_type:key1=value1,key2=value2

# Examples:
document.indexed                              # All document.indexed events
document.indexed:collection=contracts         # Only contracts collection
document.indexed:collection=contracts,tags=labor  # Contracts with labor tag
connector.synced:status=healthy               # Only successful syncs
```

### Trigger Engine Flow

```
Event arrives → List active triggers for tenant →
  For each trigger:
    Parse event_pattern → Match against event →
      If match: Execute action (analyze/notify/workflow) →
        Record execution → Send notifications
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/triggers` | POST | Create trigger |
| `/triggers` | GET | List triggers |
| `/triggers/{id}` | GET | Get trigger details |
| `/triggers/{id}` | PATCH | Update trigger |
| `/triggers/{id}` | DELETE | Delete trigger |
| `/triggers/{id}/executions` | GET | Execution history |

### Database Tables

```sql
emma_triggers          — Configurable rules (event_pattern, action_config, etc.)
emma_trigger_executions — Audit trail (status, result, tokens_used)
```

### Key Files

| File | Purpose |
|------|---------|
| `emma-agent-service/app/schemas/triggers.py` | Pydantic schemas |
| `emma-agent-service/app/services/trigger_engine.py` | Rule evaluation + dispatch |
| `emma-agent-service/app/api/triggers.py` | CRUD endpoints |
| `backend/app/db/emma_reactive_models.py` | SQLAlchemy models |

### Testing

```bash
# Create trigger
curl -X POST http://localhost:8009/triggers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Analizar Contratos",
    "trigger_type": "event",
    "event_pattern": "document.indexed:collection=contracts",
    "action_type": "analyze",
    "action_config": {"agent": "contract_agent", "prompt_template": "Analiza riesgos en: {document_title}"},
    "notification_channels": ["in_app"]
  }'

# Index a document → verify automatic trigger execution
```

---

## Phase 4: Notification System

### Purpose
Multi-channel notification delivery: in-app (WebSocket), email, webhooks.

### Notification Flow

```
Trigger executed → NotificationService.create_notification() →
  Store in Redis (per-user inbox) →
  Publish to Redis Pub/Sub channel →
  WebSocketManager picks up → pushes to connected clients
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/notifications` | GET | List notifications (with `?unread_only=true`) |
| `/notifications/unread` | GET | Get unread count |
| `/notifications/{id}/read` | PATCH | Mark as read |
| `/notifications/read-all` | POST | Mark all as read |

### WebSocket

```
ws://localhost:8000/emma/ws/notifications

# Receives JSON messages:
{
  "id": "uuid",
  "title": "🔔 Trigger activado: Analizar Contratos",
  "body": "Evento document.indexed coincidió con el trigger...",
  "notification_type": "trigger_result",
  "priority": "normal",
  "created_at": "2026-02-02T10:00:00Z"
}
```

### Frontend Components

| File | Purpose |
|------|---------|
| `frontend/.../hooks/useEmmaNotifications.ts` | WebSocket hook + state |
| `frontend/.../components/notifications/NotificationBell.tsx` | Bell icon + dropdown |

### Database Tables

```sql
emma_notifications             — Notification storage (title, body, is_read, priority)
emma_notification_preferences  — Per-user settings (email_enabled, webhook_url)
```

### Key Files

| File | Purpose |
|------|---------|
| `emma-agent-service/app/services/notification_service.py` | Multi-channel dispatcher |
| `backend/app/services/websocket_manager.py` | WebSocket connection manager |
| `emma-agent-service/app/api/notifications.py` | REST endpoints |

---

## Phase 5: Multi-Channel Messaging

### Purpose
Emma accessible via WhatsApp, Telegram, Slack, and Email — external users interact with Emma directly.

### Channel Architecture

```python
class BaseChannel(ABC):
    """Abstract base for all messaging channels."""
    async def send_message(to, content, metadata) -> Dict
    async def parse_inbound(webhook_data) -> Dict
    async def health_check() -> Dict
```

| Channel | Implementation | Provider | Status |
|---------|---------------|----------|--------|
| **Telegram** | `TelegramChannel` | Telegram Bot API | ✅ Ready |
| **WhatsApp** | `WhatsAppChannel` | Twilio API | ✅ Ready |
| **Slack** | `SlackChannel` | Slack Web API | ✅ **Active** |
| **Email** | `EmailChannel` | SMTP via aiosmtplib | ✅ Ready |

### Slack Integration (Recommended for Notifications)

Slack is the recommended channel for automatic notifications due to its team-friendly design.

**Setup:**
1. Create a Slack App at https://api.slack.com/apps
2. Add Bot Token Scopes: `chat:write`, `channels:read`
3. Install to workspace → Copy Bot Token (`xoxb-...`)
4. Create channel `#emma-alerts` (or custom name)
5. Invite bot to channel: `/invite @YourBotName`

**Register as notification channel:**
```bash
curl -X POST http://localhost:8009/channels \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "tenant_id": "YOUR_TENANT_ID",
    "channel_type": "slack",
    "channel_name": "emma-alerts",
    "config": {
      "bot_token": "xoxb-...",
      "default_channel": "#emma-alerts"
    },
    "is_notification_channel": true
  }'
```

**Heartbeat delivers to Slack** automatically when configured as notification channel.

### Inbound Message Flow

```
External message → POST /channels/webhooks/{channel_type}
  → PairingService.get_pairing()  (verify user)
      If unknown: send pairing code (6-digit)
      If known: continue
  → ChannelRouter.route_inbound()
  → Emma Background Service (LangGraph execution)
  → Channel.send_message() (response back)
```

### User Pairing

External users must link their account before interacting with Emma:

1. User sends first message → receives 6-digit pairing code
2. User enters code in NouxCubeIA web UI (`/emma/channels` → Pairing)
3. `POST /channels/pairing/confirm` links external ID → KeyCloak user
4. Future messages are automatically routed to the correct user context

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/channels` | POST | Create channel |
| `/channels` | GET | List channels |
| `/channels/{id}` | GET/PATCH/DELETE | Channel CRUD |
| `/channels/{id}/health` | GET | Check connectivity |
| `/channels/webhooks/{type}` | POST | Inbound webhook |
| `/channels/pairing/confirm` | POST | Confirm pairing code |

### Security

- **Credential encryption**: Fernet (`CREDENTIALS_ENCRYPTION_KEY` env var)
- **Webhook verification**: HMAC for Telegram/Slack webhooks
- **Rate limiting**: Per-tenant limits on reactive tasks
- **ACL enforcement**: All proactive executions respect tenant isolation

### Database Tables

```sql
emma_channels         — Channel config (type, credentials_encrypted, routing_rules)
emma_channel_messages — Message history (direction, content, emma_thread_id)
```

### Frontend

| File | Purpose |
|------|---------|
| `frontend/.../app/emma/channels/page.tsx` | Channel management UI |

### Key Files

| File | Purpose |
|------|---------|
| `emma-agent-service/app/channels/base.py` | BaseChannel ABC |
| `emma-agent-service/app/channels/telegram_channel.py` | Telegram |
| `emma-agent-service/app/channels/whatsapp_channel.py` | WhatsApp (Twilio) |
| `emma-agent-service/app/channels/slack_channel.py` | Slack |
| `emma-agent-service/app/channels/email_channel.py` | Email (SMTP) |
| `emma-agent-service/app/services/channel_router.py` | Inbound→Emma→outbound |
| `emma-agent-service/app/services/pairing_service.py` | User pairing |
| `emma-agent-service/app/api/channels_emma.py` | REST + webhooks |

---

## Phase 6: Heartbeat & Proactive Intelligence

### Purpose
Continuous background evaluation of tenant context to generate proactive insights without explicit user requests. Inspired by OpenClaw's Heartbeat System.

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    HEARTBEAT SERVICE                      │
│  (Celery Beat: every 30 min)                              │
└─────────────┬───────────────────────────────────────────┘
              │
     ┌────────▼────────┐
     │ Context Gatherer │ ← Collects from PostgreSQL + Weaviate + Redis
     │  - indexed_documents (24h)         │
     │  - expiring_contracts              │
     │  - user_activity                   │
     │  - indexing_failures               │
     └────────┬─────────┘
              │
     ┌────────▼────────┐
     │ Insight Evaluator│ ← vLLM/Qwen evaluates context
     │  - JSON structured output          │
     │  - Insight type classification     │
     │  - Priority 0.0-1.0                │
     └────────┬─────────┘
              │
     ┌────────▼────────┐
     │ Priority Scorer  │ ← Multi-factor scoring
     │  - Type base (0.40-0.85)           │
     │  - Urgency multiplier              │
     │  - Confidence adjustment           │
     └────────┬─────────┘
              │
     ┌────────▼────────┐
     │ Delivery Manager │ ← Rate limiting + quiet hours
     │  - max 5/day, 2/hour               │
     │  - quiet: 22:00-08:00              │
     │  - channels: in_app > email        │
     └──────────────────┘
```

### Insight Types

| Type | Base Priority | Example | When Generated |
|------|--------------|---------|----------------|
| `contract_expiration` | 0.85 | "Contract with Acme expires in 15 days" | Contract expires in <30 days |
| `compliance_alert` | 0.80 | "Regulatory gap detected in clause 4.2" | Compliance risk identified |
| `risk_alert` | 0.75 | "Abusive clause detected in contract" | Risk identified in analysis |
| `anomaly_detected` | 0.60 | "3 duplicate invoices found" | Duplicates, indexing failures |
| `task_reminder` | 0.55 | "5 analyses pending for 10 days" | Pending items >7 days |
| `activity_summary` | 0.40 | "Summary: 12 new docs, 3 queries" | Inactivity >7 days |

### Configuration (Per Tenant)

```python
HeartbeatConfig:
    enabled: bool = True
    run_interval_hours: int = 4           # Every 4 hours
    priority_threshold: float = 0.6       # Only deliver if priority >= 0.6
    max_insights_per_day: int = 5         # Maximum 5 per day
    max_insights_per_hour: int = 2        # Maximum 2 per hour
    min_interval_minutes: int = 30        # Minimum 30 min between notifications
    quiet_hours_start: str = "22:00"      # Do not disturb from 22:00
    quiet_hours_end: str = "08:00"        # Until 08:00
    channel_priority: List[str] = ["in_app", "email", "telegram", "slack"]
    batch_low_priority: bool = True       # Batch low priority in digest
    digest_hour: int = 9                  # Send digest at 9 AM
    contract_expiry_days_warning: int = 30
    enabled_insight_types: List[str] = [
        "contract_expiration", "compliance_alert", "risk_alert",
        "anomaly_detected", "task_reminder"
    ]
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/emma/heartbeat/status` | GET | Get heartbeat status for tenant |
| `/emma/heartbeat/run` | POST | Run heartbeat check manually |
| `/emma/heartbeat/config` | GET | Get tenant configuration |
| `/emma/heartbeat/config` | PATCH | Update tenant configuration |
| `/emma/heartbeat/insights` | GET | List generated insights |
| `/emma/heartbeat/insights/{id}` | GET | Get insight details |
| `/emma/heartbeat/insights/{id}/dismiss` | POST | Dismiss an insight |
| `/emma/heartbeat/insights/{id}/acted` | POST | Mark insight as acted upon |
| `/emma/heartbeat/digest` | GET | Get/generate daily digest |

### Celery Tasks & Schedules

| Task | Schedule | Purpose |
|------|----------|---------|
| `emma.heartbeat_check` | Every 30 min | Run heartbeat evaluation |
| `emma.heartbeat_digest` | 9 AM daily | Generate and send daily digest |
| `emma.heartbeat_all_tenants` | On-demand | Run heartbeat for all tenants |

### Database Tables

```sql
emma_heartbeat_configs      — Per-tenant configuration
  - tenant_id UUID UNIQUE
  - config JSONB            -- HeartbeatConfig JSON
  - last_run_at TIMESTAMP
  - next_run_at TIMESTAMP
  - insights_delivered_today INTEGER
  - last_insight_at TIMESTAMP

emma_proactive_insights     — Generated insights
  - tenant_id UUID
  - insight_type VARCHAR(50)
  - title VARCHAR(255)
  - summary TEXT
  - priority_score FLOAT    -- 0.0-1.0
  - urgency VARCHAR(20)     -- critical/high/medium/low
  - confidence FLOAT
  - related_documents JSONB -- [{doc_id, title}]
  - suggested_actions JSONB -- [{action, priority}]
  - status VARCHAR(20)      -- pending/delivered/dismissed/expired
  - delivered_at TIMESTAMP
  - expires_at TIMESTAMP
```

### Key Files

| File | Purpose |
|------|---------|
| `emma-agent-service/app/schemas/heartbeat.py` | Pydantic models |
| `emma-agent-service/app/services/heartbeat/heartbeat_service.py` | Main orchestrator |
| `emma-agent-service/app/services/heartbeat/context_gatherer.py` | Data collection |
| `emma-agent-service/app/services/heartbeat/insight_evaluator.py` | LLM evaluation |
| `emma-agent-service/app/services/heartbeat/priority_scorer.py` | Multi-factor scoring |
| `emma-agent-service/app/services/heartbeat/delivery_manager.py` | Rate limiting + delivery |
| `emma-agent-service/app/api/heartbeat.py` | REST endpoints |
| `background-worker/worker_app/tasks/emma_tasks.py` | Celery tasks |
| `emma-agent-service/config/prompts/emma_prompts.yaml` | Evaluation prompts |

### Testing

```bash
# Check heartbeat status
curl "http://localhost:8009/emma/heartbeat/status?tenant_id=00000000-0000-0000-0000-000000000001" \
  -H "X-API-Key: $API_KEY"

# Run heartbeat manually
curl -X POST "http://localhost:8009/emma/heartbeat/run?tenant_id=00000000-0000-0000-0000-000000000001" \
  -H "X-API-Key: $API_KEY"

# List generated insights
curl "http://localhost:8009/emma/heartbeat/insights?tenant_id=00000000-0000-0000-0000-000000000001" \
  -H "X-API-Key: $API_KEY"

# Update configuration
curl -X PATCH "http://localhost:8009/emma/heartbeat/config?tenant_id=00000000-0000-0000-0000-000000000001" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"priority_threshold": 0.5, "max_insights_per_day": 10}'

# Test via Celery
celery -A worker_app.celery_app call emma.heartbeat_check \
  --args='["00000000-0000-0000-0000-000000000001"]' --queue=emma_reactive
```

---

## Docker Compose

New service added to `docker-compose.onpremise.yml`:

```yaml
emma-reactive-worker:
  build: ../microservices/emma-agent-service
  command: ["python", "-m", "app.workers.event_listener"]
  depends_on: [redis, db, emma-agent-service]
  environment:
    - REDIS_HOST=redis
    - EVENT_CONSUMER_GROUP=emma_reactive
    - CREDENTIALS_ENCRYPTION_KEY=${CREDENTIALS_ENCRYPTION_KEY:-}
```

Extended `background-worker` with `emma_reactive` queue and beat schedules.

---

## Database Migration

Two migrations create all 8 Emma Reactive tables:

```bash
docker compose -f docker-compose.onpremise.yml exec api alembic upgrade head
```

**Migrations**:
- `a1b2c3d4e5f6_add_emma_reactive_tables.py` — Phases 3-5 (triggers, notifications, channels)
- `b2c3d4e5f6g7_add_emma_heartbeat_tables.py` — Phase 6 (heartbeat)

**Tables** (8 total):
- `emma_triggers`, `emma_trigger_executions` — Phase 3
- `emma_notifications`, `emma_notification_preferences` — Phase 4
- `emma_channels`, `emma_channel_messages` — Phase 5
- `emma_heartbeat_configs`, `emma_proactive_insights` — Phase 6

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `EVENT_BUS_ENABLED` | `true` | Enable/disable event bus |
| `EVENT_CONSUMER_GROUP` | `emma_reactive` | Redis consumer group name |
| `EVENT_CONSUMER_NAME` | `worker-{pid}` | Consumer identifier |
| `CREDENTIALS_ENCRYPTION_KEY` | (empty) | Fernet key for channel credentials |

---

## Verification / Testing

```bash
# Get API key
API_KEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)

# 1. Test event bus
redis-cli XADD emma:events '*' event_type document.indexed \
  tenant_id 00000000-0000-0000-0000-000000000001 \
  payload '{"doc_id":"123"}'

# 2. Test celery task
celery -A worker_app.celery_app call emma.analyze_new_document \
  --args='["doc_123","00000000-0000-0000-0000-000000000001"]' \
  --queue=emma_reactive

# 3. Test triggers API
curl -X POST http://localhost:8009/triggers \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"name":"test","trigger_type":"event","event_pattern":"document.indexed","action_type":"analyze","action_config":{"agent":"general"}}'

# 4. Test notifications
curl http://localhost:8009/notifications -H "X-API-Key: $API_KEY"

# 5. Test channels
curl -X POST http://localhost:8009/channels \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"channel_type":"telegram","channel_name":"Bot","config":{"bot_token":"test"}}'

# 6. Test heartbeat status
curl "http://localhost:8009/emma/heartbeat/status?tenant_id=00000000-0000-0000-0000-000000000001" \
  -H "X-API-Key: $API_KEY"

# 7. Test heartbeat run
curl -X POST "http://localhost:8009/emma/heartbeat/run?tenant_id=00000000-0000-0000-0000-000000000001" \
  -H "X-API-Key: $API_KEY"

# 8. Test heartbeat via Celery
celery -A worker_app.celery_app call emma.heartbeat_check \
  --args='["00000000-0000-0000-0000-000000000001"]' --queue=emma_reactive
```

---

## Summary: Emma Reactive Capabilities

| Phase | Feature | Status |
|-------|---------|--------|
| **1** | Event Bus (Redis Streams) | ✅ Complete |
| **2** | Background Tasks (Celery) | ✅ Complete |
| **3** | Trigger System | ✅ Complete |
| **4** | Notification System | ✅ Complete |
| **5** | Multi-Channel Messaging | ✅ Complete |
| **6** | Heartbeat & Proactive Intelligence | ✅ Complete |

*Architecture: Redis Streams + Trigger Engine + LangGraph Background + Multi-Channel + WebSocket Notifications + Proactive Heartbeat*

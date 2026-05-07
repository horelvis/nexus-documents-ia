"""Read-only repository over the LangGraph checkpointer tables.

The chat history surface (sidebar, REST listing, single-thread fetch)
sources its data from the checkpointer (`checkpoints`, `checkpoint_blobs`,
`checkpoint_writes`) — that is the single source of truth for conversation
state. There is no parallel ``emma_sessions`` table; the previous
implementation duplicated message storage there but never stayed in sync
with the LangGraph SDK and the table is being dropped.

This module exposes minimal helpers that any handler (REST endpoints
under ``/emma/sessions``) can call directly. Title/preview generation
is intentionally minimal here — extracting the first human message
requires deserialising the msgpack blob from ``checkpoint_blobs`` via
LangGraph's serializer, which is expensive for a list view. The list
returns a placeholder title; clients that need richer titles can fetch
a single thread to inspect its messages.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.checkpointer import _ensure_pool

logger = logging.getLogger(__name__)


_LIST_QUERY = """
WITH agg AS (
  SELECT thread_id,
         MIN(checkpoint_id) AS first_ckpt_id,
         MAX(checkpoint_id) AS last_ckpt_id,
         COUNT(*)            AS ckpt_count
  FROM checkpoints
  GROUP BY thread_id
),
first_ts AS (
  SELECT c.thread_id,
         (c.checkpoint->>'ts')::timestamptz AS created_at
  FROM checkpoints c
  JOIN agg a ON a.thread_id = c.thread_id AND a.first_ckpt_id = c.checkpoint_id
),
last_ts AS (
  SELECT c.thread_id,
         (c.checkpoint->>'ts')::timestamptz AS last_at,
         (c.metadata->>'step')::int         AS last_step
  FROM checkpoints c
  JOIN agg a ON a.thread_id = c.thread_id AND a.last_ckpt_id = c.checkpoint_id
)
SELECT a.thread_id,
       a.ckpt_count,
       f.created_at,
       l.last_at,
       l.last_step
FROM agg a
JOIN first_ts f USING (thread_id)
JOIN last_ts  l USING (thread_id)
ORDER BY l.last_at DESC NULLS LAST
LIMIT %s OFFSET %s
"""

_COUNT_QUERY = "SELECT COUNT(DISTINCT thread_id) AS total FROM checkpoints"

_DELETE_QUERIES = (
    "DELETE FROM checkpoint_writes WHERE thread_id = %s",
    "DELETE FROM checkpoint_blobs  WHERE thread_id = %s",
    "DELETE FROM checkpoints       WHERE thread_id = %s",
)


async def list_threads(*, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """Return a paginated list of threads ordered by last activity desc.

    Output shape matches the legacy contract enough that the frontend
    sidebar keeps working: ``{sessions: [...], total, limit, offset}``.
    Each session has session_id, title, message_count, created_at,
    last_message_at. ``is_pinned`` / ``is_archived`` are removed from
    the contract — those features lived in the dropped table.
    """
    pool = await _ensure_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(_LIST_QUERY, (limit, offset))
            rows = await cur.fetchall()
            await cur.execute(_COUNT_QUERY)
            (total,) = await cur.fetchone()

    sessions = [
        {
            "id": row[0],
            "session_id": row[0],
            "title": f"Conversación {row[0][:8]}",
            "message_count": row[4] if row[4] is not None else (row[1] // 2 or 1),
            "last_message_at": row[3].isoformat() if row[3] else None,
            "created_at": row[2].isoformat() if row[2] else None,
            "first_message_preview": None,
            "last_message_preview": None,
        }
        for row in rows
    ]
    return {"sessions": sessions, "total": int(total), "limit": limit, "offset": offset}


async def get_thread_summary(thread_id: str) -> Optional[dict[str, Any]]:
    """Return a single thread's aggregate summary (no messages).

    For full message reconstruction the caller should use the LangGraph
    AsyncPostgresSaver via ``get_checkpointer()`` — that path knows how
    to deserialise the msgpack blobs.
    """
    pool = await _ensure_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT MIN(checkpoint_id) AS first_id,
                       MAX(checkpoint_id) AS last_id,
                       COUNT(*)            AS cnt
                FROM checkpoints
                WHERE thread_id = %s
                """,
                (thread_id,),
            )
            agg = await cur.fetchone()
            if not agg or not agg[2]:
                return None
            await cur.execute(
                """
                SELECT (checkpoint->>'ts')::timestamptz, (metadata->>'step')::int
                FROM checkpoints
                WHERE thread_id = %s AND checkpoint_id = %s
                """,
                (thread_id, agg[1]),
            )
            last = await cur.fetchone()
            await cur.execute(
                """
                SELECT (checkpoint->>'ts')::timestamptz
                FROM checkpoints
                WHERE thread_id = %s AND checkpoint_id = %s
                """,
                (thread_id, agg[0]),
            )
            first = await cur.fetchone()

    return {
        "id": thread_id,
        "session_id": thread_id,
        "title": f"Conversación {thread_id[:8]}",
        "message_count": last[1] if last and last[1] is not None else (agg[2] // 2 or 1),
        "last_message_at": last[0].isoformat() if last and last[0] else None,
        "created_at": first[0].isoformat() if first and first[0] else None,
    }


async def delete_thread(thread_id: str) -> bool:
    """Delete a thread from all three checkpointer tables. Returns True
    if at least one row was removed from ``checkpoints``."""
    pool = await _ensure_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            removed = 0
            for query in _DELETE_QUERIES:
                await cur.execute(query, (thread_id,))
                if "checkpoints" in query and "_blobs" not in query and "_writes" not in query:
                    removed = cur.rowcount
    return removed > 0

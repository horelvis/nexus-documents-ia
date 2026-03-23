"""DEPRECATED: This module will be removed. Memory recall should use
Weaviate hybrid search instead of pgvector.

MemoRAG memory store using pgvector.
"""

import hashlib
import warnings
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class MemoryRow:
    document_id: str
    content: str
    metadata: Dict[str, Any]
    similarity: float


class MemoRAGStore:
    def __init__(self) -> None:
        self._db_session_factory = None
        self._initialized = False

    async def _get_session_factory(self):
        if self._db_session_factory is None:
            # Ensure asyncpg driver is used (settings.database_url may be postgresql://)
            db_url = settings.database_url
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            engine = create_async_engine(db_url)
            self._db_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        return self._db_session_factory

    async def initialize(self) -> None:
        if self._initialized:
            return

        warnings.warn(
            "MemoRAG pgvector is deprecated. Use Weaviate hybrid search.",
            DeprecationWarning,
            stacklevel=2,
        )

        session_factory = await self._get_session_factory()

        # Each DDL in its own session to prevent aborted-transaction cascade.
        # If CREATE EXTENSION fails (pgvector not installed), subsequent DDL
        # still runs — just without VECTOR column type.
        ddl_steps = [
            ("vector extension", "CREATE EXTENSION IF NOT EXISTS vector"),
            (
                "table",
                f"""
                CREATE TABLE IF NOT EXISTS {settings.memorag_table_name} (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    chunk_index INT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    metadata JSONB,
                    embedding VECTOR({settings.memorag_embedding_dim}),
                    memory_version INT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
                """,
            ),
            (
                "tenant_doc index",
                f"""
                CREATE INDEX IF NOT EXISTS {settings.memorag_table_name}_tenant_doc_idx
                ON {settings.memorag_table_name} (tenant_id, document_id)
                """,
            ),
            (
                "tenant index",
                f"""
                CREATE INDEX IF NOT EXISTS {settings.memorag_table_name}_tenant_idx
                ON {settings.memorag_table_name} (tenant_id)
                """,
            ),
            (
                "embedding index",
                f"""
                CREATE INDEX IF NOT EXISTS {settings.memorag_table_name}_embedding_idx
                ON {settings.memorag_table_name} USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """,
            ),
        ]

        for step_name, ddl_sql in ddl_steps:
            try:
                async with session_factory() as session:
                    await session.execute(text(ddl_sql))
                    await session.commit()
            except Exception as e:
                logger.warning(f"MemoRAG {step_name} init failed: {e}")

        self._initialized = True

    @staticmethod
    def hash_text(text_value: str) -> str:
        return hashlib.sha256(text_value.encode("utf-8", errors="ignore")).hexdigest()

    async def document_hash(self, tenant_id: str, document_id: str) -> Optional[str]:
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            try:
                result = await session.execute(text(
                    f"""
                    SELECT content_hash
                    FROM {settings.memorag_table_name}
                    WHERE tenant_id = :tenant_id AND document_id = :document_id
                    LIMIT 1
                    """
                ), {"tenant_id": tenant_id, "document_id": document_id})
                row = result.first()
                return row[0] if row else None
            except Exception as e:
                logger.debug(f"MemoRAG document_hash failed: {e}")
                return None

    async def replace_document_chunks(
        self,
        tenant_id: str,
        document_id: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: Dict[str, Any],
        content_hash: str,
        memory_version: int,
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings length mismatch")

        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            await session.execute(text(
                f"""
                DELETE FROM {settings.memorag_table_name}
                WHERE tenant_id = :tenant_id AND document_id = :document_id
                """
            ), {"tenant_id": tenant_id, "document_id": document_id})

            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                await session.execute(text(
                    f"""
                    INSERT INTO {settings.memorag_table_name}
                    (tenant_id, document_id, chunk_index, content, content_hash, metadata, embedding, memory_version)
                    VALUES (:tenant_id, :document_id, :chunk_index, :content, :content_hash, :metadata, CAST(:embedding AS vector), :memory_version)
                    """
                ), {
                    "tenant_id": tenant_id,
                    "document_id": document_id,
                    "chunk_index": idx,
                    "content": chunk,
                    "content_hash": content_hash,
                    "metadata": json.dumps(metadata) if isinstance(metadata, dict) else metadata,
                    "embedding": embedding_str,
                    "memory_version": memory_version,
                })

            await session.commit()

    async def recall(
        self,
        tenant_id: str,
        embedding: List[float],
        limit: int,
        domain: Optional[str] = None,
        semantic_type: Optional[str] = None,
    ) -> List[MemoryRow]:
        session_factory = await self._get_session_factory()
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        filters = ["tenant_id = :tenant_id", "embedding IS NOT NULL"]
        params: Dict[str, Any] = {"tenant_id": tenant_id, "embedding": embedding_str, "limit": limit}

        if domain:
            filters.append("metadata->>'domain' = :domain")
            params["domain"] = domain
        if semantic_type:
            filters.append("metadata->>'semantic_type' = :semantic_type")
            params["semantic_type"] = semantic_type

        where_clause = " AND ".join(filters)

        async with session_factory() as session:
            try:
                result = await session.execute(text(
                    f"""
                    SELECT document_id, content, metadata,
                           1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
                    FROM {settings.memorag_table_name}
                    WHERE {where_clause}
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :limit
                    """
                ), params)
                rows = result.fetchall()
                return [
                    MemoryRow(
                        document_id=row[0],
                        content=row[1],
                        metadata=row[2] or {},
                        similarity=float(row[3] or 0.0),
                    )
                    for row in rows
                ]
            except Exception as e:
                logger.warning(f"MemoRAG recall failed: {e}")
                return []

    async def keyword_recall(
        self,
        tenant_id: str,
        query: str,
        limit: int,
        domain: Optional[str] = None,
        semantic_type: Optional[str] = None,
    ) -> List[MemoryRow]:
        session_factory = await self._get_session_factory()
        filters = ["tenant_id = :tenant_id", "content ILIKE :pattern"]
        params: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "pattern": f"%{query}%",
            "limit": limit,
        }

        if domain:
            filters.append("metadata->>'domain' = :domain")
            params["domain"] = domain
        if semantic_type:
            filters.append("metadata->>'semantic_type' = :semantic_type")
            params["semantic_type"] = semantic_type

        where_clause = " AND ".join(filters)

        async with session_factory() as session:
            try:
                result = await session.execute(text(
                    f"""
                    SELECT document_id, content, metadata, 0.0 AS similarity
                    FROM {settings.memorag_table_name}
                    WHERE {where_clause}
                    LIMIT :limit
                    """
                ), params)
                rows = result.fetchall()
                return [
                    MemoryRow(
                        document_id=row[0],
                        content=row[1],
                        metadata=row[2] or {},
                        similarity=0.0,
                    )
                    for row in rows
                ]
            except Exception as e:
                logger.warning(f"MemoRAG keyword recall failed: {e}")
                return []

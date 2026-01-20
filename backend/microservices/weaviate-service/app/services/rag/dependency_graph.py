"""
Dependency Graph for Hierarchical RAG

Implements a document dependency graph using Apache AGE for:
- Structural dependencies: Section → Subsection → Chunk
- Semantic dependencies: Chunk references other chunks
- Cross-document references: Document A references Document B

Architecture:
┌─────────────────────────────────────────────────────────────────────────┐
│                    DEPENDENCY GRAPH SCHEMA                               │
├─────────────────────────────────────────────────────────────────────────┤
│  Vertices:                                                               │
│  ├─ Document: {id, title, type, tenant_id}                              │
│  ├─ Section: {id, title, level, parent_id, document_id}                 │
│  └─ Chunk: {id, sequence, text_preview, section_id, document_id}        │
│                                                                         │
│  Edges (Dependencies):                                                   │
│  ├─ CONTAINS: Document → Section (order)                                │
│  ├─ HAS_SUBSECTION: Section → Section (order)                           │
│  ├─ HAS_CHUNK: Section → Chunk (order)                                  │
│  ├─ NEXT_CHUNK: Chunk → Chunk (structural adjacency)                    │
│  ├─ REFERENCES: Chunk → Chunk (semantic reference)                      │
│  └─ CITES: Document → Document (citation)                               │
└─────────────────────────────────────────────────────────────────────────┘

Use Cases:

1. **Hierarchical Retrieval**: Given a relevant chunk, traverse up to get
   section context and document metadata for better understanding.

2. **Chunk Expansion**: Given a chunk, traverse NEXT_CHUNK edges to get
   adjacent chunks for context preservation.

3. **Reference Following**: Given a chunk with REFERENCES edges, retrieve
   the referenced chunks for complete context.

4. **Cross-Document Context**: When a document CITES another, include
   relevant parts of the cited document in context.

Cypher Query Examples:

  -- Get section hierarchy for a chunk:
  MATCH (c:Chunk {id: 'chunk-123'})<-[:HAS_CHUNK]-(s:Section)
        <-[:HAS_SUBSECTION*0..5]-(root:Section)
        <-[:CONTAINS]-(d:Document)
  RETURN d.title, collect(s.title)

  -- Get adjacent chunks for expansion:
  MATCH (c:Chunk {id: 'chunk-123'})-[:NEXT_CHUNK*1..2]-(adjacent:Chunk)
  RETURN adjacent.id, adjacent.text_preview

  -- Find all chunks that reference a given chunk:
  MATCH (c:Chunk {id: 'chunk-123'})<-[:REFERENCES]-(referencing:Chunk)
  RETURN referencing.id, referencing.document_id

Usage:
    from app.services.rag.dependency_graph import dependency_graph

    # Build graph during indexing
    await dependency_graph.index_document_structure(
        document_id="doc-123",
        tenant_id="tenant-456",
        sections=parsed_sections,
        chunks=parsed_chunks
    )

    # Expand chunk context for retrieval
    expanded = await dependency_graph.expand_chunk_context(
        chunk_id="chunk-789",
        tenant_id="tenant-456",
        include_adjacent=2,
        include_section=True
    )
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import asyncpg

from ...core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class DocumentNode:
    """Represents a document in the dependency graph."""
    document_id: str
    title: str
    document_type: str
    tenant_id: str
    vertex_id: Optional[int] = None


@dataclass
class SectionNode:
    """Represents a section in the dependency graph."""
    section_id: str
    title: str
    level: int  # 1 = H1, 2 = H2, etc.
    document_id: str
    parent_section_id: Optional[str] = None
    order: int = 0
    vertex_id: Optional[int] = None


@dataclass
class ChunkNode:
    """Represents a chunk in the dependency graph."""
    chunk_id: str
    sequence: int
    text_preview: str  # First 200 chars
    document_id: str
    section_id: Optional[str] = None
    vertex_id: Optional[int] = None


@dataclass
class ChunkExpansion:
    """Result of expanding a chunk's context."""
    chunk_id: str
    document_title: str
    section_hierarchy: List[str]
    adjacent_chunks: List[Dict[str, Any]]
    referenced_chunks: List[Dict[str, Any]]
    citing_documents: List[Dict[str, Any]]


class DependencyGraphService:
    """
    Dependency Graph Service for Hierarchical RAG.

    Uses Apache AGE to store and query document structure dependencies.
    """

    GRAPH_NAME = "knowledge_graph"  # Same graph as entities

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database connection."""
        if self._initialized:
            return

        try:
            db_url = settings.database_url
            if "+asyncpg" in db_url:
                db_url = db_url.replace("+asyncpg", "")

            self._pool = await asyncpg.create_pool(
                db_url,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )

            self._initialized = True
            logger.info("✅ Dependency Graph Service initialized")

        except Exception as e:
            logger.error(f"❌ Failed to initialize Dependency Graph: {e}")
            self._initialized = True

    async def _get_connection(self):
        """Get a connection with AGE loaded."""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")

        conn = await self._pool.acquire()
        await conn.execute("LOAD 'age';")
        await conn.execute("SET search_path = ag_catalog, \"$user\", public;")
        return conn

    async def _release_connection(self, conn):
        """Release connection back to pool."""
        await self._pool.release(conn)

    async def _execute_cypher(
        self,
        conn: asyncpg.Connection,
        cypher_query: str,
        return_columns: List[Tuple[str, str]],
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return results."""
        import json

        col_specs = ", ".join([f"{name} agtype" for name, _ in return_columns])

        sql = f"""
            SELECT * FROM cypher('{self.GRAPH_NAME}', $$
                {cypher_query}
            $$) AS ({col_specs});
        """

        try:
            rows = await conn.fetch(sql)
            results = []

            for row in rows:
                result = {}
                for i, (col_name, _) in enumerate(return_columns):
                    value = row[i]
                    if value is not None:
                        if isinstance(value, str):
                            try:
                                result[col_name] = json.loads(value)
                            except json.JSONDecodeError:
                                result[col_name] = value
                        else:
                            result[col_name] = value
                    else:
                        result[col_name] = None
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Cypher query failed: {e}")
            raise

    async def index_document_structure(
        self,
        document_id: str,
        tenant_id: str,
        title: str,
        document_type: str,
        sections: List[Dict[str, Any]],
        chunks: List[Dict[str, Any]],
    ) -> bool:
        """
        Index a document's hierarchical structure.

        Args:
            document_id: Document identifier
            tenant_id: Tenant identifier
            title: Document title
            document_type: Type of document
            sections: List of section dicts with {id, title, level, parent_id, order}
            chunks: List of chunk dicts with {id, sequence, text, section_id}

        Returns:
            True if successful
        """
        await self.initialize()

        if not self._pool:
            return False

        try:
            conn = await self._get_connection()

            try:
                # 1. Create Document vertex
                escaped_title = title.replace("'", "''")
                cypher_doc = f"""
                    MERGE (d:Document {{id: '{document_id}', tenant_id: '{tenant_id}'}})
                    ON CREATE SET d.title = '{escaped_title}',
                                  d.document_type = '{document_type}',
                                  d.created_at = datetime()
                    ON MATCH SET d.title = '{escaped_title}',
                                 d.document_type = '{document_type}'
                    RETURN id(d)
                """
                await self._execute_cypher(conn, cypher_doc, [("id", "bigint")])

                # 2. Create Section vertices and CONTAINS/HAS_SUBSECTION edges
                for section in sections:
                    section_id = section["id"]
                    section_title = section.get("title", "").replace("'", "''")
                    level = section.get("level", 1)
                    parent_id = section.get("parent_id")
                    order = section.get("order", 0)

                    # Create section
                    cypher_section = f"""
                        MERGE (s:Section {{id: '{section_id}', tenant_id: '{tenant_id}'}})
                        ON CREATE SET s.title = '{section_title}',
                                      s.level = {level},
                                      s.document_id = '{document_id}'
                        RETURN id(s)
                    """
                    await self._execute_cypher(conn, cypher_section, [("id", "bigint")])

                    if parent_id:
                        # Create HAS_SUBSECTION edge from parent
                        cypher_subsection = f"""
                            MATCH (parent:Section {{id: '{parent_id}', tenant_id: '{tenant_id}'}})
                            MATCH (child:Section {{id: '{section_id}', tenant_id: '{tenant_id}'}})
                            MERGE (parent)-[r:HAS_SUBSECTION]->(child)
                            ON CREATE SET r.order = {order}
                            RETURN id(r)
                        """
                        await self._execute_cypher(conn, cypher_subsection, [("id", "bigint")])
                    else:
                        # Create CONTAINS edge from document
                        cypher_contains = f"""
                            MATCH (d:Document {{id: '{document_id}', tenant_id: '{tenant_id}'}})
                            MATCH (s:Section {{id: '{section_id}', tenant_id: '{tenant_id}'}})
                            MERGE (d)-[r:CONTAINS]->(s)
                            ON CREATE SET r.order = {order}
                            RETURN id(r)
                        """
                        await self._execute_cypher(conn, cypher_contains, [("id", "bigint")])

                # 3. Create Chunk vertices and edges
                prev_chunk_id = None
                for chunk in chunks:
                    chunk_id = chunk["id"]
                    sequence = chunk.get("sequence", 0)
                    text = chunk.get("text", "")[:200].replace("'", "''")
                    section_id = chunk.get("section_id")

                    # Create chunk
                    cypher_chunk = f"""
                        MERGE (c:Chunk {{id: '{chunk_id}', tenant_id: '{tenant_id}'}})
                        ON CREATE SET c.sequence = {sequence},
                                      c.text_preview = '{text}',
                                      c.document_id = '{document_id}'
                        RETURN id(c)
                    """
                    await self._execute_cypher(conn, cypher_chunk, [("id", "bigint")])

                    # Create HAS_CHUNK edge from section
                    if section_id:
                        cypher_has_chunk = f"""
                            MATCH (s:Section {{id: '{section_id}', tenant_id: '{tenant_id}'}})
                            MATCH (c:Chunk {{id: '{chunk_id}', tenant_id: '{tenant_id}'}})
                            MERGE (s)-[r:HAS_CHUNK]->(c)
                            ON CREATE SET r.order = {sequence}
                            RETURN id(r)
                        """
                        await self._execute_cypher(conn, cypher_has_chunk, [("id", "bigint")])

                    # Create NEXT_CHUNK edge for adjacency
                    if prev_chunk_id:
                        cypher_next = f"""
                            MATCH (prev:Chunk {{id: '{prev_chunk_id}', tenant_id: '{tenant_id}'}})
                            MATCH (curr:Chunk {{id: '{chunk_id}', tenant_id: '{tenant_id}'}})
                            MERGE (prev)-[r:NEXT_CHUNK]->(curr)
                            RETURN id(r)
                        """
                        await self._execute_cypher(conn, cypher_next, [("id", "bigint")])

                    prev_chunk_id = chunk_id

                logger.info(
                    f"✅ Indexed document structure: {document_id} "
                    f"({len(sections)} sections, {len(chunks)} chunks)"
                )
                return True

            finally:
                await self._release_connection(conn)

        except Exception as e:
            logger.error(f"❌ Failed to index document structure: {e}")
            return False

    async def add_chunk_reference(
        self,
        source_chunk_id: str,
        target_chunk_id: str,
        tenant_id: str,
        reference_type: str = "semantic",
        strength: float = 0.5,
    ) -> bool:
        """
        Add a reference edge between chunks.

        Used when semantic analysis detects that one chunk references another.

        Args:
            source_chunk_id: Source chunk ID
            target_chunk_id: Target chunk ID
            tenant_id: Tenant identifier
            reference_type: Type of reference (semantic, citation, continuation)
            strength: Reference strength (0-1)

        Returns:
            True if successful
        """
        await self.initialize()

        if not self._pool:
            return False

        try:
            conn = await self._get_connection()

            try:
                cypher = f"""
                    MATCH (source:Chunk {{id: '{source_chunk_id}', tenant_id: '{tenant_id}'}})
                    MATCH (target:Chunk {{id: '{target_chunk_id}', tenant_id: '{tenant_id}'}})
                    MERGE (source)-[r:REFERENCES]->(target)
                    ON CREATE SET r.reference_type = '{reference_type}',
                                  r.strength = {strength}
                    ON MATCH SET r.strength = CASE WHEN r.strength > {strength}
                                                   THEN r.strength ELSE {strength} END
                    RETURN id(r)
                """
                await self._execute_cypher(conn, cypher, [("id", "bigint")])
                return True

            finally:
                await self._release_connection(conn)

        except Exception as e:
            logger.error(f"❌ Failed to add chunk reference: {e}")
            return False

    async def add_document_citation(
        self,
        source_document_id: str,
        target_document_id: str,
        tenant_id: str,
        citation_context: Optional[str] = None,
    ) -> bool:
        """
        Add a citation edge between documents.

        Used when one document references/cites another.

        Args:
            source_document_id: Citing document ID
            target_document_id: Cited document ID
            tenant_id: Tenant identifier
            citation_context: Optional context of the citation

        Returns:
            True if successful
        """
        await self.initialize()

        if not self._pool:
            return False

        try:
            conn = await self._get_connection()

            try:
                context_prop = ""
                if citation_context:
                    escaped = citation_context[:500].replace("'", "''")
                    context_prop = f", r.context = '{escaped}'"

                cypher = f"""
                    MATCH (source:Document {{id: '{source_document_id}', tenant_id: '{tenant_id}'}})
                    MATCH (target:Document {{id: '{target_document_id}', tenant_id: '{tenant_id}'}})
                    MERGE (source)-[r:CITES]->(target)
                    ON CREATE SET r.created_at = datetime(){context_prop}
                    RETURN id(r)
                """
                await self._execute_cypher(conn, cypher, [("id", "bigint")])
                return True

            finally:
                await self._release_connection(conn)

        except Exception as e:
            logger.error(f"❌ Failed to add document citation: {e}")
            return False

    async def expand_chunk_context(
        self,
        chunk_id: str,
        tenant_id: str,
        include_adjacent: int = 2,
        include_section: bool = True,
        include_references: bool = True,
    ) -> Optional[ChunkExpansion]:
        """
        Expand a chunk's context by traversing the dependency graph.

        This is the core method for Hierarchical RAG - it retrieves all
        relevant context for a chunk.

        Args:
            chunk_id: Chunk identifier
            tenant_id: Tenant identifier
            include_adjacent: Number of adjacent chunks to include (before/after)
            include_section: Include section hierarchy
            include_references: Include referenced chunks

        Returns:
            ChunkExpansion with all context data
        """
        await self.initialize()

        if not self._pool:
            return None

        try:
            conn = await self._get_connection()

            try:
                expansion = ChunkExpansion(
                    chunk_id=chunk_id,
                    document_title="",
                    section_hierarchy=[],
                    adjacent_chunks=[],
                    referenced_chunks=[],
                    citing_documents=[],
                )

                # 1. Get document title and section hierarchy
                if include_section:
                    cypher_hierarchy = f"""
                        MATCH (c:Chunk {{id: '{chunk_id}', tenant_id: '{tenant_id}'}})
                              <-[:HAS_CHUNK]-(s:Section)
                              <-[:HAS_SUBSECTION*0..5]-(ancestors:Section)
                              <-[:CONTAINS]-(d:Document)
                        RETURN d.title AS doc_title,
                               collect(DISTINCT ancestors.title) AS section_titles
                    """
                    results = await self._execute_cypher(
                        conn,
                        cypher_hierarchy,
                        [("doc_title", "text"), ("section_titles", "text[]")],
                    )

                    if results:
                        expansion.document_title = results[0].get("doc_title", "")
                        expansion.section_hierarchy = results[0].get("section_titles", [])

                # 2. Get adjacent chunks
                if include_adjacent > 0:
                    # Forward adjacency
                    cypher_forward = f"""
                        MATCH (c:Chunk {{id: '{chunk_id}', tenant_id: '{tenant_id}'}})
                              -[:NEXT_CHUNK*1..{include_adjacent}]->(next:Chunk)
                        RETURN next.id AS id,
                               next.sequence AS sequence,
                               next.text_preview AS preview
                        ORDER BY next.sequence
                    """
                    forward_results = await self._execute_cypher(
                        conn,
                        cypher_forward,
                        [("id", "text"), ("sequence", "int"), ("preview", "text")],
                    )

                    # Backward adjacency
                    cypher_backward = f"""
                        MATCH (c:Chunk {{id: '{chunk_id}', tenant_id: '{tenant_id}'}})
                              <-[:NEXT_CHUNK*1..{include_adjacent}]-(prev:Chunk)
                        RETURN prev.id AS id,
                               prev.sequence AS sequence,
                               prev.text_preview AS preview
                        ORDER BY prev.sequence
                    """
                    backward_results = await self._execute_cypher(
                        conn,
                        cypher_backward,
                        [("id", "text"), ("sequence", "int"), ("preview", "text")],
                    )

                    # Combine and sort by sequence
                    all_adjacent = backward_results + forward_results
                    all_adjacent.sort(key=lambda x: x.get("sequence", 0))
                    expansion.adjacent_chunks = all_adjacent

                # 3. Get referenced chunks
                if include_references:
                    cypher_refs = f"""
                        MATCH (c:Chunk {{id: '{chunk_id}', tenant_id: '{tenant_id}'}})
                              -[:REFERENCES]->(ref:Chunk)
                        RETURN ref.id AS id,
                               ref.document_id AS document_id,
                               ref.text_preview AS preview
                    """
                    ref_results = await self._execute_cypher(
                        conn,
                        cypher_refs,
                        [("id", "text"), ("document_id", "text"), ("preview", "text")],
                    )
                    expansion.referenced_chunks = ref_results

                logger.debug(
                    f"Expanded chunk {chunk_id}: "
                    f"{len(expansion.adjacent_chunks)} adjacent, "
                    f"{len(expansion.referenced_chunks)} referenced"
                )

                return expansion

            finally:
                await self._release_connection(conn)

        except Exception as e:
            logger.error(f"❌ Failed to expand chunk context: {e}")
            return None

    async def get_document_graph_preview(
        self,
        document_id: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Get a preview of a document's structure graph.

        Useful for visualization and debugging.

        Args:
            document_id: Document identifier
            tenant_id: Tenant identifier

        Returns:
            Graph preview with nodes and edges
        """
        await self.initialize()

        if not self._pool:
            return {"nodes": [], "edges": []}

        try:
            conn = await self._get_connection()

            try:
                # Get all sections
                cypher_sections = f"""
                    MATCH (d:Document {{id: '{document_id}', tenant_id: '{tenant_id}'}})
                          -[:CONTAINS|HAS_SUBSECTION*1..10]->(s:Section)
                    RETURN s.id AS id, s.title AS title, s.level AS level
                """
                sections = await self._execute_cypher(
                    conn,
                    cypher_sections,
                    [("id", "text"), ("title", "text"), ("level", "int")],
                )

                # Get chunk count per section
                cypher_chunks = f"""
                    MATCH (d:Document {{id: '{document_id}', tenant_id: '{tenant_id}'}})
                          -[:CONTAINS|HAS_SUBSECTION*1..10]->(s:Section)
                          -[:HAS_CHUNK]->(c:Chunk)
                    RETURN s.id AS section_id, count(c) AS chunk_count
                """
                chunk_counts = await self._execute_cypher(
                    conn,
                    cypher_chunks,
                    [("section_id", "text"), ("chunk_count", "int")],
                )

                # Build preview
                count_map = {r["section_id"]: r["chunk_count"] for r in chunk_counts}

                nodes = []
                for section in sections:
                    nodes.append({
                        "id": section["id"],
                        "label": section["title"],
                        "level": section["level"],
                        "chunk_count": count_map.get(section["id"], 0),
                    })

                return {
                    "document_id": document_id,
                    "sections": nodes,
                    "total_sections": len(sections),
                    "total_chunks": sum(count_map.values()),
                }

            finally:
                await self._release_connection(conn)

        except Exception as e:
            logger.error(f"❌ Failed to get document graph preview: {e}")
            return {"nodes": [], "edges": [], "error": str(e)}

    async def delete_document_graph(
        self,
        document_id: str,
        tenant_id: str,
    ) -> bool:
        """
        Delete all graph data for a document.

        Args:
            document_id: Document identifier
            tenant_id: Tenant identifier

        Returns:
            True if successful
        """
        await self.initialize()

        if not self._pool:
            return False

        try:
            conn = await self._get_connection()

            try:
                # Delete chunks first
                cypher_chunks = f"""
                    MATCH (c:Chunk {{document_id: '{document_id}', tenant_id: '{tenant_id}'}})
                    DETACH DELETE c
                """
                await self._execute_cypher(conn, cypher_chunks, [])

                # Delete sections
                cypher_sections = f"""
                    MATCH (s:Section {{document_id: '{document_id}', tenant_id: '{tenant_id}'}})
                    DETACH DELETE s
                """
                await self._execute_cypher(conn, cypher_sections, [])

                # Delete document
                cypher_doc = f"""
                    MATCH (d:Document {{id: '{document_id}', tenant_id: '{tenant_id}'}})
                    DETACH DELETE d
                """
                await self._execute_cypher(conn, cypher_doc, [])

                logger.info(f"✅ Deleted document graph: {document_id}")
                return True

            finally:
                await self._release_connection(conn)

        except Exception as e:
            logger.error(f"❌ Failed to delete document graph: {e}")
            return False

    async def close(self) -> None:
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._initialized = False


# Global singleton instance
dependency_graph = DependencyGraphService()

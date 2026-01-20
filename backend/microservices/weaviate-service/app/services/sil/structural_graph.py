"""
Structural Graph Service for Apache AGE

Extends the knowledge graph with structural nodes and edges for SIL:

Vertex Labels:
- structural_document: Document metadata (not content)
- structural_folder: Folder in hierarchy
- structural_site: SharePoint site or connector source

Edge Labels:
- contains: Folder contains document/subfolder
- version_of: Document is version of another
- relates_to: Documents are semantically related
- sibling_of: Documents in same folder

The structural graph maintains STRUCTURE, not content.
It enables queries like:
- "How many contracts are in the ACME folder?"
- "What documents were added this week?"
- "Show related documents to contract X"

Temporal Support:
Each node has valid_from and valid_to timestamps for point-in-time queries.
"""

import logging
import json
import asyncio
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from dataclasses import dataclass, field

from ...services.knowledge.age_graph_service import AGEKnowledgeGraphService, age_knowledge_graph
from .schemas import StructuralMetadata, SemanticType, DomainType

logger = logging.getLogger(__name__)


@dataclass
class StructuralNode:
    """A structural node in the graph."""

    node_id: str
    label: str  # structural_document, structural_folder, structural_site
    tenant_id: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_cypher_props(self) -> str:
        """Convert to Cypher property map."""
        props = {
            "node_id": self.node_id,
            "tenant_id": self.tenant_id,
            **self.properties,
        }

        parts = []
        for k, v in props.items():
            if v is None:
                continue
            if isinstance(v, str):
                escaped = v.replace("'", "''").replace("\\", "\\\\")
                parts.append(f"{k}: '{escaped}'")
            elif isinstance(v, bool):
                parts.append(f"{k}: {str(v).lower()}")
            elif isinstance(v, (int, float)):
                parts.append(f"{k}: {v}")
            elif isinstance(v, list):
                escaped_list = [
                    f"'{s.replace(chr(39), chr(39)+chr(39))}'" if isinstance(s, str) else str(s)
                    for s in v
                ]
                parts.append(f"{k}: [{', '.join(escaped_list)}]")
            elif isinstance(v, datetime):
                parts.append(f"{k}: '{v.isoformat()}'")

        return "{" + ", ".join(parts) + "}"


@dataclass
class StructuralEdge:
    """A structural edge in the graph."""

    source_id: str
    target_id: str
    label: str  # contains, version_of, relates_to, sibling_of
    tenant_id: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_cypher_props(self) -> str:
        """Convert to Cypher property map."""
        props = {
            "tenant_id": self.tenant_id,
            **self.properties,
        }

        parts = []
        for k, v in props.items():
            if v is None:
                continue
            if isinstance(v, str):
                escaped = v.replace("'", "''").replace("\\", "\\\\")
                parts.append(f"{k}: '{escaped}'")
            elif isinstance(v, bool):
                parts.append(f"{k}: {str(v).lower()}")
            elif isinstance(v, (int, float)):
                parts.append(f"{k}: {v}")
            elif isinstance(v, datetime):
                parts.append(f"{k}: '{v.isoformat()}'")

        return "{" + ", ".join(parts) + "}"


class StructuralGraphService:
    """
    Service for managing structural graph in Apache AGE.

    This extends the knowledge graph with structural metadata:
    - Documents as structural nodes (no content, just metadata)
    - Folders as structural nodes
    - Relationships: contains, version_of, relates_to, sibling_of

    All operations are tenant-isolated via the tenant_id property.
    """

    GRAPH_NAME = "knowledge_graph"  # Shared with knowledge graph

    # Vertex labels for structural data
    LABEL_DOCUMENT = "structural_document"
    LABEL_FOLDER = "structural_folder"
    LABEL_SITE = "structural_site"

    # Edge labels for structural relationships
    EDGE_CONTAINS = "contains"
    EDGE_VERSION_OF = "version_of"
    EDGE_RELATES_TO = "relates_to"
    EDGE_SIBLING_OF = "sibling_of"

    def __init__(self, age_service: Optional[AGEKnowledgeGraphService] = None):
        self._age = age_service or age_knowledge_graph
        self._initialized = False
        self._schema_initialized = False

    async def initialize(self) -> None:
        """Initialize the structural graph service."""
        if self._initialized:
            return

        await self._age.initialize()

        # Ensure structural labels exist
        await self._ensure_structural_schema()

        self._initialized = True
        logger.info("✅ StructuralGraphService initialized")

    async def _ensure_structural_schema(self) -> None:
        """Ensure structural vertex and edge labels exist in the graph."""
        if self._schema_initialized:
            return

        if not self._age._pool:
            logger.warning("AGE pool not available, skipping schema initialization")
            return

        try:
            async with self._age._get_connection() as conn:
                # Check and create vertex labels
                for label in [self.LABEL_DOCUMENT, self.LABEL_FOLDER, self.LABEL_SITE]:
                    exists = await conn.fetchval(
                        """
                        SELECT count(*) FROM ag_catalog.ag_label
                        WHERE name = $1 AND graph = (
                            SELECT graphid FROM ag_catalog.ag_graph WHERE name = $2
                        )
                        """,
                        label,
                        self.GRAPH_NAME,
                    )
                    if exists == 0:
                        await conn.execute(
                            f"SELECT create_vlabel('{self.GRAPH_NAME}', '{label}');"
                        )
                        logger.info(f"✅ Created vertex label: {label}")

                # Check and create edge labels
                for label in [self.EDGE_CONTAINS, self.EDGE_VERSION_OF, self.EDGE_RELATES_TO, self.EDGE_SIBLING_OF]:
                    exists = await conn.fetchval(
                        """
                        SELECT count(*) FROM ag_catalog.ag_label
                        WHERE name = $1 AND graph = (
                            SELECT graphid FROM ag_catalog.ag_graph WHERE name = $2
                        )
                        """,
                        label,
                        self.GRAPH_NAME,
                    )
                    if exists == 0:
                        await conn.execute(
                            f"SELECT create_elabel('{self.GRAPH_NAME}', '{label}');"
                        )
                        logger.info(f"✅ Created edge label: {label}")

            self._schema_initialized = True
            logger.info("✅ Structural graph schema initialized")

        except Exception as e:
            logger.error(f"Failed to initialize structural schema: {e}")
            # Don't raise - service can operate without graph

    async def add_structural_document(
        self,
        document_id: str,
        tenant_id: str,
        metadata: StructuralMetadata,
        weaviate_document_id: Optional[str] = None,
        connector_id: Optional[str] = None,
    ) -> bool:
        """
        Add a structural document node to the graph.

        This creates:
        1. The document node with structural metadata
        2. Folder nodes for the path hierarchy (if not exist)
        3. Contains edges from folder to document
        4. Sibling edges to other documents in same folder

        Args:
            document_id: Original document UUID
            tenant_id: Tenant identifier
            metadata: Extracted structural metadata
            weaviate_document_id: UUID in Weaviate document collection
            connector_id: Connector that indexed this

        Returns:
            True if successful, False otherwise
        """
        await self.initialize()

        if not self._age._pool:
            return False

        try:
            now = datetime.utcnow().isoformat()

            # Build document properties
            doc_props = {
                "document_id": document_id,
                "weaviate_id": weaviate_document_id or "",
                "connector_id": connector_id or "",

                # Structural classification
                "semantic_type": metadata.semantic_type.value if metadata.semantic_type else "",
                "domain": metadata.domain.value if metadata.domain else "",
                "importance": metadata.importance,

                # Location
                "folder_path": metadata.folder_path or "",
                "site_name": metadata.site_name or "",

                # Key properties (flattened)
                "prop_title": metadata.key_properties.get("title", ""),
                "prop_client": metadata.key_properties.get("client", ""),
                "prop_year": metadata.key_properties.get("year", ""),
                "prop_author": metadata.key_properties.get("author", ""),

                # Temporal
                "valid_from": now,
                "valid_to": "",  # Empty = currently valid
                "created_at": now,
                "modified_at": now,
            }

            async with self._age._get_connection() as conn:
                # Create or update document node
                node = StructuralNode(
                    node_id=document_id,
                    label=self.LABEL_DOCUMENT,
                    tenant_id=tenant_id,
                    properties=doc_props,
                )

                # MERGE to handle updates
                cypher = f"""
                    MERGE (d:{self.LABEL_DOCUMENT} {{document_id: '{document_id}', tenant_id: '{tenant_id}'}})
                    SET d = {node.to_cypher_props()}
                    RETURN id(d)
                """
                await self._age._execute_cypher(conn, cypher, [("id", "agtype")])

                # Create folder hierarchy
                if metadata.folder_path:
                    await self._ensure_folder_hierarchy(
                        conn, tenant_id, metadata.folder_path, document_id
                    )

                # Create sibling relationships
                await self._create_sibling_relationships(
                    conn, tenant_id, document_id, metadata.folder_path
                )

            logger.info(f"✅ Added structural document to graph: {document_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to add structural document {document_id}: {e}")
            return False

    async def _ensure_folder_hierarchy(
        self,
        conn,
        tenant_id: str,
        folder_path: str,
        document_id: str,
    ) -> None:
        """Create folder nodes and contains edges for the path hierarchy."""
        if not folder_path:
            return

        # Split path into parts
        parts = [p for p in folder_path.split("/") if p]
        if not parts:
            return

        now = datetime.utcnow().isoformat()
        parent_id = None

        for i, part in enumerate(parts):
            current_path = "/" + "/".join(parts[:i+1])
            folder_id = f"folder:{tenant_id}:{current_path}"

            # Create folder node
            folder_props = {
                "folder_id": folder_id,
                "name": part,
                "path": current_path,
                "depth": i + 1,
                "created_at": now,
            }

            node = StructuralNode(
                node_id=folder_id,
                label=self.LABEL_FOLDER,
                tenant_id=tenant_id,
                properties=folder_props,
            )

            cypher = f"""
                MERGE (f:{self.LABEL_FOLDER} {{folder_id: '{folder_id}', tenant_id: '{tenant_id}'}})
                ON CREATE SET f = {node.to_cypher_props()}
                RETURN id(f)
            """
            await self._age._execute_cypher(conn, cypher, [("id", "agtype")])

            # Create contains edge from parent folder
            if parent_id:
                cypher = f"""
                    MATCH (parent:{self.LABEL_FOLDER} {{folder_id: '{parent_id}', tenant_id: '{tenant_id}'}})
                    MATCH (child:{self.LABEL_FOLDER} {{folder_id: '{folder_id}', tenant_id: '{tenant_id}'}})
                    MERGE (parent)-[r:{self.EDGE_CONTAINS}]->(child)
                    RETURN id(r)
                """
                try:
                    await self._age._execute_cypher(conn, cypher, [("id", "agtype")])
                except Exception:
                    pass  # Edge may already exist

            parent_id = folder_id

        # Create contains edge from last folder to document
        if parent_id:
            cypher = f"""
                MATCH (f:{self.LABEL_FOLDER} {{folder_id: '{parent_id}', tenant_id: '{tenant_id}'}})
                MATCH (d:{self.LABEL_DOCUMENT} {{document_id: '{document_id}', tenant_id: '{tenant_id}'}})
                MERGE (f)-[r:{self.EDGE_CONTAINS}]->(d)
                RETURN id(r)
            """
            try:
                await self._age._execute_cypher(conn, cypher, [("id", "agtype")])
            except Exception:
                pass  # Edge may already exist

    async def _create_sibling_relationships(
        self,
        conn,
        tenant_id: str,
        document_id: str,
        folder_path: Optional[str],
    ) -> None:
        """Create sibling_of edges to other documents in the same folder."""
        if not folder_path:
            return

        folder_id = f"folder:{tenant_id}:{folder_path}"

        # Find other documents in same folder
        cypher = f"""
            MATCH (f:{self.LABEL_FOLDER} {{folder_id: '{folder_id}', tenant_id: '{tenant_id}'}})-[:{self.EDGE_CONTAINS}]->(sibling:{self.LABEL_DOCUMENT})
            WHERE sibling.document_id <> '{document_id}'
            RETURN sibling.document_id as sibling_id
        """

        try:
            results = await self._age._execute_cypher(conn, cypher, [("sibling_id", "agtype")])

            for row in results:
                sibling_id = row.get("sibling_id")
                if sibling_id:
                    # Remove quotes if present
                    if isinstance(sibling_id, str):
                        sibling_id = sibling_id.strip('"')

                    # Create bidirectional sibling relationship
                    cypher = f"""
                        MATCH (d1:{self.LABEL_DOCUMENT} {{document_id: '{document_id}', tenant_id: '{tenant_id}'}})
                        MATCH (d2:{self.LABEL_DOCUMENT} {{document_id: '{sibling_id}', tenant_id: '{tenant_id}'}})
                        MERGE (d1)-[r:{self.EDGE_SIBLING_OF}]->(d2)
                        RETURN id(r)
                    """
                    try:
                        await self._age._execute_cypher(conn, cypher, [("id", "agtype")])
                    except Exception:
                        pass  # Edge may already exist

        except Exception as e:
            logger.debug(f"Could not create sibling relationships: {e}")

    async def add_relationship(
        self,
        source_document_id: str,
        target_document_id: str,
        relationship_type: str,
        tenant_id: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Add a relationship between two structural documents.

        Args:
            source_document_id: Source document ID
            target_document_id: Target document ID
            relationship_type: Type of relationship (relates_to, version_of)
            tenant_id: Tenant identifier
            properties: Optional edge properties

        Returns:
            True if successful, False otherwise
        """
        await self.initialize()

        if not self._age._pool:
            return False

        # Validate relationship type
        valid_types = [self.EDGE_RELATES_TO, self.EDGE_VERSION_OF]
        if relationship_type not in valid_types:
            logger.warning(f"Invalid relationship type: {relationship_type}")
            return False

        try:
            async with self._age._get_connection() as conn:
                edge = StructuralEdge(
                    source_id=source_document_id,
                    target_id=target_document_id,
                    label=relationship_type,
                    tenant_id=tenant_id,
                    properties=properties or {},
                )

                cypher = f"""
                    MATCH (s:{self.LABEL_DOCUMENT} {{document_id: '{source_document_id}', tenant_id: '{tenant_id}'}})
                    MATCH (t:{self.LABEL_DOCUMENT} {{document_id: '{target_document_id}', tenant_id: '{tenant_id}'}})
                    MERGE (s)-[r:{relationship_type} {edge.to_cypher_props()}]->(t)
                    RETURN id(r)
                """
                await self._age._execute_cypher(conn, cypher, [("id", "agtype")])

            logger.info(f"✅ Created {relationship_type} relationship: {source_document_id} -> {target_document_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to create relationship: {e}")
            return False

    async def mark_document_removed(
        self,
        document_id: str,
        tenant_id: str,
    ) -> bool:
        """
        Mark a structural document as removed (set valid_to).

        This preserves the node for temporal queries while
        indicating it's no longer current.
        """
        await self.initialize()

        if not self._age._pool:
            return False

        try:
            now = datetime.utcnow().isoformat()

            async with self._age._get_connection() as conn:
                cypher = f"""
                    MATCH (d:{self.LABEL_DOCUMENT} {{document_id: '{document_id}', tenant_id: '{tenant_id}'}})
                    SET d.valid_to = '{now}'
                    SET d.modified_at = '{now}'
                    RETURN id(d)
                """
                await self._age._execute_cypher(conn, cypher, [("id", "agtype")])

            logger.info(f"✅ Marked document as removed: {document_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to mark document as removed: {e}")
            return False

    async def get_folder_contents(
        self,
        folder_path: str,
        tenant_id: str,
        include_subfolders: bool = False,
        valid_at: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get contents of a folder.

        Args:
            folder_path: Path to folder
            tenant_id: Tenant identifier
            include_subfolders: Whether to include nested content
            valid_at: Point in time for temporal query (default: now)

        Returns:
            List of documents and subfolders
        """
        await self.initialize()

        if not self._age._pool:
            return []

        try:
            folder_id = f"folder:{tenant_id}:{folder_path}"

            # Build temporal filter
            temporal_filter = ""
            if valid_at:
                timestamp = valid_at.isoformat()
                temporal_filter = f"""
                    AND d.valid_from <= '{timestamp}'
                    AND (d.valid_to = '' OR d.valid_to > '{timestamp}')
                """
            else:
                temporal_filter = "AND (d.valid_to = '' OR d.valid_to IS NULL)"

            # Query path
            path_pattern = f"-[:{self.EDGE_CONTAINS}]->" if not include_subfolders else f"-[:{self.EDGE_CONTAINS}*1..5]->"

            async with self._age._get_connection() as conn:
                cypher = f"""
                    MATCH (f:{self.LABEL_FOLDER} {{folder_id: '{folder_id}', tenant_id: '{tenant_id}'}})
                    {path_pattern}(d:{self.LABEL_DOCUMENT})
                    WHERE d.tenant_id = '{tenant_id}' {temporal_filter}
                    RETURN
                        d.document_id as document_id,
                        d.prop_title as title,
                        d.semantic_type as semantic_type,
                        d.domain as domain,
                        d.folder_path as folder_path,
                        d.importance as importance
                    ORDER BY d.importance DESC
                """
                results = await self._age._execute_cypher(
                    conn,
                    cypher,
                    [
                        ("document_id", "agtype"),
                        ("title", "agtype"),
                        ("semantic_type", "agtype"),
                        ("domain", "agtype"),
                        ("folder_path", "agtype"),
                        ("importance", "agtype"),
                    ],
                )

                # Clean up results (remove quotes from strings)
                cleaned = []
                for row in results:
                    cleaned_row = {}
                    for k, v in row.items():
                        if isinstance(v, str):
                            cleaned_row[k] = v.strip('"')
                        else:
                            cleaned_row[k] = v
                    cleaned.append(cleaned_row)

                return cleaned

        except Exception as e:
            logger.error(f"Failed to get folder contents: {e}")
            return []

    async def get_related_documents(
        self,
        document_id: str,
        tenant_id: str,
        relationship_type: Optional[str] = None,
        max_depth: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Get documents related to a given document.

        Args:
            document_id: Source document ID
            tenant_id: Tenant identifier
            relationship_type: Filter by relationship type
            max_depth: Maximum traversal depth

        Returns:
            List of related documents
        """
        await self.initialize()

        if not self._age._pool:
            return []

        try:
            # Build relationship filter
            if relationship_type:
                rel_pattern = f"-[r:{relationship_type}*1..{max_depth}]-"
            else:
                rel_pattern = f"-[r*1..{max_depth}]-"

            async with self._age._get_connection() as conn:
                cypher = f"""
                    MATCH (d:{self.LABEL_DOCUMENT} {{document_id: '{document_id}', tenant_id: '{tenant_id}'}})
                    {rel_pattern}(related:{self.LABEL_DOCUMENT})
                    WHERE related.document_id <> '{document_id}'
                      AND related.tenant_id = '{tenant_id}'
                      AND (related.valid_to = '' OR related.valid_to IS NULL)
                    RETURN DISTINCT
                        related.document_id as document_id,
                        related.prop_title as title,
                        related.semantic_type as semantic_type,
                        related.folder_path as folder_path
                    LIMIT 50
                """
                results = await self._age._execute_cypher(
                    conn,
                    cypher,
                    [
                        ("document_id", "agtype"),
                        ("title", "agtype"),
                        ("semantic_type", "agtype"),
                        ("folder_path", "agtype"),
                    ],
                )

                # Clean up results
                cleaned = []
                for row in results:
                    cleaned_row = {}
                    for k, v in row.items():
                        if isinstance(v, str):
                            cleaned_row[k] = v.strip('"')
                        else:
                            cleaned_row[k] = v
                    cleaned.append(cleaned_row)

                return cleaned

        except Exception as e:
            logger.error(f"Failed to get related documents: {e}")
            return []

    async def get_graph_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get statistics about the structural graph for a tenant."""
        await self.initialize()

        if not self._age._pool:
            return {"error": "Graph not available"}

        try:
            async with self._age._get_connection() as conn:
                # Count documents
                doc_cypher = f"""
                    MATCH (d:{self.LABEL_DOCUMENT} {{tenant_id: '{tenant_id}'}})
                    WHERE d.valid_to = '' OR d.valid_to IS NULL
                    RETURN count(d) as count
                """
                doc_result = await self._age._execute_cypher(conn, doc_cypher, [("count", "agtype")])
                doc_count = doc_result[0]["count"] if doc_result else 0

                # Count folders
                folder_cypher = f"""
                    MATCH (f:{self.LABEL_FOLDER} {{tenant_id: '{tenant_id}'}})
                    RETURN count(f) as count
                """
                folder_result = await self._age._execute_cypher(conn, folder_cypher, [("count", "agtype")])
                folder_count = folder_result[0]["count"] if folder_result else 0

                # Count by semantic type
                type_cypher = f"""
                    MATCH (d:{self.LABEL_DOCUMENT} {{tenant_id: '{tenant_id}'}})
                    WHERE d.valid_to = '' OR d.valid_to IS NULL
                    RETURN d.semantic_type as type, count(d) as count
                """
                type_results = await self._age._execute_cypher(
                    conn, type_cypher, [("type", "agtype"), ("count", "agtype")]
                )

                types_breakdown = {}
                for row in type_results:
                    t = row.get("type", "unknown")
                    if isinstance(t, str):
                        t = t.strip('"')
                    types_breakdown[t or "unknown"] = row.get("count", 0)

                return {
                    "tenant_id": tenant_id,
                    "total_documents": doc_count,
                    "total_folders": folder_count,
                    "types_breakdown": types_breakdown,
                    "graph_name": self.GRAPH_NAME,
                }

        except Exception as e:
            logger.error(f"Failed to get graph stats: {e}")
            return {"error": str(e)}


# Global singleton instance
structural_graph = StructuralGraphService()

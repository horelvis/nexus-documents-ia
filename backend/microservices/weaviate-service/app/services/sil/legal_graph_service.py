"""
Legal Knowledge Graph Service

Extends SIL with legal knowledge graph capabilities for Spanish legislation.

This service manages:
- Legal laws (BOE legislation)
- Articles within laws
- Jurisdictions
- Document-to-law relationships (governed_by)
- Cross-references between laws

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    Documents (SIL)                          │
    │              (structural_document nodes)                    │
    └────────────────────────┬────────────────────────────────────┘
                             │ governed_by
                             ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                    Legal Laws                               │
    │  (legal_law nodes - ET, RGPD, LGT, etc.)                   │
    └────────────────────────┬────────────────────────────────────┘
                             │ contains_article
                             ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                    Legal Articles                           │
    │  (legal_article nodes - Art. 34 ET, Art. 5 RGPD, etc.)     │
    └─────────────────────────────────────────────────────────────┘

Usage:
    from app.services.sil.legal_graph_service import legal_graph

    # Add a law
    await legal_graph.add_law(
        boe_id="BOE-A-2015-11430",
        title="Estatuto de los Trabajadores",
        domain="labor",
        tenant_id="global"  # Laws are shared across tenants
    )

    # Add an article
    await legal_graph.add_article(
        law_boe_id="BOE-A-2015-11430",
        article_number="34",
        title="Jornada",
        summary="Jornada máxima 40h/semana",
        tenant_id="global"
    )

    # Link document to applicable law
    await legal_graph.link_document_to_law(
        document_id="doc-123",
        law_boe_id="BOE-A-2015-11430",
        tenant_id="tenant-456"
    )

    # Find applicable laws for a document type
    laws = await legal_graph.get_applicable_laws(
        document_type="contract",
        domain="labor",
        tenant_id="tenant-456"
    )
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from .graph import (
    EdgeLabel,
    GraphEdge,
    GraphNode,
    GraphProvider,
    NodeLabel,
    get_graph_provider,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Legal Domain Models
# =============================================================================

class LegalDomain(str, Enum):
    """Legal domains for categorizing laws."""
    LABOR = "labor"
    FISCAL = "fiscal"
    PRIVACY = "privacy"
    CIVIL = "civil"
    MERCANTILE = "mercantile"
    ADMINISTRATIVE = "administrative"
    COMPLIANCE = "compliance"
    IP = "intellectual_property"
    COMMERCE = "commerce"
    REAL_ESTATE = "real_estate"
    EDUCATION = "education"
    GENERAL = "general"


class LawStatus(str, Enum):
    """Status of a law."""
    VIGENTE = "vigente"
    DEROGADA = "derogada"
    PARCIALMENTE_DEROGADA = "parcialmente_derogada"
    PENDIENTE = "pendiente"


@dataclass
class LegalLaw:
    """Represents a law in the knowledge graph."""
    boe_id: str                      # e.g., "BOE-A-2015-11430"
    title: str                       # Full title
    short_name: str                  # e.g., "ET", "RGPD", "LGT"
    domain: LegalDomain
    status: LawStatus = LawStatus.VIGENTE
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    eli_uri: Optional[str] = None    # European Legislation Identifier
    summary: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    weaviate_uuid: Optional[str] = None  # Link to PublicKnowledge document

    def to_node(self, tenant_id: str = "global") -> GraphNode:
        """Convert to GraphNode."""
        return GraphNode(
            node_id=self.boe_id,
            label=NodeLabel.LAW,
            tenant_id=tenant_id,
            properties={
                "boe_id": self.boe_id,
                "title": self.title,
                "short_name": self.short_name,
                "domain": self.domain.value,
                "status": self.status.value,
                "publication_date": self.publication_date or "",
                "effective_date": self.effective_date or "",
                "eli_uri": self.eli_uri or "",
                "summary": self.summary or "",
                "keywords": self.keywords,
                "weaviate_uuid": self.weaviate_uuid or "",
                "valid_from": datetime.utcnow().isoformat(),
                "valid_to": "",
            }
        )


@dataclass
class LegalArticle:
    """Represents an article within a law."""
    article_id: str                  # e.g., "BOE-A-2015-11430:art:34"
    law_boe_id: str                  # Parent law BOE ID
    article_number: str              # e.g., "34", "31bis", "DA 1ª"
    title: Optional[str] = None      # Article title
    summary: Optional[str] = None    # Brief summary (NOT full content)
    key_concepts: List[str] = field(default_factory=list)
    is_derogated: bool = False

    def to_node(self, tenant_id: str = "global") -> GraphNode:
        """Convert to GraphNode."""
        return GraphNode(
            node_id=self.article_id,
            label=NodeLabel.ARTICLE,
            tenant_id=tenant_id,
            properties={
                "article_id": self.article_id,
                "law_boe_id": self.law_boe_id,
                "article_number": self.article_number,
                "title": self.title or "",
                "summary": self.summary or "",
                "key_concepts": self.key_concepts,
                "is_derogated": self.is_derogated,
                "valid_from": datetime.utcnow().isoformat(),
                "valid_to": "" if not self.is_derogated else datetime.utcnow().isoformat(),
            }
        )


# =============================================================================
# Legal Knowledge Graph Service
# =============================================================================

class LegalGraphService:
    """
    Service for managing legal knowledge in the graph.

    This service extends SIL to include Spanish legislation,
    enabling queries like:
    - "What laws govern this contract?"
    - "What are the key articles for labor compliance?"
    - "Find documents that might be affected by law X"
    """

    # Global tenant ID for shared legal knowledge
    GLOBAL_TENANT = "global"

    def __init__(self):
        self._provider: Optional[GraphProvider] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the service and ensure schema exists."""
        if self._initialized:
            return

        try:
            self._provider = await get_graph_provider()

            # Ensure legal node and edge labels exist
            await self._provider.ensure_schema(
                node_labels=[
                    NodeLabel.LAW,
                    NodeLabel.ARTICLE,
                    NodeLabel.JURISDICTION,
                    NodeLabel.OBLIGATION,
                ],
                edge_labels=[
                    EdgeLabel.GOVERNED_BY,
                    EdgeLabel.REFERENCES,
                    EdgeLabel.CONTAINS_ARTICLE,
                    EdgeLabel.CREATES_OBLIGATION,
                    EdgeLabel.AMENDS,
                ],
            )

            self._initialized = True
            logger.info("✅ LegalGraphService initialized")

        except Exception as e:
            logger.error(f"Failed to initialize LegalGraphService: {e}")
            raise

    # =========================================================================
    # Law Operations
    # =========================================================================

    async def add_law(self, law: LegalLaw) -> bool:
        """
        Add a law to the knowledge graph.

        Laws are stored with tenant_id="global" since they are
        shared across all tenants.

        Args:
            law: The law to add

        Returns:
            True if successful
        """
        await self.initialize()

        try:
            node = law.to_node(self.GLOBAL_TENANT)
            result = await self._provider.add_node(node)

            if result:
                logger.info(f"✅ Added law: {law.short_name} ({law.boe_id})")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to add law {law.boe_id}: {e}")
            return False

    async def get_law(self, boe_id: str) -> Optional[Dict[str, Any]]:
        """Get a law by BOE ID."""
        await self.initialize()

        return await self._provider.get_node(
            node_id=boe_id,
            label=NodeLabel.LAW,
            tenant_id=self.GLOBAL_TENANT,
        )

    async def get_laws_by_domain(self, domain: LegalDomain) -> List[Dict[str, Any]]:
        """Get all laws for a specific domain."""
        await self.initialize()

        return await self._provider.find_nodes(
            label=NodeLabel.LAW,
            tenant_id=self.GLOBAL_TENANT,
            filters={"domain": domain.value},
            limit=100,
        )

    async def get_all_laws(self) -> List[Dict[str, Any]]:
        """Get all laws in the knowledge graph."""
        await self.initialize()

        return await self._provider.find_nodes(
            label=NodeLabel.LAW,
            tenant_id=self.GLOBAL_TENANT,
            limit=500,
        )

    async def update_law_weaviate_uuid(self, boe_id: str, weaviate_uuid: str) -> bool:
        """
        Update the weaviate_uuid for an existing law.

        This links the Apache AGE node to the corresponding
        PublicKnowledge document in Weaviate.

        Args:
            boe_id: BOE ID of the law
            weaviate_uuid: UUID of the document in Weaviate

        Returns:
            True if successful
        """
        await self.initialize()

        try:
            result = await self._provider.execute_query(
                f"""
                MATCH (law:legal_law {{boe_id: '{boe_id}', tenant_id: '{self.GLOBAL_TENANT}'}})
                SET law.weaviate_uuid = '{weaviate_uuid}'
                RETURN law.boe_id as boe_id
                """
            )

            if result and result.rows:
                logger.info(f"✅ Updated weaviate_uuid for {boe_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to update weaviate_uuid for {boe_id}: {e}")
            return False

    # =========================================================================
    # Article Operations
    # =========================================================================

    async def add_article(
        self,
        law_boe_id: str,
        article_number: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        key_concepts: Optional[List[str]] = None,
    ) -> bool:
        """
        Add an article to a law.

        Creates the article node and links it to the parent law.

        Args:
            law_boe_id: Parent law BOE ID
            article_number: Article number (e.g., "34", "31bis")
            title: Article title
            summary: Brief summary (not full text!)
            key_concepts: Key concepts covered

        Returns:
            True if successful
        """
        await self.initialize()

        try:
            article = LegalArticle(
                article_id=f"{law_boe_id}:art:{article_number}",
                law_boe_id=law_boe_id,
                article_number=article_number,
                title=title,
                summary=summary,
                key_concepts=key_concepts or [],
            )

            node = article.to_node(self.GLOBAL_TENANT)
            result = await self._provider.add_node(node)

            if not result:
                return False

            # Create edge from law to article
            edge = GraphEdge(
                source_id=law_boe_id,
                target_id=article.article_id,
                label=EdgeLabel.CONTAINS_ARTICLE,
                tenant_id=self.GLOBAL_TENANT,
            )

            await self._provider.add_edge(
                edge,
                source_label=NodeLabel.LAW,
                target_label=NodeLabel.ARTICLE,
            )

            logger.debug(f"Added article: {law_boe_id} Art. {article_number}")
            return True

        except Exception as e:
            logger.error(f"Failed to add article: {e}")
            return False

    async def get_articles_for_law(self, boe_id: str) -> List[Dict[str, Any]]:
        """Get all articles for a specific law."""
        await self.initialize()

        return await self._provider.find_nodes(
            label=NodeLabel.ARTICLE,
            tenant_id=self.GLOBAL_TENANT,
            filters={"law_boe_id": boe_id},
            limit=500,
            order_by="article_number",
        )

    async def get_article(
        self,
        law_boe_id: str,
        article_number: str,
    ) -> Optional[Dict[str, Any]]:
        """Get a specific article."""
        await self.initialize()

        article_id = f"{law_boe_id}:art:{article_number}"
        return await self._provider.get_node(
            node_id=article_id,
            label=NodeLabel.ARTICLE,
            tenant_id=self.GLOBAL_TENANT,
        )

    # =========================================================================
    # Document-Law Relationships
    # =========================================================================

    async def link_document_to_law(
        self,
        document_id: str,
        law_boe_id: str,
        tenant_id: str,
        relationship_type: str = "governed_by",
        articles: Optional[List[str]] = None,
    ) -> bool:
        """
        Link a document to an applicable law.

        Args:
            document_id: Document ID in the structural graph
            law_boe_id: BOE ID of the applicable law
            tenant_id: Tenant that owns the document
            relationship_type: Type of relationship
            articles: Specific articles that apply (optional)

        Returns:
            True if successful
        """
        await self.initialize()

        try:
            edge = GraphEdge(
                source_id=document_id,
                target_id=law_boe_id,
                label=EdgeLabel.GOVERNED_BY,
                tenant_id=tenant_id,
                properties={
                    "relationship_type": relationship_type,
                    "articles": articles or [],
                    "created_at": datetime.utcnow().isoformat(),
                },
            )

            success = await self._provider.add_edge(
                edge,
                source_label=NodeLabel.DOCUMENT,
                target_label=NodeLabel.LAW,
            )

            if success:
                logger.debug(f"Linked document {document_id} to law {law_boe_id}")

            return success

        except Exception as e:
            logger.error(f"Failed to link document to law: {e}")
            return False

    async def get_applicable_laws(
        self,
        document_id: str,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all laws applicable to a document.

        Args:
            document_id: Document ID
            tenant_id: Tenant ID

        Returns:
            List of applicable laws
        """
        await self.initialize()

        try:
            result = await self._provider.execute_query(
                f"""
                MATCH (d:structural_document {{node_id: '{document_id}', tenant_id: '{tenant_id}'}})
                      -[:governed_by]->(law:legal_law)
                RETURN law.boe_id as boe_id,
                       law.title as title,
                       law.short_name as short_name,
                       law.domain as domain
                """
            )

            return result.rows

        except Exception as e:
            logger.error(f"Failed to get applicable laws: {e}")
            return []

    async def get_documents_by_law(
        self,
        law_boe_id: str,
        tenant_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get all documents governed by a specific law.

        Args:
            law_boe_id: BOE ID of the law
            tenant_id: Tenant to search
            limit: Maximum results

        Returns:
            List of documents
        """
        await self.initialize()

        try:
            result = await self._provider.execute_query(
                f"""
                MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                      -[:governed_by]->(law:legal_law {{boe_id: '{law_boe_id}'}})
                WHERE d.valid_to = '' OR d.valid_to IS NULL
                RETURN d.document_id as document_id,
                       d.prop_title as title,
                       d.semantic_type as semantic_type,
                       d.folder_path as folder_path
                LIMIT {limit}
                """
            )

            return result.rows

        except Exception as e:
            logger.error(f"Failed to get documents by law: {e}")
            return []

    # =========================================================================
    # Cross-Reference Operations
    # =========================================================================

    async def add_law_reference(
        self,
        source_boe_id: str,
        target_boe_id: str,
        reference_type: str = "references",
    ) -> bool:
        """
        Add a reference between two laws.

        Args:
            source_boe_id: Source law BOE ID
            target_boe_id: Target law BOE ID
            reference_type: Type of reference

        Returns:
            True if successful
        """
        await self.initialize()

        try:
            edge = GraphEdge(
                source_id=source_boe_id,
                target_id=target_boe_id,
                label=EdgeLabel.REFERENCES,
                tenant_id=self.GLOBAL_TENANT,
                properties={"reference_type": reference_type},
            )

            return await self._provider.add_edge(
                edge,
                source_label=NodeLabel.LAW,
                target_label=NodeLabel.LAW,
            )

        except Exception as e:
            logger.error(f"Failed to add law reference: {e}")
            return False

    async def get_related_laws(
        self,
        boe_id: str,
        max_depth: int = 2,
    ) -> List[Dict[str, Any]]:
        """Get laws related to a specific law."""
        await self.initialize()

        try:
            return await self._provider.traverse(
                start_node_id=boe_id,
                start_label=NodeLabel.LAW,
                tenant_id=self.GLOBAL_TENANT,
                edge_labels=[EdgeLabel.REFERENCES, EdgeLabel.AMENDS],
                max_depth=max_depth,
            )

        except Exception as e:
            logger.error(f"Failed to get related laws: {e}")
            return []

    # =========================================================================
    # Query Operations
    # =========================================================================

    async def find_applicable_laws_for_domain(
        self,
        document_type: str,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find laws that might apply to a document type.

        This uses heuristics based on document type and domain
        to suggest applicable legislation.

        Args:
            document_type: Semantic type of document
            domain: Business domain (optional)

        Returns:
            List of potentially applicable laws
        """
        await self.initialize()

        # Map document types to legal domains
        type_to_domain = {
            "contract": [LegalDomain.LABOR, LegalDomain.CIVIL, LegalDomain.MERCANTILE],
            "invoice": [LegalDomain.FISCAL, LegalDomain.COMMERCE],
            "employee_file": [LegalDomain.LABOR, LegalDomain.PRIVACY],
            "policy": [LegalDomain.COMPLIANCE, LegalDomain.PRIVACY],
            "tax_return": [LegalDomain.FISCAL],
            "rental_agreement": [LegalDomain.REAL_ESTATE, LegalDomain.CIVIL],
        }

        # Determine domains to search
        domains = []
        if domain:
            try:
                domains.append(LegalDomain(domain))
            except ValueError:
                pass

        doc_type_lower = document_type.lower()
        if doc_type_lower in type_to_domain:
            domains.extend(type_to_domain[doc_type_lower])

        if not domains:
            domains = [LegalDomain.GENERAL]

        # Get laws for each domain
        laws = []
        seen_ids = set()

        for d in domains:
            domain_laws = await self.get_laws_by_domain(d)
            for law in domain_laws:
                law_id = law.get("boe_id")
                if law_id and law_id not in seen_ids:
                    laws.append(law)
                    seen_ids.add(law_id)

        return laws

    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the legal knowledge graph."""
        await self.initialize()

        try:
            laws_count = await self._provider.count_nodes(
                label=NodeLabel.LAW,
                tenant_id=self.GLOBAL_TENANT,
            )

            articles_count = await self._provider.count_nodes(
                label=NodeLabel.ARTICLE,
                tenant_id=self.GLOBAL_TENANT,
            )

            # Count by domain
            domains_breakdown = {}
            for domain in LegalDomain:
                count = await self._provider.count_nodes(
                    label=NodeLabel.LAW,
                    tenant_id=self.GLOBAL_TENANT,
                    filters={"domain": domain.value},
                )
                if count > 0:
                    domains_breakdown[domain.value] = count

            return {
                "total_laws": laws_count,
                "total_articles": articles_count,
                "laws_by_domain": domains_breakdown,
            }

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"error": str(e)}


# =============================================================================
# Global Instance
# =============================================================================

legal_graph = LegalGraphService()


# =============================================================================
# Convenience Functions
# =============================================================================

async def add_law(law: LegalLaw) -> bool:
    """Add a law to the knowledge graph."""
    return await legal_graph.add_law(law)


async def get_applicable_laws(document_id: str, tenant_id: str) -> List[Dict[str, Any]]:
    """Get laws applicable to a document."""
    return await legal_graph.get_applicable_laws(document_id, tenant_id)


async def link_document_to_law(
    document_id: str,
    law_boe_id: str,
    tenant_id: str,
) -> bool:
    """Link a document to an applicable law."""
    return await legal_graph.link_document_to_law(document_id, law_boe_id, tenant_id)

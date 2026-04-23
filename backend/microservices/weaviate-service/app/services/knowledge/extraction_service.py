"""
Knowledge Extraction Service for Emma AI.

Extracts, normalizes, and stores structured knowledge from documents.
Integrates with LangExtract for entity extraction and builds a knowledge graph.
"""

import logging
import time
import re
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import asyncio

from .schemas import (
    KnowledgeEntity,
    KnowledgeRelationship,
    KnowledgeExtractionResult,
    KnowledgeExtractionConfig,
    EntityType,
    RelationshipType,
)

logger = logging.getLogger(__name__)

# Singleton instance
_knowledge_service: Optional["KnowledgeExtractionService"] = None


def get_knowledge_service() -> "KnowledgeExtractionService":
    """Get or create the singleton KnowledgeExtractionService instance."""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeExtractionService()
    return _knowledge_service


class KnowledgeExtractionService:
    """
    Service for extracting and storing knowledge from documents.

    Processes entities from LangExtract, normalizes them, detects relationships,
    and stores the knowledge graph in PostgreSQL and Weaviate.
    """

    def __init__(self, config: Optional[KnowledgeExtractionConfig] = None):
        self.config = config or KnowledgeExtractionConfig()
        self._weaviate_service = None
        self._initialized = False

        # Entity type mapping from LangExtract class names
        self._type_mapping = {
            # Spanish document types
            "persona": EntityType.PERSON,
            "person": EntityType.PERSON,
            "empleado": EntityType.PERSON,
            "trabajador": EntityType.PERSON,
            "representante": EntityType.PERSON,
            "firmante": EntityType.PERSON,
            "empresa": EntityType.ORGANIZATION,
            "organization": EntityType.ORGANIZATION,
            "organizacion": EntityType.ORGANIZATION,
            "compania": EntityType.ORGANIZATION,
            "sociedad": EntityType.ORGANIZATION,
            "entidad": EntityType.ORGANIZATION,
            "clausula": EntityType.CLAUSE,
            "clause": EntityType.CLAUSE,
            "articulo": EntityType.CLAUSE,
            "seccion": EntityType.CLAUSE,
            "termino": EntityType.TERM,
            "term": EntityType.TERM,
            "definicion": EntityType.TERM,
            "fecha": EntityType.DATE,
            "date": EntityType.DATE,
            "periodo": EntityType.DATE,
            "vigencia": EntityType.DATE,
            "importe": EntityType.AMOUNT,
            "amount": EntityType.AMOUNT,
            "cantidad": EntityType.AMOUNT,
            "monto": EntityType.AMOUNT,
            "salario": EntityType.AMOUNT,
            "precio": EntityType.AMOUNT,
            "ubicacion": EntityType.LOCATION,
            "location": EntityType.LOCATION,
            "direccion": EntityType.LOCATION,
            "domicilio": EntityType.LOCATION,
            "obligacion": EntityType.OBLIGATION,
            "obligation": EntityType.OBLIGATION,
            "deber": EntityType.OBLIGATION,
            "derecho": EntityType.RIGHT,
            "right": EntityType.RIGHT,
            "referencia": EntityType.REFERENCE,
            "reference": EntityType.REFERENCE,
            "ley": EntityType.REFERENCE,
            "normativa": EntityType.REFERENCE,
        }

    async def initialize(self) -> None:
        """Initialize the service and its dependencies."""
        if self._initialized:
            return

        try:
            # Import here to avoid circular dependencies
            from app.services.weaviate_service import WeaviateService

            self._weaviate_service = WeaviateService()
            await self._weaviate_service.initialize()

            self._initialized = True
            logger.info("✅ KnowledgeExtractionService initialized")

        except Exception as e:
            logger.error(f"❌ Failed to initialize KnowledgeExtractionService: {e}")
            raise

    async def extract_from_document(
        self,
        document_id: str,
        extracted_entities: List[Dict[str, Any]],
        content: str,
        document_type: Optional[str] = None,
    ) -> KnowledgeExtractionResult:
        """
        Extract and store knowledge from a document.

        This is the main entry point, called from IndexingPipeline after LangExtract.

        Args:
            document_id: PostgreSQL document UUID
            extracted_entities: Raw entities from LangExtract
            content: Full document text
            document_type: Type of document (contract, invoice, etc.)

        Returns:
            KnowledgeExtractionResult with extracted entities and relationships
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        result = KnowledgeExtractionResult(
            document_id=document_id,
        )

        try:
            logger.info(f"🧠 Extracting knowledge from document {document_id}")
            logger.info(f"📊 Input: {len(extracted_entities)} raw entities from LangExtract")

            # Step 1: Normalize entities
            normalized_entities = await self._normalize_entities(
                raw_entities=extracted_entities,
                content=content,
                document_type=document_type
            )
            logger.info(f"📊 Normalized: {len(normalized_entities)} entities")

            # Step 2: Detect relationships
            relationships = await self._detect_relationships(
                entities=normalized_entities,
                content=content
            )
            logger.info(f"📊 Detected: {len(relationships)} relationships")

            # Step 4: Store in PostgreSQL and Weaviate
            stored_entities = await self._store_entities(
                entities=normalized_entities,
                document_id=document_id,
            )

            stored_relationships = await self._store_relationships(
                relationships=relationships,
                document_id=document_id,
                entity_map=stored_entities,
            )

            # Update result
            result.entities = normalized_entities
            result.relationships = relationships
            result.entities_count = len(normalized_entities)
            result.relationships_count = len(relationships)
            result.processing_time_ms = int((time.time() - start_time) * 1000)
            result.success = True

            logger.info(
                f"✅ Knowledge extraction complete: "
                f"{result.entities_count} entities, "
                f"{result.relationships_count} relationships "
                f"in {result.processing_time_ms}ms"
            )

        except Exception as e:
            logger.error(f"❌ Knowledge extraction failed: {e}")
            result.success = False
            result.errors.append(str(e))

        return result

    async def _normalize_entities(
        self,
        raw_entities: List[Dict[str, Any]],
        content: str,
        document_type: Optional[str] = None
    ) -> List[KnowledgeEntity]:
        """
        Normalize raw entities from LangExtract.

        - Classifies entity types
        - Extracts context text
        - Deduplicates similar entities
        """
        normalized = []
        seen_values = set()

        for raw in raw_entities:
            try:
                # Get entity value (try different field names)
                entity_value = (
                    raw.get("text") or
                    raw.get("value") or
                    raw.get("entity_value") or
                    raw.get("name") or
                    ""
                ).strip()

                if not entity_value or len(entity_value) < 2:
                    continue

                # Deduplication
                normalized_value = entity_value.lower().strip()
                if normalized_value in seen_values:
                    continue
                seen_values.add(normalized_value)

                # Classify entity type
                raw_type = (
                    raw.get("class_name") or
                    raw.get("type") or
                    raw.get("entity_type") or
                    "term"
                ).lower()
                entity_type = self._type_mapping.get(raw_type, EntityType.CONCEPT)

                # Extract context from content
                context_text = self._extract_context(
                    entity_value=entity_value,
                    content=content,
                    chars_before=self.config.normalization.context_chars_before,
                    chars_after=self.config.normalization.context_chars_after
                )

                # Build entity
                entity = KnowledgeEntity(
                    entity_type=entity_type,
                    entity_value=entity_value,
                    entity_label=raw.get("label") or entity_value,
                    context_text=context_text,
                    extraction_confidence=raw.get("confidence", 0.8),
                    attributes=raw.get("attributes", {}),
                    char_start=raw.get("source_indices", [None])[0] if raw.get("source_indices") else None
                )

                normalized.append(entity)

            except Exception as e:
                logger.warning(f"⚠️ Failed to normalize entity: {e}")
                continue

        # Limit entities
        if len(normalized) > self.config.max_entities_per_document:
            logger.warning(
                f"⚠️ Truncating entities from {len(normalized)} "
                f"to {self.config.max_entities_per_document}"
            )
            normalized = normalized[:self.config.max_entities_per_document]

        return normalized

    def _extract_context(
        self,
        entity_value: str,
        content: str,
        chars_before: int = 100,
        chars_after: int = 100
    ) -> str:
        """Extract surrounding context for an entity."""
        try:
            # Find entity in content (case insensitive)
            pattern = re.escape(entity_value)
            match = re.search(pattern, content, re.IGNORECASE)

            if match:
                start = max(0, match.start() - chars_before)
                end = min(len(content), match.end() + chars_after)
                context = content[start:end].strip()
                # Clean up whitespace
                context = re.sub(r'\s+', ' ', context)
                return context

            # Fallback: use entity value as context
            return f"{entity_value}"

        except Exception:
            return entity_value

    async def _detect_relationships(
        self,
        entities: List[KnowledgeEntity],
        content: str
    ) -> List[KnowledgeRelationship]:
        """
        Detect relationships between entities.

        Uses co-occurrence analysis to find entities that appear near each other.
        """
        relationships = []

        if not self.config.relationship_detection.use_cooccurrence:
            return relationships

        # Build entity positions
        entity_positions = []
        content_lower = content.lower()

        for entity in entities:
            pattern = re.escape(entity.entity_value.lower())
            for match in re.finditer(pattern, content_lower):
                entity_positions.append({
                    "entity": entity,
                    "start": match.start(),
                    "end": match.end()
                })

        # Sort by position
        entity_positions.sort(key=lambda x: x["start"])

        # Find co-occurring entities (within 200 chars)
        window_size = 200
        seen_pairs = set()

        for i, pos1 in enumerate(entity_positions):
            for j, pos2 in enumerate(entity_positions[i + 1:], i + 1):
                # Check distance
                distance = pos2["start"] - pos1["end"]
                if distance > window_size:
                    break
                if distance < 0:
                    continue

                # Skip same entity
                if pos1["entity"].entity_value == pos2["entity"].entity_value:
                    continue

                # Create unique pair key
                pair_key = tuple(sorted([
                    pos1["entity"].entity_value,
                    pos2["entity"].entity_value
                ]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Determine relationship type based on entity types
                rel_type = self._infer_relationship_type(
                    pos1["entity"].entity_type,
                    pos2["entity"].entity_type
                )

                # Calculate strength based on distance
                strength = max(0.3, 1.0 - (distance / window_size))

                # Extract context snippet
                snippet_start = pos1["start"]
                snippet_end = pos2["end"]
                context = content[snippet_start:snippet_end][:200]

                relationship = KnowledgeRelationship(
                    source_entity_value=pos1["entity"].entity_value,
                    target_entity_value=pos2["entity"].entity_value,
                    relationship_type=rel_type,
                    relationship_strength=strength,
                    context_snippet=context
                )
                relationships.append(relationship)

        # Limit relationships
        if len(relationships) > self.config.max_relationships_per_document:
            # Keep strongest relationships
            relationships.sort(key=lambda r: r.relationship_strength, reverse=True)
            relationships = relationships[:self.config.max_relationships_per_document]

        return relationships

    def _infer_relationship_type(
        self,
        source_type: EntityType,
        target_type: EntityType
    ) -> RelationshipType:
        """Infer relationship type based on entity types."""
        # Person/Organization relationships
        if source_type == EntityType.PERSON and target_type == EntityType.ORGANIZATION:
            return RelationshipType.BELONGS_TO
        if source_type == EntityType.ORGANIZATION and target_type == EntityType.PERSON:
            return RelationshipType.INVOLVES

        # Clause relationships
        if source_type == EntityType.CLAUSE or target_type == EntityType.CLAUSE:
            return RelationshipType.DEFINES

        # Reference relationships
        if source_type == EntityType.REFERENCE or target_type == EntityType.REFERENCE:
            return RelationshipType.REFERENCES

        # Default
        return RelationshipType.RELATES_TO

    async def _store_entities(
        self,
        entities: List[KnowledgeEntity],
        document_id: str,
    ) -> Dict[str, str]:
        """
        Store entities in Weaviate and knowledge-tree-service graph.

        Entities are persisted in two places:
        1. Weaviate _knowledge collection (for semantic entity search)
        2. knowledge-tree-service sector graph (for graph traversal via HTTP)

        Returns a mapping of entity_value -> entity_id for relationship storage.
        """
        entity_map = {}

        if not self.config.store_in_weaviate:
            return entity_map

        for entity in entities:
            try:
                import uuid
                entity_id = str(uuid.uuid4())

                # Store in Weaviate _knowledge collection
                await self._weaviate_service.add_knowledge_entity(
                    entity_id=entity_id,
                    entity_type=entity.entity_type,
                    entity_value=entity.entity_value,
                    context_text=entity.context_text,
                    entity_label=entity.entity_label,
                    source_document_id=document_id,
                    confidence=entity.extraction_confidence,
                    attributes=entity.attributes,
                )

                entity_map[entity.entity_value] = entity_id
                logger.debug(f"Stored entity {entity_id}: {entity.entity_value}")

            except Exception as e:
                logger.warning(f"⚠️ Failed to store entity {entity.entity_value}: {e}")
                continue

        # Store in knowledge-tree-service via TrustGraph triple extraction.
        # Send raw chunk texts to KTS and let the 4 LLM extractors build the graph.
        # This replaces the old entity-by-entity store_entities() approach.
        if entity_map:
            try:
                from app.clients.knowledge_tree_client import knowledge_tree_legal_client

                # Build chunk list from entity context texts as a proxy for chunks
                # (the full chunk list is not available here — use context windows)
                chunk_texts = list({
                    e.context_text for e in entities if e.context_text
                })
                # Fall back to a single content window if no context texts
                if not chunk_texts:
                    chunk_texts = [content[:4000]] if content else []

                if chunk_texts:
                    kt_result = await knowledge_tree_legal_client.extract_triples(
                        document_id=document_id,
                        chunks=chunk_texts,
                    )
                    triples_extracted = kt_result.get("triples_extracted", 0)
                    logger.info(
                        f"📊 TrustGraph extraction queued: "
                        f"{triples_extracted} triples for document {document_id}"
                    )

            except Exception as e:
                # Pipeline-critical path: KTS /extract/triples failure leaves
                # FalkorDB empty even though Weaviate indexing succeeded. We
                # lived this bug on 2026-04-23 (FalkorDB had 0 nodes for
                # hours while the sync reported 'indexed'). Elevate to ERROR
                # so it surfaces in production log aggregators, include
                # document_id for triage.
                logger.error(
                    "❌ TrustGraph extraction failed for document %s "
                    "(Weaviate stored but graph will be incomplete): %s",
                    document_id, e,
                )

        logger.info(f"📦 Stored {len(entity_map)} entities in Weaviate")
        return entity_map

    async def _store_relationships(
        self,
        relationships: List[KnowledgeRelationship],
        document_id: str,
        entity_map: Dict[str, str],
    ) -> int:
        """
        Store relationships in the sector graph via knowledge-tree-service.

        Creates edges between typed entity nodes (Persona, Organizacion, etc.)
        that were persisted by _store_entities().
        """
        if not relationships:
            return 0

        # Filter to only relationships where both entities were stored
        valid_rels = [
            {
                "source": rel.source_entity_value,
                "target": rel.target_entity_value,
                "type": rel.relationship_type.value if hasattr(rel.relationship_type, 'value') else str(rel.relationship_type),
                "strength": rel.relationship_strength,
            }
            for rel in relationships
            if entity_map.get(rel.source_entity_value) and entity_map.get(rel.target_entity_value)
        ]

        if not valid_rels:
            return 0

        try:
            from app.clients.knowledge_tree_client import knowledge_tree_legal_client

            result = await knowledge_tree_legal_client.store_entities(
                document_id=document_id,
                entities=[],  # No new entities, just relationships
                relationships=valid_rels,
            )

            stored = result.get("relationships_stored", 0)
            logger.info(f"📦 Stored {stored} relationships in sector graph")
            return stored

        except Exception as e:
            # TODO(legacy-kts-endpoint): knowledge_tree_legal_client.store_entities
            # POSTs /tree/entities/store which returns 404 in the current KTS
            # (removed alongside the Phase-3 refactor). Every call through this
            # path silently drops relationships. Either wire to a live endpoint
            # or drop this whole method once callers migrate to
            # /extract/triples. Until then, elevate to ERROR so the failure
            # is visible in logs instead of hidden by WARNING.
            logger.error(
                "❌ Failed to store relationships for document %s via legacy "
                "KTS endpoint (likely 404 — endpoint removed): %s",
                document_id, e,
            )
            return 0

    async def delete_document_knowledge(
        self,
        document_id: str,
    ) -> int:
        """Delete all knowledge entities from a document."""
        if not self._initialized:
            await self.initialize()

        try:
            deleted = await self._weaviate_service.delete_knowledge_by_document(
                document_id=document_id,
            )
            logger.info(f"🗑️ Deleted {deleted} knowledge entities for document {document_id}")
            return deleted

        except Exception as e:
            logger.error(f"❌ Failed to delete knowledge for document {document_id}: {e}")
            return 0

    async def search_knowledge(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        domain: Optional[str] = None,
        limit: int = 10,
        user_id: Optional[str] = None,
        user_roles: Optional[List[str]] = None,
        is_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search knowledge entities semantically."""
        if not self._initialized:
            await self.initialize()

        return await self._weaviate_service.search_knowledge_entities(
            query=query,
            user_roles=user_roles or [],
            entity_types=entity_types,
            domain=domain,
            limit=limit,
            is_admin=is_admin,
        )

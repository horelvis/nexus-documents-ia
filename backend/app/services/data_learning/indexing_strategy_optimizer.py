"""
Indexing Strategy Optimizer

Generates optimal indexing strategies based on learned knowledge:
- Chunking strategy based on document type (legal → sections, general → semantic)
- Embedding field selection and weights
- Entity extraction configuration
- Knowledge Graph integration settings

Strategies are applied during document indexing to optimize retrieval.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Connector,
    ConnectorContentModel,
    ConnectorIndexingStrategy,
    DataLearningJob,
)
from app.schemas.data_learning import (
    ChunkingType,
    ChunkingConfig,
    ConnectorIndexingStrategyCreate,
    ConnectorIndexingStrategyUpdate,
)

logger = logging.getLogger(__name__)


# Default chunking configurations by type
DEFAULT_CHUNKING_CONFIGS = {
    ChunkingType.SEMANTIC: {
        "target_chunk_size": 512,
        "overlap": 50,
    },
    ChunkingType.FIXED_SIZE: {
        "target_chunk_size": 1000,
        "overlap": 100,
    },
    ChunkingType.LEGAL_SECTIONS: {
        "target_chunk_size": 1000,
        "overlap": 100,
        "section_markers": [
            "CLÁUSULA", "CLAUSULA", "ARTÍCULO", "ARTICULO",
            "SECCIÓN", "SECCION", "CAPÍTULO", "CAPITULO",
            "PRIMERO", "SEGUNDO", "TERCERO",
        ],
    },
    ChunkingType.MARKDOWN_HEADERS: {
        "target_chunk_size": 800,
        "overlap": 50,
        "header_levels": [1, 2, 3],
    },
    ChunkingType.PAGE_BASED: {
        "pages_per_chunk": 1,
        "overlap": 0,
    },
}

# Document type to chunking strategy mapping
TYPE_CHUNKING_MAPPING = {
    "contract": ChunkingType.LEGAL_SECTIONS,
    "legal": ChunkingType.LEGAL_SECTIONS,
    "agreement": ChunkingType.LEGAL_SECTIONS,
    "contrato": ChunkingType.LEGAL_SECTIONS,
    "expediente": ChunkingType.LEGAL_SECTIONS,
    "invoice": ChunkingType.PAGE_BASED,
    "factura": ChunkingType.PAGE_BASED,
    "receipt": ChunkingType.PAGE_BASED,
    "memo": ChunkingType.SEMANTIC,
    "email": ChunkingType.SEMANTIC,
    "report": ChunkingType.MARKDOWN_HEADERS,
    "informe": ChunkingType.MARKDOWN_HEADERS,
    "manual": ChunkingType.MARKDOWN_HEADERS,
    "documentation": ChunkingType.MARKDOWN_HEADERS,
}


class IndexingStrategyOptimizer:
    """
    Service for generating and managing indexing strategies.

    Uses learned content model and type semantics to determine
    optimal indexing configuration for each document type.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the optimizer.

        Args:
            db: Database session
        """
        self.db = db

    async def generate_indexing_strategies(
        self,
        connector_id: UUID,
        update_job: Optional[DataLearningJob] = None,
    ) -> List[ConnectorIndexingStrategy]:
        """
        Generate indexing strategies for a connector.

        Creates strategies based on:
        1. Discovered content types and their semantics
        2. Common document types (contract, invoice, etc.)
        3. MIME types

        Args:
            connector_id: UUID of the connector
            update_job: Optional job to update progress

        Returns:
            List of generated strategies
        """
        # Fetch connector
        result = await self.db.execute(
            select(Connector).where(Connector.id == connector_id)
        )
        connector = result.scalar_one_or_none()
        if not connector:
            raise ValueError(f"Connector not found: {connector_id}")

        # Update job progress
        if update_job:
            update_job.current_phase = "Loading content model"
            update_job.progress_percent = 10
            await self.db.commit()

        # Get content model
        cm_result = await self.db.execute(
            select(ConnectorContentModel)
            .where(ConnectorContentModel.connector_id == connector_id)
        )
        content_model = cm_result.scalar_one_or_none()

        # Update job progress
        if update_job:
            update_job.current_phase = "Generating strategies"
            update_job.progress_percent = 30
            await self.db.commit()

        strategies = []

        # 1. Create default strategy for all documents
        default_strategy = await self._create_or_update_strategy(
            connector_id=connector_id,
            document_type=None,
            mime_type_pattern=None,
            chunking_type=ChunkingType.SEMANTIC,
            priority=0,
        )
        strategies.append(default_strategy)

        # 2. Create strategies based on content types
        if content_model and content_model.type_semantics:
            for type_name, semantics in content_model.type_semantics.items():
                semantic_type = semantics.get("semantic_type", "")
                domain = semantics.get("domain", "general")
                suggested_chunking = semantics.get("chunking_strategy")

                # Determine chunking type
                if suggested_chunking:
                    chunking = ChunkingType(suggested_chunking)
                else:
                    chunking = self._infer_chunking_type(semantic_type, domain)

                strategy = await self._create_or_update_strategy(
                    connector_id=connector_id,
                    document_type=type_name,
                    mime_type_pattern=None,
                    chunking_type=chunking,
                    priority=10,
                    extract_entities=domain in ["legal", "hr", "finance"],
                )
                strategies.append(strategy)

        # 3. Create MIME type specific strategies
        mime_strategies = [
            # PDF documents
            ("application/pdf", ChunkingType.PAGE_BASED, 5),
            # Office documents
            ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             ChunkingType.SEMANTIC, 5),
            ("application/msword", ChunkingType.SEMANTIC, 5),
            # Markdown
            ("text/markdown", ChunkingType.MARKDOWN_HEADERS, 5),
            # Plain text
            ("text/plain", ChunkingType.FIXED_SIZE, 5),
        ]

        for mime_type, chunking, priority in mime_strategies:
            strategy = await self._create_or_update_strategy(
                connector_id=connector_id,
                document_type=None,
                mime_type_pattern=mime_type,
                chunking_type=chunking,
                priority=priority,
            )
            strategies.append(strategy)

        await self.db.commit()

        # Update job progress
        if update_job:
            update_job.current_phase = "Strategy optimization completed"
            update_job.progress_percent = 100
            await self.db.commit()

        logger.info(
            f"Strategy optimization completed for connector {connector_id}: "
            f"{len(strategies)} strategies"
        )

        return strategies

    async def _create_or_update_strategy(
        self,
        connector_id: UUID,
        document_type: Optional[str],
        mime_type_pattern: Optional[str],
        chunking_type: ChunkingType,
        priority: int,
        extract_entities: bool = True,
        embedding_fields: Optional[List[str]] = None,
    ) -> ConnectorIndexingStrategy:
        """Create or update an indexing strategy."""
        # Check if exists
        query = select(ConnectorIndexingStrategy).where(
            ConnectorIndexingStrategy.connector_id == connector_id
        )
        if document_type:
            query = query.where(ConnectorIndexingStrategy.document_type == document_type)
        else:
            query = query.where(ConnectorIndexingStrategy.document_type.is_(None))

        if mime_type_pattern:
            query = query.where(ConnectorIndexingStrategy.mime_type_pattern == mime_type_pattern)
        else:
            query = query.where(ConnectorIndexingStrategy.mime_type_pattern.is_(None))

        result = await self.db.execute(query)
        strategy = result.scalar_one_or_none()

        # Get default config
        chunking_config = DEFAULT_CHUNKING_CONFIGS.get(
            chunking_type,
            DEFAULT_CHUNKING_CONFIGS[ChunkingType.SEMANTIC]
        )

        # Default embedding fields
        if embedding_fields is None:
            embedding_fields = ["content", "title"]

        if strategy:
            # Update existing
            strategy.chunking_type = chunking_type.value
            strategy.chunking_config = chunking_config
            strategy.priority = priority
            strategy.extract_entities = extract_entities
            strategy.embedding_fields = embedding_fields
        else:
            # Create new
            strategy = ConnectorIndexingStrategy(
                connector_id=connector_id,
                document_type=document_type,
                mime_type_pattern=mime_type_pattern,
                chunking_type=chunking_type.value,
                chunking_config=chunking_config,
                embedding_fields=embedding_fields,
                extract_entities=extract_entities,
                entity_types=["PERSON", "ORG", "DATE", "MONEY"] if extract_entities else None,
                extract_to_knowledge_graph=True,
                priority=priority,
                is_active=True,
            )
            self.db.add(strategy)

        return strategy

    def _infer_chunking_type(
        self,
        semantic_type: str,
        domain: str,
    ) -> ChunkingType:
        """
        Infer chunking type from semantic type and domain.

        Args:
            semantic_type: Normalized semantic type
            domain: Document domain

        Returns:
            Appropriate chunking type
        """
        # Check semantic type mapping
        lower_type = semantic_type.lower()
        for key, chunking in TYPE_CHUNKING_MAPPING.items():
            if key in lower_type:
                return chunking

        # Check domain
        if domain == "legal":
            return ChunkingType.LEGAL_SECTIONS
        elif domain == "technical":
            return ChunkingType.MARKDOWN_HEADERS

        return ChunkingType.SEMANTIC

    async def get_strategy_for_document(
        self,
        connector_id: UUID,
        document_type: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> Optional[ConnectorIndexingStrategy]:
        """
        Get the best matching strategy for a document.

        Matches by priority order:
        1. Exact document_type match
        2. MIME type match
        3. Default strategy (no type/mime)

        Args:
            connector_id: UUID of the connector
            document_type: Document type (e.g., gdapm:expediente)
            mime_type: MIME type (e.g., application/pdf)

        Returns:
            Best matching strategy or None
        """
        # Get all active strategies, ordered by priority descending
        result = await self.db.execute(
            select(ConnectorIndexingStrategy)
            .where(ConnectorIndexingStrategy.connector_id == connector_id)
            .where(ConnectorIndexingStrategy.is_active == True)
            .order_by(ConnectorIndexingStrategy.priority.desc())
        )
        strategies = list(result.scalars().all())

        # Find best match
        for strategy in strategies:
            # Check document type match
            if strategy.document_type and document_type:
                if strategy.document_type == document_type:
                    return strategy

            # Check MIME type match
            if strategy.mime_type_pattern and mime_type:
                if mime_type.startswith(strategy.mime_type_pattern.rstrip("*")):
                    return strategy

        # Return default strategy (no type/mime specified)
        for strategy in strategies:
            if not strategy.document_type and not strategy.mime_type_pattern:
                return strategy

        return None

    async def get_strategies(
        self,
        connector_id: UUID,
    ) -> List[ConnectorIndexingStrategy]:
        """Get all strategies for a connector."""
        result = await self.db.execute(
            select(ConnectorIndexingStrategy)
            .where(ConnectorIndexingStrategy.connector_id == connector_id)
            .order_by(ConnectorIndexingStrategy.priority.desc())
        )
        return list(result.scalars().all())

    async def update_strategy(
        self,
        strategy_id: UUID,
        update: ConnectorIndexingStrategyUpdate,
    ) -> Optional[ConnectorIndexingStrategy]:
        """Update an indexing strategy."""
        result = await self.db.execute(
            select(ConnectorIndexingStrategy)
            .where(ConnectorIndexingStrategy.id == strategy_id)
        )
        strategy = result.scalar_one_or_none()

        if not strategy:
            return None

        update_data = update.model_dump(exclude_unset=True)

        # Handle nested chunking_config
        if "chunking_config" in update_data and update_data["chunking_config"]:
            update_data["chunking_config"] = update_data["chunking_config"].model_dump()

        for key, value in update_data.items():
            setattr(strategy, key, value)

        await self.db.commit()
        await self.db.refresh(strategy)

        return strategy

    async def create_strategy(
        self,
        connector_id: UUID,
        create: ConnectorIndexingStrategyCreate,
    ) -> ConnectorIndexingStrategy:
        """Create a new indexing strategy."""
        result = await self.db.execute(
            select(Connector).where(Connector.id == connector_id)
        )
        connector = result.scalar_one_or_none()
        if not connector:
            raise ValueError(f"Connector not found: {connector_id}")

        strategy = ConnectorIndexingStrategy(
            connector_id=connector_id,
            document_type=create.document_type,
            mime_type_pattern=create.mime_type_pattern,
            chunking_type=create.chunking_type.value,
            chunking_config=create.chunking_config.model_dump() if create.chunking_config else {},
            embedding_fields=create.embedding_fields,
            embedding_weights=create.embedding_weights,
            extract_entities=create.extract_entities,
            entity_types=create.entity_types,
            extract_to_knowledge_graph=create.extract_to_knowledge_graph,
            priority=create.priority,
            is_active=create.is_active,
        )
        self.db.add(strategy)
        await self.db.commit()
        await self.db.refresh(strategy)

        return strategy

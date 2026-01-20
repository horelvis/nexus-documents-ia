"""
Learning Orchestrator

Orchestrates the complete data learning workflow:
1. Content model discovery
2. Folder structure analysis
3. Property mapping generation
4. Relationship type learning
5. Indexing strategy optimization

Can run full learning or individual phases.
Manages learning job tracking and progress updates.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Connector,
    DataLearningJob,
    DataLearningJobStatus,
    DataLearningJobType,
)
from app.schemas.data_learning import (
    DataLearningJobCreate,
    DataLearningJobResponse,
    TriggerLearningRequest,
    TriggerLearningResponse,
    ConnectorLearningStatusResponse,
    ContentModelSummary,
)

from .content_model_discovery import ContentModelDiscoveryService
from .folder_structure_analyzer import FolderStructureAnalyzer
from .metadata_intelligence import MetadataIntelligenceService
from .relationship_learner import RelationshipLearner
from .indexing_strategy_optimizer import IndexingStrategyOptimizer

logger = logging.getLogger(__name__)


class LearningOrchestrator:
    """
    Main orchestrator for the Data Learning System.

    Coordinates all learning services and manages job lifecycle.
    """

    def __init__(self, db: AsyncSession, llm_client=None):
        """
        Initialize the orchestrator.

        Args:
            db: Database session
            llm_client: Optional LLM client for semantic enrichment
        """
        self.db = db
        self.llm_client = llm_client

        # Initialize services
        self.content_model_service = ContentModelDiscoveryService(db, llm_client)
        self.folder_analyzer = FolderStructureAnalyzer(db)
        self.metadata_service = MetadataIntelligenceService(db)
        self.relationship_learner = RelationshipLearner(db)
        self.strategy_optimizer = IndexingStrategyOptimizer(db)

    async def trigger_learning(
        self,
        connector_id: UUID,
        request: TriggerLearningRequest,
        user_id: Optional[UUID] = None,
    ) -> TriggerLearningResponse:
        """
        Trigger a learning job for a connector.

        Args:
            connector_id: UUID of the connector
            request: Learning request with job type and options
            user_id: Optional user who triggered the job

        Returns:
            Response with job ID and status
        """
        # Verify connector exists
        result = await self.db.execute(
            select(Connector).where(Connector.id == connector_id)
        )
        connector = result.scalar_one_or_none()
        if not connector:
            raise ValueError(f"Connector not found: {connector_id}")

        # Check for existing running job
        existing_result = await self.db.execute(
            select(DataLearningJob)
            .where(DataLearningJob.connector_id == connector_id)
            .where(DataLearningJob.status == DataLearningJobStatus.RUNNING)
        )
        existing_job = existing_result.scalar_one_or_none()
        if existing_job:
            return TriggerLearningResponse(
                job_id=existing_job.id,
                connector_id=connector_id,
                job_type=request.job_type,
                status=existing_job.status,
                message="A learning job is already running for this connector",
            )

        # Create job
        job = DataLearningJob(
            connector_id=connector_id,
            tenant_id=connector.tenant_id,
            job_type=request.job_type.value,
            status=DataLearningJobStatus.PENDING,
            config=request.config,
            triggered_by="manual",
            triggered_by_user_id=user_id,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)

        # Execute job (in production, this would be async via Celery)
        try:
            await self._execute_job(job, request.force_rediscovery)
        except Exception as e:
            logger.error(f"Learning job {job.id} failed: {e}")
            job.status = DataLearningJobStatus.FAILED
            job.status_message = str(e)
            job.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            raise

        return TriggerLearningResponse(
            job_id=job.id,
            connector_id=connector_id,
            job_type=request.job_type,
            status=job.status,
            message="Learning job completed successfully",
        )

    async def _execute_job(
        self,
        job: DataLearningJob,
        force_rediscovery: bool = False,
    ):
        """
        Execute a learning job.

        Args:
            job: The job to execute
            force_rediscovery: Force re-discovery even if data exists
        """
        job.status = DataLearningJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        await self.db.commit()

        results_summary = {}
        errors = []

        try:
            job_type = job.job_type

            if job_type == DataLearningJobType.FULL_LEARNING or \
               job_type == DataLearningJobType.CONTENT_MODEL_DISCOVERY:
                # Phase 1: Content Model Discovery
                try:
                    content_model = await self.content_model_service.discover_content_model(
                        connector_id=job.connector_id,
                        enrich_with_llm=self.llm_client is not None,
                        update_job=job,
                    )
                    results_summary["types_discovered"] = len(content_model.content_types)
                    results_summary["aspects_discovered"] = len(content_model.aspects)
                    results_summary["properties_discovered"] = len(
                        content_model.property_definitions or {}
                    )
                except Exception as e:
                    logger.error(f"Content model discovery failed: {e}")
                    errors.append({"phase": "content_model_discovery", "error": str(e)})

            if job_type == DataLearningJobType.FULL_LEARNING or \
               job_type == DataLearningJobType.FOLDER_ANALYSIS:
                # Phase 2: Folder Structure Analysis
                try:
                    patterns = await self.folder_analyzer.analyze_folder_structure(
                        connector_id=job.connector_id,
                        update_job=job,
                    )
                    results_summary["folder_patterns_learned"] = len(patterns)
                except Exception as e:
                    logger.error(f"Folder analysis failed: {e}")
                    errors.append({"phase": "folder_analysis", "error": str(e)})

            if job_type == DataLearningJobType.FULL_LEARNING or \
               job_type == DataLearningJobType.PROPERTY_MAPPING:
                # Phase 3: Property Mapping
                try:
                    mappings = await self.metadata_service.generate_property_mappings(
                        connector_id=job.connector_id,
                        update_job=job,
                    )
                    results_summary["properties_mapped"] = len(mappings)
                except Exception as e:
                    logger.error(f"Property mapping failed: {e}")
                    errors.append({"phase": "property_mapping", "error": str(e)})

            if job_type == DataLearningJobType.FULL_LEARNING or \
               job_type == DataLearningJobType.RELATIONSHIP_LEARNING:
                # Phase 4: Relationship Learning
                try:
                    relationships = await self.relationship_learner.learn_relationship_types(
                        connector_id=job.connector_id,
                        update_job=job,
                    )
                    results_summary["relationship_types_learned"] = len(relationships)
                except Exception as e:
                    logger.error(f"Relationship learning failed: {e}")
                    errors.append({"phase": "relationship_learning", "error": str(e)})

            if job_type == DataLearningJobType.FULL_LEARNING or \
               job_type == DataLearningJobType.STRATEGY_OPTIMIZATION:
                # Phase 5: Indexing Strategy Optimization
                try:
                    strategies = await self.strategy_optimizer.generate_indexing_strategies(
                        connector_id=job.connector_id,
                        update_job=job,
                    )
                    results_summary["strategies_generated"] = len(strategies)
                except Exception as e:
                    logger.error(f"Strategy optimization failed: {e}")
                    errors.append({"phase": "strategy_optimization", "error": str(e)})

            # Mark job as completed
            job.status = DataLearningJobStatus.COMPLETED
            job.results_summary = results_summary
            job.errors = errors if errors else None
            job.progress_percent = 100
            job.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            job.status = DataLearningJobStatus.FAILED
            job.status_message = str(e)
            job.errors = errors
            job.completed_at = datetime.now(timezone.utc)
            raise

        finally:
            await self.db.commit()

    async def get_job_status(
        self,
        job_id: UUID,
    ) -> Optional[DataLearningJob]:
        """Get status of a learning job."""
        result = await self.db.execute(
            select(DataLearningJob).where(DataLearningJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_connector_learning_status(
        self,
        connector_id: UUID,
    ) -> ConnectorLearningStatusResponse:
        """
        Get overall learning status for a connector.

        Returns summary of all learned data and recommendations.
        """
        # Verify connector exists
        result = await self.db.execute(
            select(Connector).where(Connector.id == connector_id)
        )
        connector = result.scalar_one_or_none()
        if not connector:
            raise ValueError(f"Connector not found: {connector_id}")

        # Get content model summary
        content_model_summary = await self.content_model_service.get_content_model_summary(
            connector_id
        )
        content_model = await self.content_model_service.get_content_model(connector_id)

        # Get folder patterns
        folder_patterns = await self.folder_analyzer.get_patterns(connector_id)
        verified_patterns = [p for p in folder_patterns if p.is_verified]

        # Get property mappings
        property_mappings = await self.metadata_service.get_property_mappings(connector_id)
        custom_mappings = [m for m in property_mappings if m.learned_from_usage]

        # Get relationship types
        relationship_types = await self.relationship_learner.get_relationship_types(connector_id)

        # Get indexing strategies
        strategies = await self.strategy_optimizer.get_strategies(connector_id)
        active_strategies = [s for s in strategies if s.is_active]

        # Get latest job
        latest_job_result = await self.db.execute(
            select(DataLearningJob)
            .where(DataLearningJob.connector_id == connector_id)
            .order_by(DataLearningJob.created_at.desc())
            .limit(1)
        )
        latest_job = latest_job_result.scalar_one_or_none()

        # Generate recommendations
        recommendations = []
        if not content_model:
            recommendations.append("Run content model discovery to learn document types")
        if not folder_patterns:
            recommendations.append("Run folder analysis to improve document context")
        if len(verified_patterns) < len(folder_patterns):
            recommendations.append("Review and verify detected folder patterns")
        if not property_mappings:
            recommendations.append("Generate property mappings for search optimization")
        if not strategies:
            recommendations.append("Generate indexing strategies for optimal retrieval")

        return ConnectorLearningStatusResponse(
            connector_id=connector_id,
            connector_name=connector.name,
            has_content_model=content_model is not None,
            content_model_discovered_at=content_model.discovered_at if content_model else None,
            content_model_summary=content_model_summary,
            folder_patterns_count=len(folder_patterns),
            verified_patterns_count=len(verified_patterns),
            property_mappings_count=len(property_mappings),
            custom_mappings_count=len(custom_mappings),
            relationship_types_count=len(relationship_types),
            indexing_strategies_count=len(strategies),
            active_strategies_count=len(active_strategies),
            latest_job=DataLearningJobResponse.model_validate(latest_job) if latest_job else None,
            recommendations=recommendations,
        )

    async def get_jobs_for_connector(
        self,
        connector_id: UUID,
        limit: int = 10,
    ) -> List[DataLearningJob]:
        """Get recent learning jobs for a connector."""
        result = await self.db.execute(
            select(DataLearningJob)
            .where(DataLearningJob.connector_id == connector_id)
            .order_by(DataLearningJob.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def cancel_job(
        self,
        job_id: UUID,
    ) -> bool:
        """
        Cancel a running learning job.

        Args:
            job_id: UUID of the job to cancel

        Returns:
            True if cancelled, False if job not found or not running
        """
        result = await self.db.execute(
            select(DataLearningJob).where(DataLearningJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return False

        if job.status != DataLearningJobStatus.RUNNING:
            return False

        job.status = DataLearningJobStatus.CANCELLED
        job.status_message = "Cancelled by user"
        job.completed_at = datetime.now(timezone.utc)
        await self.db.commit()

        return True

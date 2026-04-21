"""
Folder Structure Analyzer

Analyzes folder hierarchies from connectors to learn semantic patterns:
- Detects department/project/year structures
- Maps folder levels to semantic meanings
- Extracts context for documents based on their paths

Example: /Sites/gdapm/RRHH/2024/Expedientes → {department: "RRHH", year: "2024", type: "Expedientes"}
"""
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Connector,
    LearnedFolderPattern,
    DataLearningJob,
    IndexedDocument,
)
from app.schemas.data_learning import (
    LevelSemantic,
    LevelSemanticType,
    FolderContext,
)

logger = logging.getLogger(__name__)


class FolderStructureAnalyzer:
    """
    Analyzes folder structures to learn semantic patterns.

    The analyzer samples document paths, detects patterns, and infers
    the semantic meaning of each folder level (department, year, type, etc.).
    """

    # Known fixed folder names (case-insensitive)
    KNOWN_FIXED_FOLDERS = {
        "documentlibrary", "documents", "shared documents",
        "sites", "company_home", "documentos", "archivos",
    }

    # Year patterns
    YEAR_PATTERN = re.compile(r"^(19|20)\d{2}$")

    # Month patterns
    MONTH_PATTERNS = [
        re.compile(r"^(0?[1-9]|1[0-2])$"),  # 1-12
        re.compile(r"^(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)$", re.IGNORECASE),
        re.compile(r"^(january|february|march|april|may|june|july|august|september|october|november|december)$", re.IGNORECASE),
    ]

    # Common department names
    KNOWN_DEPARTMENTS = {
        "rrhh", "hr", "recursos humanos", "human resources",
        "legal", "juridico", "jurídico",
        "finance", "finanzas", "contabilidad", "accounting",
        "it", "sistemas", "tecnologia", "technology",
        "sales", "ventas", "comercial",
        "marketing", "comunicacion", "comunicación",
        "operations", "operaciones",
        "admin", "administracion", "administración",
    }

    def __init__(self, db: AsyncSession):
        """
        Initialize the analyzer.

        Args:
            db: Database session
        """
        self.db = db

    async def analyze_folder_structure(
        self,
        connector_id: UUID,
        sample_size: int = 1000,
        min_confidence: float = 0.6,
        update_job: Optional[DataLearningJob] = None,
    ) -> List[LearnedFolderPattern]:
        """
        Analyze folder structure from document paths.

        Args:
            connector_id: UUID of the connector
            sample_size: Number of documents to sample
            min_confidence: Minimum confidence to store a pattern
            update_job: Optional job to update progress

        Returns:
            List of learned folder patterns
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
            update_job.current_phase = "Sampling document paths"
            update_job.progress_percent = 10
            await self.db.commit()

        # Fetch sample of document paths
        paths_result = await self.db.execute(
            select(IndexedDocument.external_path)
            .where(IndexedDocument.connector_id == connector_id)
            .where(IndexedDocument.external_path.isnot(None))
            .limit(sample_size)
        )
        paths = [row[0] for row in paths_result.fetchall() if row[0]]

        if not paths:
            logger.warning(f"No document paths found for connector {connector_id}")
            return []

        # Update job progress
        if update_job:
            update_job.current_phase = f"Analyzing {len(paths)} document paths"
            update_job.progress_percent = 30
            await self.db.commit()

        # Analyze paths to detect patterns
        patterns = self._detect_patterns(paths)

        # Update job progress
        if update_job:
            update_job.current_phase = "Storing learned patterns"
            update_job.progress_percent = 70
            await self.db.commit()

        # Filter by confidence and store
        learned_patterns = []
        for pattern_info in patterns:
            if pattern_info["confidence"] >= min_confidence:
                # Check if pattern already exists
                existing = await self.db.execute(
                    select(LearnedFolderPattern)
                    .where(LearnedFolderPattern.connector_id == connector_id)
                    .where(LearnedFolderPattern.path_pattern == pattern_info["pattern"])
                )
                folder_pattern = existing.scalar_one_or_none()

                if folder_pattern:
                    # Update existing
                    folder_pattern.level_semantics = pattern_info["level_semantics"]
                    folder_pattern.example_paths = pattern_info["examples"][:5]
                    folder_pattern.match_count = pattern_info["match_count"]
                    folder_pattern.confidence = pattern_info["confidence"]
                    folder_pattern.learned_from_sample_size = len(paths)
                else:
                    # Create new
                    folder_pattern = LearnedFolderPattern(
                        connector_id=connector_id,
                        path_pattern=pattern_info["pattern"],
                        level_semantics=pattern_info["level_semantics"],
                        example_paths=pattern_info["examples"][:5],
                        match_count=pattern_info["match_count"],
                        confidence=pattern_info["confidence"],
                        learned_from_sample_size=len(paths),
                    )
                    self.db.add(folder_pattern)

                learned_patterns.append(folder_pattern)

        await self.db.commit()

        # Update job progress
        if update_job:
            update_job.current_phase = "Folder analysis completed"
            update_job.progress_percent = 100
            await self.db.commit()

        logger.info(
            f"Folder analysis completed for connector {connector_id}: "
            f"{len(learned_patterns)} patterns learned from {len(paths)} paths"
        )

        return learned_patterns

    def _detect_patterns(self, paths: List[str]) -> List[Dict[str, Any]]:
        """
        Detect folder patterns from a list of paths.

        Args:
            paths: List of document paths

        Returns:
            List of pattern info dicts
        """
        # Parse paths into segments
        parsed_paths = []
        for path in paths:
            segments = [s for s in path.split("/") if s]
            if segments:
                parsed_paths.append(segments)

        if not parsed_paths:
            return []

        # Group by path depth and structure
        depth_groups = defaultdict(list)
        for segments in parsed_paths:
            depth = len(segments)
            # Create structure signature (fixed vs variable)
            signature = []
            for seg in segments:
                if seg.lower() in self.KNOWN_FIXED_FOLDERS:
                    signature.append("fixed")
                elif self.YEAR_PATTERN.match(seg):
                    signature.append("year")
                elif any(p.match(seg) for p in self.MONTH_PATTERNS):
                    signature.append("month")
                else:
                    signature.append("var")
            depth_groups[(depth, tuple(signature))].append(segments)

        # Analyze each group
        patterns = []
        for (depth, signature), group_paths in depth_groups.items():
            if len(group_paths) < 3:  # Need minimum paths to detect pattern
                continue

            pattern_info = self._analyze_path_group(group_paths, signature)
            if pattern_info:
                patterns.append(pattern_info)

        return patterns

    def _analyze_path_group(
        self,
        group_paths: List[List[str]],
        signature: Tuple[str, ...]
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze a group of similar paths to extract pattern.

        Args:
            group_paths: List of path segment lists
            signature: Structural signature of the group

        Returns:
            Pattern info dict or None
        """
        if not group_paths:
            return None

        level_semantics = {}
        pattern_parts = []

        for level, sig_type in enumerate(signature):
            values = [p[level] for p in group_paths if len(p) > level]
            unique_values = set(values)
            value_counts = Counter(values)

            if sig_type == "fixed" or len(unique_values) == 1:
                # Fixed value
                fixed_value = value_counts.most_common(1)[0][0]
                pattern_parts.append(fixed_value)
                level_semantics[str(level)] = {
                    "name": fixed_value.lower().replace(" ", "_"),
                    "type": LevelSemanticType.FIXED.value,
                }
            elif sig_type == "year":
                pattern_parts.append("{year}")
                level_semantics[str(level)] = {
                    "name": "year",
                    "type": LevelSemanticType.TEMPORAL.value,
                    "format": "YYYY",
                    "values": sorted(unique_values)[:10],
                }
            elif sig_type == "month":
                pattern_parts.append("{month}")
                level_semantics[str(level)] = {
                    "name": "month",
                    "type": LevelSemanticType.TEMPORAL.value,
                    "format": "MM or month_name",
                    "values": sorted(unique_values)[:12],
                }
            else:
                # Variable - try to determine semantic type
                semantic_type = self._infer_semantic_type(unique_values)
                placeholder = "{" + semantic_type.value.lower() + "}"
                pattern_parts.append(placeholder)
                level_semantics[str(level)] = {
                    "name": semantic_type.value.lower(),
                    "type": semantic_type.value,
                    "values": sorted(unique_values)[:20],
                }

        # Build pattern string
        pattern = "/" + "/".join(pattern_parts)

        # Calculate confidence based on coverage and consistency
        confidence = min(1.0, len(group_paths) / 100)  # More paths = higher confidence

        # Build example paths
        examples = ["/" + "/".join(p) for p in group_paths[:5]]

        return {
            "pattern": pattern,
            "level_semantics": level_semantics,
            "examples": examples,
            "match_count": len(group_paths),
            "confidence": confidence,
        }

    def _infer_semantic_type(self, values: set) -> LevelSemanticType:
        """
        Infer the semantic type of a folder level from its values.

        Args:
            values: Set of values at this level

        Returns:
            Inferred semantic type
        """
        lower_values = {v.lower() for v in values}

        # Check if it looks like departments
        if lower_values & self.KNOWN_DEPARTMENTS:
            return LevelSemanticType.CLASSIFICATION

        # Check if it looks like site identifiers
        if len(values) <= 3 and all(len(v) < 20 for v in values):
            return LevelSemanticType.SITE_IDENTIFIER

        # Check if it looks like document types
        if any(kw in " ".join(lower_values) for kw in ["expediente", "contrato", "factura", "documento"]):
            return LevelSemanticType.DOCUMENT_TYPE

        # Default to classification
        return LevelSemanticType.CLASSIFICATION

    async def get_folder_context(
        self,
        connector_id: UUID,
        path: str,
    ) -> FolderContext:
        """
        Get folder context for a document path.

        Matches the path against learned patterns and extracts
        semantic context (department, year, etc.).

        Args:
            connector_id: UUID of the connector
            path: Document path

        Returns:
            FolderContext with extracted semantics
        """
        # Fetch patterns for connector
        result = await self.db.execute(
            select(LearnedFolderPattern)
            .where(LearnedFolderPattern.connector_id == connector_id)
            .order_by(LearnedFolderPattern.confidence.desc())
        )
        patterns = result.scalars().all()

        if not patterns:
            return FolderContext(path=path, confidence=0.0)

        # Parse path
        segments = [s for s in path.split("/") if s]

        # Try to match against patterns
        for pattern in patterns:
            match_result = self._match_pattern(segments, pattern)
            if match_result:
                return FolderContext(
                    path=path,
                    pattern_id=pattern.id,
                    semantics=match_result,
                    confidence=pattern.confidence,
                )

        return FolderContext(path=path, confidence=0.0)

    def _match_pattern(
        self,
        segments: List[str],
        pattern: LearnedFolderPattern,
    ) -> Optional[Dict[str, Any]]:
        """
        Match path segments against a pattern.

        Args:
            segments: Path segments
            pattern: Learned pattern to match against

        Returns:
            Dict of extracted semantics or None if no match
        """
        pattern_parts = [p for p in pattern.path_pattern.split("/") if p]

        if len(segments) < len(pattern_parts):
            return None

        semantics = {}
        for i, part in enumerate(pattern_parts):
            if i >= len(segments):
                return None

            segment = segments[i]
            level_info = pattern.level_semantics.get(str(i), {})
            level_type = level_info.get("type", "")
            level_name = level_info.get("name", f"level_{i}")

            if part.startswith("{") and part.endswith("}"):
                # Variable - extract value
                semantics[level_name] = segment
            else:
                # Fixed - must match
                if segment.lower() != part.lower():
                    return None

        return semantics

    async def get_patterns(
        self,
        connector_id: UUID,
    ) -> List[LearnedFolderPattern]:
        """Get all learned patterns for a connector."""
        result = await self.db.execute(
            select(LearnedFolderPattern)
            .where(LearnedFolderPattern.connector_id == connector_id)
            .order_by(LearnedFolderPattern.confidence.desc())
        )
        return list(result.scalars().all())

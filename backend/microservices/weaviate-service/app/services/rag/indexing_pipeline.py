"""
Document Indexing Pipeline

Complete RAG preprocessing pipeline:
- Text Extraction: Call textextract-service for PDF/DOCX/etc.
- Layer 0: DocumentIntelligence (quality assessment, cleaning)
- Layer 1: SemanticChunker (structure-aware chunking)

This pipeline prepares documents for vector indexing with:
1. Text extraction from binary files via textextract-service
2. Quality analysis of extracted text
3. Automatic cleaning if needed
4. Intelligent chunking based on document structure
5. Metadata enrichment for retrieval

Usage:
    from app.services.rag.indexing_pipeline import indexing_pipeline

    # Process from file bytes (full pipeline)
    result = await indexing_pipeline.process_file(
        document_id="doc-123",
        file_bytes=pdf_content,
        filename="contract.pdf",
        metadata={"title": "Contract"},
        tenant_id="tenant-abc"
    )

    # Or process from already-extracted text
    result = await indexing_pipeline.process_text(
        document_id="doc-123",
        text=extracted_text,
        metadata={"title": "Contract"},
        tenant_id="tenant-abc"
    )
"""

import logging
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .document_intelligence import (
    DocumentIntelligence,
    DocumentAnalysis,
    DocumentQuality,
    document_intelligence,
)
from .semantic_chunker import (
    SemanticChunker,
    DocumentChunk,
    PositionedChunk,
    DocumentType,
    semantic_chunker,
)
from .textextract_client import TextExtractClient, TextExtractResult, textextract_client
from app.services.text_alignment_service import (
    TextAlignmentService,
    AlignedBlock,
    AlignmentResult,
    text_alignment_service,
)
from app.services.knowledge import KnowledgeExtractionService, get_knowledge_service
from app.services.knowledge.schemas import KnowledgeExtractionResult

logger = logging.getLogger(__name__)


@dataclass
class IndexingResult:
    """Result of document indexing pipeline"""
    # Document info
    document_id: str
    tenant_id: str

    # Extraction results
    extracted_text: str = ""
    extraction_language: Optional[str] = None
    extraction_characters: int = 0

    # Processing results
    analysis: Optional[DocumentAnalysis] = None
    chunks: List[DocumentChunk] = field(default_factory=list)

    # Knowledge extraction results
    knowledge_result: Optional[KnowledgeExtractionResult] = None

    # Processing metadata
    processed_at: datetime = field(default_factory=datetime.now)
    extraction_time_ms: float = 0.0
    analysis_time_ms: float = 0.0
    chunking_time_ms: float = 0.0
    knowledge_extraction_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Status
    success: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "tenant_id": self.tenant_id,
            "extraction": {
                "characters": self.extraction_characters,
                "language": self.extraction_language,
            },
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "chunk_count": len(self.chunks),
            "knowledge": {
                "entities_count": self.knowledge_result.entities_count if self.knowledge_result else 0,
                "relationships_count": self.knowledge_result.relationships_count if self.knowledge_result else 0,
                "domain": self.knowledge_result.domain.value if self.knowledge_result else None,
            } if self.knowledge_result else None,
            "timing": {
                "extraction_ms": self.extraction_time_ms,
                "analysis_ms": self.analysis_time_ms,
                "chunking_ms": self.chunking_time_ms,
                "knowledge_extraction_ms": self.knowledge_extraction_time_ms,
                "total_ms": self.total_time_ms,
            },
            "processed_at": self.processed_at.isoformat(),
            "success": self.success,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class IndexingPipeline:
    """
    Complete document indexing pipeline.

    Pipeline stages:
    1. Extract text (textextract-service) - for binary files
    2. Analyze quality (DocumentIntelligence)
    3. Clean text if needed
    4. Chunk document (SemanticChunker)
    5. Extract knowledge entities (KnowledgeExtractionService)
    6. Enrich chunks with metadata
    """

    def __init__(
        self,
        extractor: Optional[TextExtractClient] = None,
        intelligence: Optional[DocumentIntelligence] = None,
        chunker: Optional[SemanticChunker] = None,
        knowledge_extractor: Optional[KnowledgeExtractionService] = None,
    ):
        self.extractor = extractor or textextract_client
        self.intelligence = intelligence or document_intelligence
        self.chunker = chunker or semantic_chunker
        self.knowledge_extractor = knowledge_extractor or get_knowledge_service()
        self._knowledge_extraction_enabled = True

    async def process_file(
        self,
        document_id: str,
        file_bytes: bytes,
        filename: str,
        metadata: Dict[str, Any],
        tenant_id: str,
        user_id: Optional[str] = None,
        extraction_strategy: str = "auto",
    ) -> IndexingResult:
        """
        Process a document file through the complete pipeline.

        Args:
            document_id: Unique document identifier
            file_bytes: Raw file content (PDF, DOCX, etc.)
            filename: Original filename
            metadata: Document metadata
            tenant_id: Tenant identifier
            user_id: Optional user identifier
            extraction_strategy: Text extraction strategy (auto, fast, hi_res)

        Returns:
            IndexingResult with chunks ready for embedding
        """
        start_time = time.time()
        errors = []
        warnings = []

        # === Stage 1: Text Extraction ===
        logger.info(f"[{document_id}] Starting text extraction from {filename}...")
        extraction_start = time.time()

        extract_result = await self.extractor.extract_from_bytes(
            file_bytes=file_bytes,
            filename=filename,
            tenant_id=tenant_id,
            user_id=user_id,
            strategy=extraction_strategy,
        )

        extraction_time = (time.time() - extraction_start) * 1000

        if not extract_result.success:
            logger.error(f"[{document_id}] Text extraction failed: {extract_result.error}")
            return IndexingResult(
                document_id=document_id,
                tenant_id=tenant_id,
                extraction_time_ms=extraction_time,
                total_time_ms=(time.time() - start_time) * 1000,
                success=False,
                errors=[f"Text extraction failed: {extract_result.error}"],
            )

        if not extract_result.text.strip():
            logger.warning(f"[{document_id}] No text extracted from {filename}")
            return IndexingResult(
                document_id=document_id,
                tenant_id=tenant_id,
                extraction_time_ms=extraction_time,
                total_time_ms=(time.time() - start_time) * 1000,
                success=False,
                errors=["No text content extracted from document"],
            )

        logger.info(
            f"[{document_id}] Extracted {extract_result.characters} chars, "
            f"language={extract_result.language}"
        )

        # Add extraction metadata
        enriched_metadata = {
            **metadata,
            "filename": filename,
            "extraction_strategy": extraction_strategy,
            "detected_language": extract_result.language,
            **extract_result.metadata,
        }

        # Continue with text processing
        result = await self._process_text_internal(
            document_id=document_id,
            text=extract_result.text,
            metadata=enriched_metadata,
            tenant_id=tenant_id,
            errors=errors,
            warnings=warnings,
        )

        # Update timing
        result.extracted_text = extract_result.text
        result.extraction_language = extract_result.language
        result.extraction_characters = extract_result.characters
        result.extraction_time_ms = extraction_time
        result.total_time_ms = (time.time() - start_time) * 1000

        return result

    async def process_text(
        self,
        document_id: str,
        text: str,
        metadata: Dict[str, Any],
        tenant_id: str,
    ) -> IndexingResult:
        """
        Process already-extracted text through the pipeline.

        Use this when text is already available (e.g., from database or API).

        Args:
            document_id: Unique document identifier
            text: Already-extracted document text
            metadata: Document metadata
            tenant_id: Tenant identifier

        Returns:
            IndexingResult with chunks ready for embedding
        """
        start_time = time.time()

        result = await self._process_text_internal(
            document_id=document_id,
            text=text,
            metadata=metadata,
            tenant_id=tenant_id,
            errors=[],
            warnings=[],
        )

        result.extracted_text = text
        result.extraction_characters = len(text)
        result.total_time_ms = (time.time() - start_time) * 1000

        return result

    async def _process_text_internal(
        self,
        document_id: str,
        text: str,
        metadata: Dict[str, Any],
        tenant_id: str,
        errors: List[str],
        warnings: List[str],
    ) -> IndexingResult:
        """Internal text processing (analysis + chunking)"""

        # === Stage 2: Document Intelligence ===
        logger.info(f"[{document_id}] Analyzing document quality...")
        analysis_start = time.time()

        try:
            analysis = self.intelligence.analyze(text, metadata)
            analysis_time = (time.time() - analysis_start) * 1000

            # Log quality issues
            if analysis.issues:
                for issue in analysis.issues:
                    warnings.append(f"Quality issue: {issue.value}")
                logger.warning(f"[{document_id}] Quality issues: {[i.value for i in analysis.issues]}")

            logger.info(
                f"[{document_id}] Quality: {analysis.quality.value}, "
                f"confidence: {analysis.confidence:.2f}"
            )

        except Exception as e:
            logger.error(f"[{document_id}] Document analysis failed: {e}")
            errors.append(f"Analysis failed: {e}")

            return IndexingResult(
                document_id=document_id,
                tenant_id=tenant_id,
                analysis_time_ms=(time.time() - analysis_start) * 1000,
                success=False,
                errors=errors,
                warnings=warnings,
            )

        # Use cleaned text if needed
        if analysis.needs_cleaning and analysis.processed_text:
            text_for_chunking = analysis.processed_text
            logger.info(f"[{document_id}] Using cleaned text for chunking")
        else:
            text_for_chunking = text

        # === Stage 3: Semantic Chunking ===
        logger.info(f"[{document_id}] Starting semantic chunking...")
        chunking_start = time.time()

        try:
            # Detect document type
            doc_type = self._detect_document_type(metadata, analysis)

            # Prepare metadata for chunks
            chunk_metadata = {
                **metadata,
                "document_id": document_id,
                "tenant_id": tenant_id,
                "quality": analysis.quality.value,
                "confidence": analysis.confidence,
            }

            # Chunk the document
            chunks = self.chunker.chunk_document(
                text=text_for_chunking,
                metadata=chunk_metadata,
                document_type=doc_type,
            )

            chunking_time = (time.time() - chunking_start) * 1000

            logger.info(f"[{document_id}] Created {len(chunks)} chunks")

            # Enrich chunks with analysis metadata
            for i, chunk in enumerate(chunks):
                chunk.metadata["chunk_index"] = i
                chunk.metadata["total_chunks"] = len(chunks)
                chunk.metadata["has_tables"] = analysis.has_tables
                chunk.metadata["has_headers"] = analysis.has_headers

        except Exception as e:
            logger.error(f"[{document_id}] Chunking failed: {e}")
            errors.append(f"Chunking failed: {e}")

            return IndexingResult(
                document_id=document_id,
                tenant_id=tenant_id,
                analysis=analysis,
                analysis_time_ms=analysis_time,
                chunking_time_ms=(time.time() - chunking_start) * 1000,
                success=False,
                errors=errors,
                warnings=warnings,
            )

        # === Stage 4: Knowledge Extraction ===
        knowledge_result = None
        knowledge_time = 0.0

        if self._knowledge_extraction_enabled:
            logger.info(f"[{document_id}] Extracting knowledge entities...")
            knowledge_start = time.time()

            try:
                # Get ACL info from metadata if available
                acl_user_ids = metadata.get("acl_user_ids", [])
                acl_role_ids = metadata.get("acl_role_ids", [])
                acl_everyone = metadata.get("acl_everyone", False)

                knowledge_result = await self.knowledge_extractor.extract_from_document(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    extracted_entities=metadata.get("extracted_entities", []),
                    content=text_for_chunking,
                    document_type=metadata.get("document_type", "general"),
                    acl_user_ids=acl_user_ids,
                    acl_role_ids=acl_role_ids,
                    acl_everyone=acl_everyone,
                )

                knowledge_time = (time.time() - knowledge_start) * 1000

                logger.info(
                    f"[{document_id}] Extracted {knowledge_result.entities_count} entities, "
                    f"{knowledge_result.relationships_count} relationships, "
                    f"domain: {knowledge_result.domain.value}"
                )

            except Exception as e:
                logger.warning(f"[{document_id}] Knowledge extraction failed (non-blocking): {e}")
                warnings.append(f"Knowledge extraction failed: {e}")
                knowledge_time = (time.time() - knowledge_start) * 1000

        return IndexingResult(
            document_id=document_id,
            tenant_id=tenant_id,
            analysis=analysis,
            chunks=chunks,
            knowledge_result=knowledge_result,
            analysis_time_ms=analysis_time,
            chunking_time_ms=chunking_time,
            knowledge_extraction_time_ms=knowledge_time,
            success=True,
            errors=errors,
            warnings=warnings,
        )

    def _detect_document_type(
        self,
        metadata: Dict[str, Any],
        analysis: DocumentAnalysis,
    ) -> Optional[DocumentType]:
        """Detect document type from metadata and analysis"""
        # Check metadata first
        doc_type_str = metadata.get("document_type", "").lower()

        type_mapping = {
            "contract": DocumentType.LEGAL_CONTRACT,
            "legal": DocumentType.LEGAL_CONTRACT,
            "brief": DocumentType.LEGAL_BRIEF,
            "technical": DocumentType.TECHNICAL_MANUAL,
            "manual": DocumentType.TECHNICAL_MANUAL,
            "medical": DocumentType.MEDICAL_RECORD,
            "financial": DocumentType.FINANCIAL_REPORT,
            "report": DocumentType.FINANCIAL_REPORT,
        }

        for key, dtype in type_mapping.items():
            if key in doc_type_str:
                return dtype

        # Infer from analysis
        if analysis.header_count > 5:
            return DocumentType.TECHNICAL_MANUAL

        if analysis.has_tables and analysis.table_count > 2:
            return DocumentType.FINANCIAL_REPORT

        return DocumentType.GENERAL

    async def process_file_from_url(
        self,
        document_id: str,
        file_url: str,
        filename: str,
        metadata: Dict[str, Any],
        tenant_id: str,
        user_id: Optional[str] = None,
        extraction_strategy: str = "auto",
    ) -> IndexingResult:
        """
        Download file from URL and process through pipeline.

        Args:
            document_id: Unique document identifier
            file_url: URL to download file from
            filename: Original filename
            metadata: Document metadata
            tenant_id: Tenant identifier
            user_id: Optional user identifier
            extraction_strategy: Extraction strategy

        Returns:
            IndexingResult with chunks ready for embedding
        """
        start_time = time.time()

        # Download and extract
        logger.info(f"[{document_id}] Extracting from URL: {file_url}")
        extraction_start = time.time()

        extract_result = await self.extractor.extract_from_url(
            file_url=file_url,
            filename=filename,
            tenant_id=tenant_id,
            user_id=user_id,
            strategy=extraction_strategy,
        )

        extraction_time = (time.time() - extraction_start) * 1000

        if not extract_result.success:
            return IndexingResult(
                document_id=document_id,
                tenant_id=tenant_id,
                extraction_time_ms=extraction_time,
                total_time_ms=(time.time() - start_time) * 1000,
                success=False,
                errors=[f"Extraction from URL failed: {extract_result.error}"],
            )

        # Continue with text processing
        enriched_metadata = {
            **metadata,
            "filename": filename,
            "source_url": file_url,
            "detected_language": extract_result.language,
        }

        result = await self._process_text_internal(
            document_id=document_id,
            text=extract_result.text,
            metadata=enriched_metadata,
            tenant_id=tenant_id,
            errors=[],
            warnings=[],
        )

        result.extracted_text = extract_result.text
        result.extraction_language = extract_result.language
        result.extraction_characters = extract_result.characters
        result.extraction_time_ms = extraction_time
        result.total_time_ms = (time.time() - start_time) * 1000

        return result

    async def process_batch_files(
        self,
        files: List[Dict[str, Any]],
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> List[IndexingResult]:
        """
        Process multiple files in batch.

        Args:
            files: List of dicts with document_id, file_bytes, filename, metadata
            tenant_id: Tenant identifier
            user_id: Optional user identifier

        Returns:
            List of IndexingResults
        """
        results = []

        for file_info in files:
            result = await self.process_file(
                document_id=file_info["document_id"],
                file_bytes=file_info["file_bytes"],
                filename=file_info["filename"],
                metadata=file_info.get("metadata", {}),
                tenant_id=tenant_id,
                user_id=user_id,
            )
            results.append(result)

        # Log batch summary
        successful = sum(1 for r in results if r.success)
        total_chunks = sum(len(r.chunks) for r in results)

        logger.info(
            f"Batch processing complete: {successful}/{len(files)} successful, "
            f"{total_chunks} total chunks"
        )

        return results

    async def process_file_with_positions(
        self,
        document_id: str,
        pdf_bytes: bytes,
        tika_text: Optional[str],
        metadata: Dict[str, Any],
        tenant_id: str,
        alignment_service: Optional[TextAlignmentService] = None,
    ) -> "PositionedIndexingResult":
        """
        Procesa un PDF creando chunks con información de posición.

        Este método es ideal para documentos que requieren anotaciones
        precisas, ya que preserva:
        - Páginas de inicio/fin de cada chunk
        - Posiciones de caracteres en texto completo
        - Coordenadas bbox para localización en PDF

        Args:
            document_id: ID único del documento
            pdf_bytes: PDF en bytes
            tika_text: Texto extraído por Tika (opcional, se extrae con PyMuPDF si no se provee)
            metadata: Metadatos del documento
            tenant_id: ID del tenant
            alignment_service: Servicio de alineamiento (opcional)

        Returns:
            PositionedIndexingResult con chunks posicionados
        """
        start_time = time.time()
        errors = []
        warnings = []

        aligner = alignment_service or text_alignment_service

        logger.info(f"[{document_id}] Procesando PDF con posiciones...")

        # === Stage 1: Text Alignment ===
        alignment_start = time.time()

        try:
            alignment_result = aligner.align_text_with_coordinates(
                pdf_bytes=pdf_bytes,
                tika_text=tika_text,
                use_tika_text=tika_text is not None,
            )
            alignment_time = (time.time() - alignment_start) * 1000

            if not alignment_result.aligned_blocks:
                logger.warning(f"[{document_id}] No se alinearon bloques")
                return PositionedIndexingResult(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    alignment_time_ms=alignment_time,
                    total_time_ms=(time.time() - start_time) * 1000,
                    success=False,
                    errors=["No se pudieron alinear bloques del documento"],
                )

            logger.info(
                f"[{document_id}] Alineados {len(alignment_result.aligned_blocks)} bloques, "
                f"calidad: {alignment_result.alignment_quality:.1%}"
            )

            warnings.extend(alignment_result.warnings)

        except Exception as e:
            logger.error(f"[{document_id}] Error en alineamiento: {e}")
            return PositionedIndexingResult(
                document_id=document_id,
                tenant_id=tenant_id,
                alignment_time_ms=(time.time() - alignment_start) * 1000,
                total_time_ms=(time.time() - start_time) * 1000,
                success=False,
                errors=[f"Error de alineamiento: {e}"],
            )

        # === Stage 2: Document Analysis (optional) ===
        analysis = None
        analysis_time = 0.0

        try:
            analysis_start = time.time()
            analysis = self.intelligence.analyze(alignment_result.full_text, metadata)
            analysis_time = (time.time() - analysis_start) * 1000

            if analysis.issues:
                for issue in analysis.issues:
                    warnings.append(f"Problema de calidad: {issue.value}")

        except Exception as e:
            logger.warning(f"[{document_id}] Análisis de calidad falló: {e}")
            warnings.append(f"Análisis de calidad omitido: {e}")

        # === Stage 3: Positioned Chunking ===
        logger.info(f"[{document_id}] Creando chunks posicionados...")
        chunking_start = time.time()

        try:
            doc_type = self._detect_document_type(metadata, analysis) if analysis else None

            chunk_metadata = {
                **metadata,
                "document_id": document_id,
                "tenant_id": tenant_id,
                "quality": analysis.quality.value if analysis else "unknown",
                "alignment_quality": alignment_result.alignment_quality,
            }

            positioned_chunks = self.chunker.chunk_document_with_positions(
                aligned_blocks=alignment_result.aligned_blocks,
                metadata=chunk_metadata,
                document_type=doc_type,
            )

            chunking_time = (time.time() - chunking_start) * 1000

            logger.info(f"[{document_id}] Creados {len(positioned_chunks)} chunks posicionados")

        except Exception as e:
            logger.error(f"[{document_id}] Error en chunking: {e}")
            return PositionedIndexingResult(
                document_id=document_id,
                tenant_id=tenant_id,
                alignment_result=alignment_result,
                analysis=analysis,
                alignment_time_ms=alignment_time,
                analysis_time_ms=analysis_time,
                chunking_time_ms=(time.time() - chunking_start) * 1000,
                total_time_ms=(time.time() - start_time) * 1000,
                success=False,
                errors=[f"Error de chunking: {e}"],
                warnings=warnings,
            )

        return PositionedIndexingResult(
            document_id=document_id,
            tenant_id=tenant_id,
            full_text=alignment_result.full_text,
            alignment_result=alignment_result,
            analysis=analysis,
            positioned_chunks=positioned_chunks,
            alignment_time_ms=alignment_time,
            analysis_time_ms=analysis_time,
            chunking_time_ms=chunking_time,
            total_time_ms=(time.time() - start_time) * 1000,
            success=True,
            errors=errors,
            warnings=warnings,
        )


@dataclass
class PositionedIndexingResult:
    """
    Resultado de indexación con posiciones completas.

    Contiene chunks con información de:
    - Página de inicio/fin
    - Posición de caracteres
    - Coordenadas bbox para PDF
    """
    document_id: str
    tenant_id: str

    # Texto completo
    full_text: str = ""

    # Resultado de alineamiento
    alignment_result: Optional[AlignmentResult] = None

    # Análisis de calidad
    analysis: Optional[DocumentAnalysis] = None

    # Chunks posicionados
    positioned_chunks: List[PositionedChunk] = field(default_factory=list)

    # Tiempos de procesamiento
    processed_at: datetime = field(default_factory=datetime.now)
    alignment_time_ms: float = 0.0
    analysis_time_ms: float = 0.0
    chunking_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Estado
    success: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "tenant_id": self.tenant_id,
            "full_text_length": len(self.full_text),
            "alignment_quality": (
                self.alignment_result.alignment_quality
                if self.alignment_result else None
            ),
            "total_blocks": (
                len(self.alignment_result.aligned_blocks)
                if self.alignment_result else 0
            ),
            "chunk_count": len(self.positioned_chunks),
            "timing": {
                "alignment_ms": self.alignment_time_ms,
                "analysis_ms": self.analysis_time_ms,
                "chunking_ms": self.chunking_time_ms,
                "total_ms": self.total_time_ms,
            },
            "processed_at": self.processed_at.isoformat(),
            "success": self.success,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# Global instance
indexing_pipeline = IndexingPipeline()

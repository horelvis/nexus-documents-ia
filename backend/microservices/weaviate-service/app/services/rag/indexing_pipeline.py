"""
Document Indexing Pipeline

Complete RAG preprocessing pipeline:
- Text Extraction: Call intelligence-docs-service for PDF/DOCX/etc.
- Layer 0: DocumentIntelligence (quality assessment, cleaning)
- Layer 1: SemanticChunker (structure-aware chunking)
- Layer 2: VisualExtractor (multimodal content for images/tables/diagrams)

This pipeline prepares documents for vector indexing with:
1. Text extraction from binary files via intelligence-docs-service
2. Quality analysis of extracted text
3. Automatic cleaning if needed
4. Intelligent chunking based on document structure
5. Visual content extraction (tables, diagrams, images) for multimodal embedding
6. Metadata enrichment for retrieval

Usage:
    from app.services.rag.indexing_pipeline import indexing_pipeline

    # Process from file bytes (full pipeline)
    result = await indexing_pipeline.process_file(
        document_id="doc-123",
        file_bytes=pdf_content,
        filename="contract.pdf",
        metadata={"title": "Contract"},
    )

    # Or process from already-extracted text
    result = await indexing_pipeline.process_text(
        document_id="doc-123",
        text=extracted_text,
        metadata={"title": "Contract"},
    )

    # Process with multimodal (visual) content
    result = await indexing_pipeline.process_file(
        document_id="doc-123",
        file_bytes=pdf_content,
        filename="report.pdf",
        metadata={"title": "Annual Report"},
        extract_visuals=True,  # Enable multimodal extraction
    )

"""

import logging
import os
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from app.core.config import settings
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
from .hierarchical_indexer import (
    HierarchicalIndexer,
    DocumentSummary,
    hierarchical_indexer,
)
from app.clients.intelligence_client import (
    IntelligenceExtractClient,
    TextExtractResult,
    LangExtractResult,
    OCRResult,
    intelligence_extract_client,
)
from app.clients import intelligence_client
from app.services.text_alignment_service import (
    TextAlignmentService,
    AlignedBlock,
    AlignmentResult,
    text_alignment_service,
)
from app.services.knowledge import KnowledgeExtractionService, get_knowledge_service
from app.services.knowledge.schemas import KnowledgeExtractionResult

# Contextual Retrieval (Anthropic pattern)
try:
    from .contextual_retrieval import (
        contextual_retrieval,
        ContextGenerationResult,
        ContextualizedChunk,
    )
    CONTEXTUAL_RETRIEVAL_AVAILABLE = True
except ImportError:
    CONTEXTUAL_RETRIEVAL_AVAILABLE = False
    contextual_retrieval = None

# Conditional imports for multimodal support
try:
    from .visual_extractor import (
        VisualContentExtractor,
        VisualExtractionResult,
        ExtractedVisual,
        visual_extractor,
    )
    from app.services.multimodal_embedding_service import (
        MultimodalEmbeddingService,
        ContentType,
        VisualContent,
        multimodal_embedding_service,
    )
    MULTIMODAL_AVAILABLE = True
except ImportError:
    MULTIMODAL_AVAILABLE = False
    visual_extractor = None
    multimodal_embedding_service = None

logger = logging.getLogger(__name__)


@dataclass
class VisualEmbeddingItem:
    """A visual content item with its embedding"""
    content_type: str  # image, table_image, diagram, page_thumbnail
    embedding: List[float]
    page_number: int
    bbox: tuple  # (x0, y0, x1, y1)
    caption: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IndexingResult:
    """Result of document indexing pipeline"""
    # Document info
    document_id: str

    # Extraction results
    extracted_text: str = ""
    extraction_language: Optional[str] = None
    extraction_characters: int = 0

    # Processing results
    analysis: Optional[DocumentAnalysis] = None
    chunks: List[DocumentChunk] = field(default_factory=list)

    # Contextual Retrieval results (Anthropic pattern)
    contextual_prefix: Optional[str] = None  # Context prepended to chunks

    # Knowledge extraction results
    knowledge_result: Optional[KnowledgeExtractionResult] = None

    # Hierarchical summary (for long context RAG)
    document_summary: Optional[DocumentSummary] = None

    # Visual/Multimodal extraction results
    visual_embeddings: List[VisualEmbeddingItem] = field(default_factory=list)
    images_count: int = 0
    tables_count: int = 0
    diagrams_count: int = 0

    # Processing metadata
    processed_at: datetime = field(default_factory=datetime.now)
    extraction_time_ms: float = 0.0
    analysis_time_ms: float = 0.0
    chunking_time_ms: float = 0.0
    contextual_time_ms: float = 0.0  # Contextual Retrieval processing
    knowledge_extraction_time_ms: float = 0.0
    summary_generation_time_ms: float = 0.0  # Hierarchical RAG
    visual_extraction_time_ms: float = 0.0
    total_time_ms: float = 0.0

    # Status
    success: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "extraction": {
                "characters": self.extraction_characters,
                "language": self.extraction_language,
            },
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "chunk_count": len(self.chunks),
            "contextual_retrieval": {
                "context_prefix_length": len(self.contextual_prefix) if self.contextual_prefix else 0,
            } if self.contextual_prefix else None,
            "knowledge": {
                "entities_count": self.knowledge_result.entities_count if self.knowledge_result else 0,
                "relationships_count": self.knowledge_result.relationships_count if self.knowledge_result else 0,
            } if self.knowledge_result else None,
            "visual": {
                "visual_embeddings_count": len(self.visual_embeddings),
                "images_count": self.images_count,
                "tables_count": self.tables_count,
                "diagrams_count": self.diagrams_count,
            } if self.visual_embeddings else None,
            "timing": {
                "extraction_ms": self.extraction_time_ms,
                "analysis_ms": self.analysis_time_ms,
                "chunking_ms": self.chunking_time_ms,
                "contextual_ms": self.contextual_time_ms,
                "knowledge_extraction_ms": self.knowledge_extraction_time_ms,
                "visual_extraction_ms": self.visual_extraction_time_ms,
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
    1. Extract text (intelligence-docs-service) - for binary files
    2. Analyze quality (DocumentIntelligence)
    2.5. Enhanced OCR fallback (if quality < threshold)
    3. Clean text if needed
    4. Chunk document (SemanticChunker)
    5. Extract knowledge entities (KnowledgeExtractionService)
    6. Extract visual content (VisualExtractor) - for multimodal embedding
    7. Enrich chunks with metadata
    """

    def __init__(
        self,
        extractor: Optional[IntelligenceExtractClient] = None,
        intelligence: Optional[DocumentIntelligence] = None,
        chunker: Optional[SemanticChunker] = None,
        knowledge_extractor: Optional[KnowledgeExtractionService] = None,
    ):
        self.extractor = extractor or intelligence_extract_client
        self.intelligence = intelligence or document_intelligence
        self.chunker = chunker or semantic_chunker
        self.knowledge_extractor = knowledge_extractor or get_knowledge_service()
        self._knowledge_extraction_enabled = True
        # Visual extractor for multimodal support
        self._visual_extractor = visual_extractor if MULTIMODAL_AVAILABLE else None
        self._embedding_service = multimodal_embedding_service if MULTIMODAL_AVAILABLE else None

    async def process_file(
        self,
        document_id: str,
        file_bytes: bytes,
        filename: str,
        metadata: Dict[str, Any],
        user_id: Optional[str] = None,
        extraction_strategy: str = "auto",
        extract_visuals: Optional[bool] = None,
        indexing_strategy: Optional[Dict[str, Any]] = None,
    ) -> IndexingResult:
        """
        Process a document file through the complete pipeline.

        Args:
            document_id: Unique document identifier
            file_bytes: Raw file content (PDF, DOCX, etc.)
            filename: Original filename
            metadata: Document metadata
            user_id: Optional user identifier
            extraction_strategy: Text extraction strategy (auto, fast, hi_res)
            extract_visuals: If True, extract visual content for multimodal embedding.
                           Defaults to config setting (MULTIMODAL_EMBEDDING_ENABLED).
            indexing_strategy: Optional strategy from Data Learning System:
                - chunking_type: semantic, legal_sections, markdown_headers, paragraph
                - chunking_config: {target_chunk_size, overlap, ...}
                - embedding_fields: Fields to prioritize in embedding
                - extract_entities: Whether to extract named entities

        Returns:
            IndexingResult with chunks ready for embedding

        Note: MIME type is automatically detected from file content (magic bytes)
        by the intelligence-docs-service, NOT from the filename extension.
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
            user_id=user_id,
            strategy=extraction_strategy,
        )

        extraction_time = (time.time() - extraction_start) * 1000

        if not extract_result.success:
            logger.error(f"[{document_id}] Text extraction failed: {extract_result.error}")
            return IndexingResult(
                document_id=document_id,
                extraction_time_ms=extraction_time,
                total_time_ms=(time.time() - start_time) * 1000,
                success=False,
                errors=[f"Text extraction failed: {extract_result.error}"],
            )

        # Note: We don't return early on empty text anymore - let OCR fallback handle it
        if not extract_result.text.strip():
            logger.warning(f"[{document_id}] No text from Tika for {filename}, will try OCR fallback")
        else:
            logger.info(
                f"[{document_id}] Extracted {extract_result.characters} chars, "
                f"language={extract_result.language}"
            )

        # === Stage 1.5: Enhanced OCR Fallback ===
        # Check if we should trigger enhanced OCR for scanned/low-quality documents or images
        text_to_use = extract_result.text
        extraction_method = "tika"
        ocr_time = 0.0

        # Define image extensions that should always use OCR
        IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif'}
        file_ext = os.path.splitext(filename.lower())[1]
        is_image = file_ext in IMAGE_EXTENSIONS

        # For images with no text extracted, always try OCR
        # For PDFs with low quality extraction, check if OCR would help
        should_try_ocr = (
            settings.enhanced_ocr_enabled and
            (is_image or filename.lower().endswith('.pdf'))
        )

        if should_try_ocr:
            # Quick quality check before full analysis
            preliminary_analysis = self.intelligence.analyze(
                extract_result.text,
                {"page_count": extract_result.metadata.get("page_count", 0)}
            )

            # Force OCR for:
            # - Images with no/little text
            # - PDFs with no text (scanned documents)
            is_pdf = filename.lower().endswith('.pdf')
            no_text_extracted = len(extract_result.text.strip()) < 50

            force_ocr_for_image = is_image and no_text_extracted
            force_ocr_for_scanned_pdf = is_pdf and no_text_extracted

            # For documents with some text, use intelligence-based decision
            trigger_ocr = (
                force_ocr_for_image or
                force_ocr_for_scanned_pdf or
                self.intelligence.should_trigger_enhanced_ocr(
                    preliminary_analysis,
                    metadata={**metadata, **extract_result.metadata},
                    min_confidence=settings.enhanced_ocr_quality_threshold,
                )
            )

            if trigger_ocr:
                if force_ocr_for_image:
                    reason = "image with no text"
                elif force_ocr_for_scanned_pdf:
                    reason = "scanned PDF with no text"
                else:
                    reason = f"quality={preliminary_analysis.quality.value}"
                logger.info(
                    f"[{document_id}] Triggering enhanced OCR "
                    f"(reason={reason}, confidence={preliminary_analysis.confidence:.2f})"
                )

                ocr_start = time.time()
                try:
                    # Get OCR config based on analysis
                    ocr_config = self.intelligence.get_enhanced_ocr_config(
                        preliminary_analysis,
                        metadata={**metadata, **extract_result.metadata},
                    )

                    # Parse languages from config
                    ocr_languages = settings.enhanced_ocr_languages.split(",")

                    ocr_result = await self.extractor.extract_with_ocr(
                        file_bytes=file_bytes,
                        languages=ocr_languages,
                        use_hybrid=settings.enhanced_ocr_use_hybrid or ocr_config.get("use_hybrid", False),
                        preprocess=ocr_config.get("preprocess", True),
                        dpi=ocr_config.get("dpi", 300),
                    )

                    ocr_time = (time.time() - ocr_start) * 1000

                    # Use OCR result if:
                    # 1. Tika returned no text and OCR has text (forced OCR case)
                    # 2. OCR quality is better than Tika quality
                    use_ocr_result = (
                        ocr_result.success and
                        len(ocr_result.text.strip()) > 0 and
                        (
                            no_text_extracted or  # Tika had no text, use OCR
                            ocr_result.confidence > preliminary_analysis.confidence  # OCR is better
                        )
                    )

                    if use_ocr_result:
                        text_to_use = ocr_result.text
                        extraction_method = f"ocr_{ocr_result.engine}"
                        if no_text_extracted:
                            logger.info(
                                f"[{document_id}] OCR recovered text from scanned document: "
                                f"{len(ocr_result.text)} chars, confidence={ocr_result.confidence:.2f}"
                            )
                            warnings.append(
                                f"OCR used for scanned document: {len(ocr_result.text)} chars extracted"
                            )
                        else:
                            logger.info(
                                f"[{document_id}] Using OCR result: "
                                f"{len(ocr_result.text)} chars, "
                                f"confidence={ocr_result.confidence:.2f} (was {preliminary_analysis.confidence:.2f})"
                            )
                            warnings.append(
                                f"Enhanced OCR applied: confidence improved from "
                                f"{preliminary_analysis.confidence:.2f} to {ocr_result.confidence:.2f}"
                            )
                    else:
                        if no_text_extracted:
                            logger.warning(
                                f"[{document_id}] OCR also failed to extract text "
                                f"(success={ocr_result.success}, chars={len(ocr_result.text.strip())})"
                            )
                        else:
                            logger.info(
                                f"[{document_id}] Keeping Tika result "
                                f"(OCR confidence={ocr_result.confidence:.2f} <= Tika {preliminary_analysis.confidence:.2f})"
                            )
                        if ocr_result.warnings:
                            warnings.extend(ocr_result.warnings)

                except Exception as e:
                    logger.warning(f"[{document_id}] Enhanced OCR failed (non-blocking): {e}")
                    warnings.append(f"Enhanced OCR failed: {e}")
                    ocr_time = (time.time() - ocr_start) * 1000

        # Final check: if still no text after Tika + OCR, fail
        if not text_to_use.strip():
            logger.error(f"[{document_id}] No text extracted from {filename} (Tika + OCR both failed)")
            return IndexingResult(
                document_id=document_id,
                extraction_time_ms=extraction_time + ocr_time,
                total_time_ms=(time.time() - start_time) * 1000,
                success=False,
                errors=["No text content extracted (both Tika and OCR failed)"],
                warnings=warnings,
            )

        # Add extraction metadata
        # Propagate extraction_format (e.g. "markdown" from Docling) for downstream
        # consumers like SemanticChunker that adjust behavior based on format.
        extraction_backend = extract_result.metadata.get("extraction_backend", "tika")
        if extraction_method == "tika":
            extraction_method = extraction_backend

        enriched_metadata = {
            **metadata,
            "filename": filename,
            "extraction_strategy": extraction_strategy,
            "extraction_method": extraction_method,
            "detected_language": extract_result.language,
            **extract_result.metadata,
        }

        # Continue with text processing (pass indexing strategy for adaptive chunking)
        result = await self._process_text_internal(
            document_id=document_id,
            text=text_to_use,  # Use OCR text if it was better, otherwise Tika
            metadata=enriched_metadata,
            errors=errors,
            warnings=warnings,
            indexing_strategy=indexing_strategy,
        )

        # Update timing
        result.extracted_text = text_to_use
        result.extraction_language = extract_result.language
        result.extraction_characters = len(text_to_use)
        result.extraction_time_ms = extraction_time + ocr_time  # Include OCR time if used

        # === Stage 5: Visual Content Extraction (if enabled) ===
        # Only for PDFs and when multimodal is available and enabled
        should_extract_visuals = (
            extract_visuals if extract_visuals is not None
            else settings.multimodal_embedding_enabled
        )
        is_pdf = filename.lower().endswith('.pdf')

        if should_extract_visuals and is_pdf and MULTIMODAL_AVAILABLE and self._visual_extractor:
            visual_result = await self._extract_visuals(
                pdf_bytes=file_bytes,
                document_id=document_id,
            )

            if visual_result:
                result.visual_embeddings = visual_result.visual_embeddings
                result.images_count = visual_result.images_count
                result.tables_count = visual_result.tables_count
                result.diagrams_count = visual_result.diagrams_count
                result.visual_extraction_time_ms = visual_result.visual_extraction_time_ms
                result.warnings.extend(visual_result.warnings)

        result.total_time_ms = (time.time() - start_time) * 1000

        # Emit document.indexed event to the reactive event bus
        await self._emit_document_indexed(document_id, metadata, result)

        return result

    async def process_text(
        self,
        document_id: str,
        text: str,
        metadata: Dict[str, Any],
        collection_name: Optional[str] = None,
        indexing_strategy: Optional[Dict[str, Any]] = None,
    ) -> IndexingResult:
        """
        Process already-extracted text through the pipeline.

        Use this when text is already available (e.g., from database or API).

        Args:
            document_id: Unique document identifier
            text: Already-extracted document text
            metadata: Document metadata
            collection_name: Optional Weaviate collection override.
                If None, uses DOCUMENTS_COLLECTION.
            indexing_strategy: Optional strategy for chunking:
                - chunking_type: semantic, legal_sections, markdown_headers, paragraph
                - chunking_config: {target_chunk_size, overlap, ...}

        Returns:
            IndexingResult with chunks ready for embedding
        """
        start_time = time.time()

        # Store collection_name in metadata for downstream stages
        if collection_name:
            metadata["_collection_name"] = collection_name

        result = await self._process_text_internal(
            document_id=document_id,
            text=text,
            metadata=metadata,
            errors=[],
            warnings=[],
            indexing_strategy=indexing_strategy,
        )

        result.extracted_text = text
        result.extraction_characters = len(text)
        result.total_time_ms = (time.time() - start_time) * 1000

        # Emit document.indexed event to the reactive event bus
        await self._emit_document_indexed(document_id, metadata, result)

        return result

    async def _process_text_internal(
        self,
        document_id: str,
        text: str,
        metadata: Dict[str, Any],
        errors: List[str],
        warnings: List[str],
        indexing_strategy: Optional[Dict[str, Any]] = None,
    ) -> IndexingResult:
        """Internal text processing (analysis + chunking with adaptive strategy)"""

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

        # === Stage 3: Semantic Chunking (with adaptive strategy) ===
        logger.info(f"[{document_id}] Starting semantic chunking...")
        chunking_start = time.time()

        try:
            # Determine document type: use strategy if provided, otherwise detect
            doc_type = self._get_document_type_from_strategy(
                indexing_strategy=indexing_strategy,
                metadata=metadata,
                analysis=analysis,
            )

            # Log the chunking strategy being applied
            if indexing_strategy:
                chunking_type = indexing_strategy.get("chunking_type", "semantic")
                chunking_config = indexing_strategy.get("chunking_config", {})
                logger.info(
                    f"[{document_id}] Applying learned strategy: "
                    f"chunking_type={chunking_type}, config={chunking_config}"
                )
            elif self._get_sector_strategy():
                sector_strategy = self._get_sector_strategy()
                logger.info(
                    f"[{document_id}] Applying sector strategy: "
                    f"chunk_strategy={sector_strategy.get('chunking_type')}, "
                    f"chunk_size={sector_strategy.get('chunking_config', {}).get('target_chunk_size')}"
                )
                # Use sector strategy as indexing_strategy
                indexing_strategy = sector_strategy
            else:
                logger.info(f"[{document_id}] Using default strategy for type={doc_type}")

            # Prepare metadata for chunks
            chunk_metadata = {
                **metadata,
                "document_id": document_id,
                "quality": analysis.quality.value,
                "confidence": analysis.confidence,
            }

            # Note: SemanticChunker uses instance-level config (target_chunk_size, overlap)
            # Strategy-based chunking config would require chunker reconfiguration
            # For now, use chunker's default settings

            # Chunk the document
            chunks = self.chunker.chunk_document(
                text=text_for_chunking,
                metadata=chunk_metadata,
                document_type=doc_type,
            )

            chunking_time = (time.time() - chunking_start) * 1000

            logger.info(f"[{document_id}] Created {len(chunks)} chunks (type={doc_type})")

            # Enrich chunks with analysis metadata and strategy info
            for i, chunk in enumerate(chunks):
                chunk.metadata["chunk_index"] = i
                chunk.metadata["total_chunks"] = len(chunks)
                chunk.metadata["has_tables"] = analysis.has_tables
                chunk.metadata["has_headers"] = analysis.has_headers
                # Add strategy info for retrieval debugging
                if indexing_strategy:
                    chunk.metadata["chunking_type"] = indexing_strategy.get("chunking_type")
                    chunk.metadata["strategy_applied"] = True

        except Exception as e:
            logger.error(f"[{document_id}] Chunking failed: {e}")
            errors.append(f"Chunking failed: {e}")

            return IndexingResult(
                document_id=document_id,
                analysis=analysis,
                analysis_time_ms=analysis_time,
                chunking_time_ms=(time.time() - chunking_start) * 1000,
                success=False,
                errors=errors,
                warnings=warnings,
            )

        # === Stage 3b: Parent-Child Chunking (optional, replaces flat chunks) ===
        if settings.parent_child_chunking_enabled:
            try:
                from .parent_child_chunker import parent_child_chunker

                pc_start = time.time()
                children = parent_child_chunker.chunk_with_parents(
                    text=text_for_chunking,
                    metadata={**metadata, "document_id": document_id},
                    doc_type=str(doc_type) if doc_type else "general",
                )
                pc_time = (time.time() - pc_start) * 1000

                if children:
                    # Convert ChildChunk to DocumentChunk format for downstream compatibility
                    from .semantic_chunker import DocumentChunk
                    chunks = [
                        DocumentChunk(
                            content=child.content,
                            metadata={
                                **child.metadata,
                                "parent_chunk_id": child.parent_chunk_id,
                                "parent_content": child.parent_content,
                                "child_index": child.child_index,
                            },
                            section_title=child.section_title,
                            chunk_index=child.chunk_index,
                            total_chunks=child.total_chunks,
                            token_count=child.token_count,
                        )
                        for child in children
                    ]
                    logger.info(
                        f"[{document_id}] Parent-child chunking: {len(chunks)} children "
                        f"({pc_time:.0f}ms)"
                    )
            except Exception as e:
                logger.warning(f"[{document_id}] Parent-child chunking failed, using flat chunks: {e}")

        # === Stage 4: Contextual Retrieval (Anthropic pattern) ===
        contextual_prefix = None
        contextual_time = 0.0

        if settings.contextual_retrieval_enabled and CONTEXTUAL_RETRIEVAL_AVAILABLE:
            logger.info(f"[{document_id}] Applying contextual retrieval...")
            contextual_start = time.time()

            try:
                # Analyze document to detect type and extract entities
                context_result = await contextual_retrieval.analyze_document(
                    document_id=document_id,
                    text=text_for_chunking,
                    metadata=metadata,
                    use_llm=settings.contextual_retrieval_use_llm,
                )

                contextual_prefix = context_result.context_prefix

                # Apply context to chunks - modify chunk content with context prefix
                for chunk in chunks:
                    # Prepend context to chunk content for embedding
                    original_text = chunk.content
                    chunk.content = f"{contextual_prefix} {original_text}"

                    # Enrich chunk metadata with contextual info
                    chunk.metadata["contextual_prefix_applied"] = True
                    chunk.metadata["original_text_length"] = len(original_text)

                contextual_time = (time.time() - contextual_start) * 1000

                logger.info(
                    f"[{document_id}] Applied contextual retrieval: "
                    f"document_type={context_result.document_type}, "
                    f"prefix={len(contextual_prefix)} chars, time={contextual_time:.1f}ms"
                )

            except Exception as e:
                logger.warning(f"[{document_id}] Contextual retrieval failed (non-blocking): {e}")
                warnings.append(f"Contextual retrieval failed: {e}")
                contextual_time = (time.time() - contextual_start) * 1000

        # === Stage 4a: Per-Chunk LLM Context Enrichment (Anthropic full pattern) ===
        # When CONTEXTUAL_RETRIEVAL_USE_LLM=true, each chunk gets a unique 1-2 sentence
        # context generated by the LLM, situating it within the document.
        # This complements Stage 4's domain-level prefix with per-chunk specificity.
        if settings.contextual_retrieval_use_llm and chunks:
            try:
                from .context_enricher import context_enricher

                enricher_start = time.time()
                chunks = await context_enricher.enrich_chunks(
                    full_text=text_for_chunking,
                    chunks=chunks,
                    doc_metadata={
                        "title": metadata.get("title", metadata.get("filename", "Documento")),
                    },
                )
                enricher_time = (time.time() - enricher_start) * 1000

                logger.info(
                    f"[{document_id}] Per-chunk LLM enrichment completed "
                    f"({enricher_time:.0f}ms for {len(chunks)} chunks)"
                )
            except Exception as e:
                logger.warning(f"[{document_id}] Per-chunk context enrichment failed (non-blocking): {e}")
                warnings.append(f"Per-chunk context enrichment failed: {e}")

        # === Stage 4.5: Entity Extraction (LangExtract) ===
        # Extract entities (DNI, NIE, CIF, PERSON, ORGANIZATION, etc.) before knowledge extraction
        extracted_entities = []
        entity_extraction_time = 0.0

        if self._knowledge_extraction_enabled and (indexing_strategy or {}).get("extract_entities", True):
            logger.info(f"[{document_id}] Extracting named entities...")
            entity_start = time.time()

            try:
                # Call LangExtract client for entity extraction
                langextract_result = await intelligence_client.extract_entities(
                    text=text_for_chunking,
                    document_type=metadata.get("document_type", "general"),
                    filename=metadata.get("filename"),
                    use_llm=True,  # Use LLM for rich entity extraction
                )

                if langextract_result.success and langextract_result.entities:
                    extracted_entities = langextract_result.entities
                    logger.info(
                        f"[{document_id}] Extracted {len(extracted_entities)} entities: "
                        f"{', '.join(set(e.get('type', 'UNKNOWN') for e in extracted_entities[:10]))}"
                    )

                entity_extraction_time = (time.time() - entity_start) * 1000

            except Exception as e:
                logger.warning(f"[{document_id}] Entity extraction failed (non-blocking): {e}")
                warnings.append(f"Entity extraction failed: {e}")
                entity_extraction_time = (time.time() - entity_start) * 1000

        # === Stage 5: Knowledge Extraction ===
        knowledge_result = None
        knowledge_time = 0.0

        if self._knowledge_extraction_enabled:
            logger.info(f"[{document_id}] Extracting knowledge entities...")
            knowledge_start = time.time()

            try:
                knowledge_result = await self.knowledge_extractor.extract_from_document(
                    document_id=document_id,
                    extracted_entities=extracted_entities,  # Use entities from LangExtract
                    content=text_for_chunking,
                    document_type=metadata.get("document_type", "general"),
                )

                knowledge_time = (time.time() - knowledge_start) * 1000

                logger.info(
                    f"[{document_id}] Extracted {knowledge_result.entities_count} entities, "
                    f"{knowledge_result.relationships_count} relationships"
                )

            except Exception as e:
                logger.warning(f"[{document_id}] Knowledge extraction failed (non-blocking): {e}")
                warnings.append(f"Knowledge extraction failed: {e}")
                knowledge_time = (time.time() - knowledge_start) * 1000

        # === Stage 5: Hierarchical Summary Generation ===
        document_summary = None
        summary_time = 0.0

        if settings.rag_hierarchical_enabled:
            logger.info(f"[{document_id}] Generating document summary for hierarchical RAG...")
            summary_start = time.time()

            try:
                document_summary = await hierarchical_indexer.generate_document_summary(
                    document_id=document_id,
                    title=metadata.get("title", "Untitled"),
                    full_text=text_for_chunking,
                    document_type=metadata.get("document_type", "general"),
                    total_chunks=len(chunks),
                    metadata=metadata,
                )

                if document_summary:
                    # Index the summary in Weaviate
                    await hierarchical_indexer.index_summary(document_summary)
                    logger.info(
                        f"[{document_id}] Generated and indexed document summary "
                        f"({len(document_summary.summary)} chars, {len(document_summary.key_topics)} topics)"
                    )
                else:
                    warnings.append("Summary generation returned None (LLM may be unavailable)")

                summary_time = (time.time() - summary_start) * 1000

            except Exception as e:
                logger.warning(f"[{document_id}] Summary generation failed (non-blocking): {e}")
                warnings.append(f"Summary generation failed: {e}")
                summary_time = (time.time() - summary_start) * 1000

        return IndexingResult(
            document_id=document_id,
            analysis=analysis,
            chunks=chunks,
            contextual_prefix=contextual_prefix,
            knowledge_result=knowledge_result,
            document_summary=document_summary,
            analysis_time_ms=analysis_time,
            chunking_time_ms=chunking_time,
            contextual_time_ms=contextual_time,
            knowledge_extraction_time_ms=knowledge_time,
            summary_generation_time_ms=summary_time,
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

    @staticmethod
    def _get_sector_strategy() -> Optional[Dict[str, Any]]:
        """
        Get chunking strategy from ACTIVE_SECTOR env var.

        Returns an indexing_strategy dict if a sector is configured,
        or None for generic mode.
        """
        import os
        active_sector = os.getenv("ACTIVE_SECTOR", "").strip().lower()
        if not active_sector:
            return None

        # Sector → chunking parameters mapping
        sector_strategies = {
            "legal": {
                "chunking_type": "legal_sections",
                "chunking_config": {
                    "target_chunk_size": 1500,
                    "overlap": 200,
                },
            },
            "medical": {
                "chunking_type": "paragraph",
                "chunking_config": {
                    "target_chunk_size": 1200,
                    "overlap": 150,
                },
            },
            "documental": {
                "chunking_type": "semantic",
                "chunking_config": {
                    "target_chunk_size": 1000,
                    "overlap": 100,
                },
            },
        }

        return sector_strategies.get(active_sector)

    def _get_document_type_from_strategy(
        self,
        indexing_strategy: Optional[Dict[str, Any]],
        metadata: Dict[str, Any],
        analysis: DocumentAnalysis,
    ) -> Optional[DocumentType]:
        """
        Get document type from indexing strategy, falling back to detection.

        The Data Learning System provides optimized chunking types based on
        learned patterns from the connector's content model.

        Strategy chunking_type mapping:
        - legal_sections → LEGAL_CONTRACT (clause-aware chunking)
        - legal_brief → LEGAL_BRIEF
        - technical → TECHNICAL_MANUAL (header-aware)
        - markdown_headers → TECHNICAL_MANUAL
        - financial → FINANCIAL_REPORT (table-preserving)
        - medical → MEDICAL_RECORD
        - semantic → GENERAL (default semantic chunking)
        - paragraph → GENERAL (simple paragraph splitting)
        """
        if indexing_strategy:
            chunking_type = indexing_strategy.get("chunking_type", "").lower()

            # Map strategy chunking types to DocumentType
            strategy_type_mapping = {
                "legal_sections": DocumentType.LEGAL_CONTRACT,
                "legal_contract": DocumentType.LEGAL_CONTRACT,
                "legal_brief": DocumentType.LEGAL_BRIEF,
                "technical": DocumentType.TECHNICAL_MANUAL,
                "markdown_headers": DocumentType.TECHNICAL_MANUAL,
                "financial": DocumentType.FINANCIAL_REPORT,
                "medical": DocumentType.MEDICAL_RECORD,
            }

            if chunking_type in strategy_type_mapping:
                return strategy_type_mapping[chunking_type]

        # Fall back to metadata/analysis detection
        return self._detect_document_type(metadata, analysis)

    async def process_file_from_url(
        self,
        document_id: str,
        file_url: str,
        filename: str,
        metadata: Dict[str, Any],
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
            user_id=user_id,
            strategy=extraction_strategy,
        )

        extraction_time = (time.time() - extraction_start) * 1000

        if not extract_result.success:
            return IndexingResult(
                document_id=document_id,
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
        user_id: Optional[str] = None,
    ) -> List[IndexingResult]:
        """
        Process multiple files in batch.

        Args:
            files: List of dicts with document_id, file_bytes, filename, metadata
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

    async def _emit_document_indexed(
        self,
        document_id: str,
        metadata: Dict[str, Any],
        result: "IndexingResult",
    ):
        """Emit a document.indexed event to the reactive event bus (fire-and-forget)."""
        try:
            from app.services.event_publisher import publish_event
            await publish_event(
                event_type="document.indexed",
                payload={
                    "doc_id": document_id,
                    "collection": metadata.get("_collection_name", ""),
                    "title": metadata.get("title", ""),
                    "filename": metadata.get("filename", ""),
                    "chunks_count": len(result.chunks),
                    "tags": metadata.get("tags", []),
                    # Enrichment for FalkorDB auto-index
                    "file_path": metadata.get("external_path", ""),
                    "domain": "",
                    "semantic_type": metadata.get("document_type", ""),
                    "connector_id": metadata.get("connector_id", ""),
                    "connector_type": metadata.get("connector_type", ""),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to emit document.indexed event: {e}")

    async def _extract_visuals(
        self,
        pdf_bytes: bytes,
        document_id: str,
    ) -> Optional["VisualExtractionPipelineResult"]:
        """
        Extract visual content from PDF and generate embeddings.

        This method:
        1. Extracts images, tables, and diagrams from the PDF
        2. Generates embeddings using Qwen3-VL-Embedding
        3. Returns results ready for Weaviate storage

        Args:
            pdf_bytes: PDF file content
            document_id: Document identifier

        Returns:
            VisualExtractionPipelineResult or None if extraction fails
        """
        import time
        start_time = time.time()

        if not self._visual_extractor or not self._embedding_service:
            logger.debug(f"[{document_id}] Visual extraction not available")
            return None

        if not settings.multimodal_embedding_enabled:
            logger.debug(f"[{document_id}] Multimodal embedding disabled")
            return None

        try:
            # Step 1: Extract visual content from PDF
            logger.info(f"[{document_id}] Extracting visual content...")
            visual_result = await self._visual_extractor.extract_visuals(
                pdf_bytes=pdf_bytes,
                document_id=document_id,
            )

            if not visual_result.success or not visual_result.visuals:
                if visual_result.errors:
                    logger.warning(f"[{document_id}] Visual extraction warnings: {visual_result.errors}")
                return VisualExtractionPipelineResult(
                    visual_embeddings=[],
                    images_count=0,
                    tables_count=0,
                    diagrams_count=0,
                    visual_extraction_time_ms=(time.time() - start_time) * 1000,
                    warnings=visual_result.warnings,
                )

            logger.info(
                f"[{document_id}] Found {len(visual_result.visuals)} visual elements: "
                f"{visual_result.images_count} images, {visual_result.tables_count} tables, "
                f"{visual_result.diagrams_count} diagrams"
            )

            # Step 2: Generate embeddings for visual content
            visual_contents = [v.to_visual_content() for v in visual_result.visuals]
            embedding_results = await self._embedding_service.embed_visual_content(visual_contents)

            # Step 3: Create VisualEmbeddingItems for successful embeddings
            visual_embeddings = []
            for visual, emb_result in zip(visual_result.visuals, embedding_results):
                if emb_result.success and emb_result.vectors:
                    visual_embeddings.append(VisualEmbeddingItem(
                        content_type=visual.content_type.value,
                        embedding=emb_result.vectors[0],
                        page_number=visual.page_number,
                        bbox=visual.bbox,
                        caption=visual.caption,
                        metadata={
                            "width": visual.width,
                            "height": visual.height,
                            "detection_method": visual.detection_method,
                            "embedding_model": emb_result.model_used,
                            "embedding_dimensions": emb_result.dimensions,
                            **visual.metadata,
                        },
                    ))

            processing_time = (time.time() - start_time) * 1000

            logger.info(
                f"[{document_id}] Generated {len(visual_embeddings)} visual embeddings "
                f"({processing_time:.0f}ms)"
            )

            return VisualExtractionPipelineResult(
                visual_embeddings=visual_embeddings,
                images_count=visual_result.images_count,
                tables_count=visual_result.tables_count,
                diagrams_count=visual_result.diagrams_count,
                visual_extraction_time_ms=processing_time,
                warnings=visual_result.warnings,
            )

        except Exception as e:
            logger.error(f"[{document_id}] Visual extraction failed: {e}")
            return VisualExtractionPipelineResult(
                visual_embeddings=[],
                images_count=0,
                tables_count=0,
                diagrams_count=0,
                visual_extraction_time_ms=(time.time() - start_time) * 1000,
                warnings=[f"Visual extraction failed: {e}"],
            )


@dataclass
class VisualExtractionPipelineResult:
    """Result of visual extraction in the pipeline"""
    visual_embeddings: List[VisualEmbeddingItem]
    images_count: int = 0
    tables_count: int = 0
    diagrams_count: int = 0
    visual_extraction_time_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)


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

#!/usr/bin/env python3
"""
Reindexer script that reprocesses document contents through the same pipeline used on upload.

It downloads each file from the storage service, extracts text via DocumentService,
and reindexes the document into Weaviate/Elasticsearch so searches pick up full content.
"""

import asyncio
import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.db.database import SessionLocal
from app.db.models import Document, Tenant
from app.schemas.enums import IndexingStatus
from app.services.document_service import DocumentService
from app.services.elasticsearch_client import elasticsearch_client
from app.services.langextract_client import langextract_client

logging.basicConfig(level=logging.INFO)
# Silence verbose SQLAlchemy engine/pool logs during batch runs
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


REINDEX_BATCH_SIZE = int(os.getenv("REINDEX_BATCH_SIZE", "50"))


async def _reindex_single_document(
    tenant_id: str,
    db: Session,
    document: Document,
) -> bool:
    """
    Download, extract and reindex a single document using DocumentService.

    Returns True on success, False otherwise.
    """
    try:
        doc_service = DocumentService(
            tenant_id=tenant_id,
            user_id=str(document.created_by) if document.created_by else None,
        )

        title = document.title or document.filename or "Documento"
        file_ext = document.file_type or (
            document.filename.split(".")[-1].lower() if document.filename and "." in document.filename else ""
        )

        if not file_ext:
            raise ValueError("No se pudo determinar la extensión del archivo")

        logger.info("⬇️  Descargando documento %s (%s)", document.id, document.file_path)
        file_contents = await asyncio.to_thread(
            doc_service.storage_service.download_file,
            document.file_path,
        )

        if not file_contents:
            raise ValueError("No se pudo descargar el archivo o está vacío")

        # Extraer texto para indexación
        logger.info("📝 Extrayendo texto del documento %s", document.id)
        extraction = await doc_service.text_extraction_client.extract_text(
            file_bytes=file_contents,
            filename=document.filename or f"{document.id}.{file_ext}",
            file_extension=file_ext,
        )
        text_content = extraction.text

        if not text_content or not text_content.strip():
            raise ValueError("No se pudo extraer texto del documento")

        logger.info(
            "🧮 Documento %s: texto extraído con %s caracteres",
            document.id,
            len(text_content),
        )

        # Marcar como en procesamiento antes de iniciar indexación
        document.indexed = IndexingStatus.PROCESSING
        document.indexing_error = None
        db.flush()

        # Persist preview & extraction metadata similar to upload pipeline
        document.content = text_content[:10000]
        extraction_metadata = {
            "language": extraction.language,
            "characters": extraction.characters,
            **(extraction.metadata or {}),
        }
        current_metadata = document.document_metadata or {}
        current_metadata["text_extraction"] = extraction_metadata
        document.document_metadata = current_metadata
        db.flush()

        # Extract entities via LangExtract to keep parity with ingestion flow
        try:
            entities_result = await langextract_client.extract_entities(
                text=text_content,
                document_type=document.category or "general",
                filename=document.filename,
            )
            if entities_result.get("success"):
                document.extracted_entities = entities_result.get("extractions", [])
                logger.info(
                    "🧠 Documento %s: extraídas %s entidades",
                    document.id,
                    len(document.extracted_entities or []),
                )
            else:
                document.extracted_entities = []
        except Exception as entity_exc:  # pylint: disable=broad-except
            logger.warning("⚠️ Falló extracción de entidades para %s: %s", document.id, entity_exc)
            document.extracted_entities = []
        db.flush()

        # Preparar metadatos comunes
        document_metadata = {
            "doc_id": str(document.id),
            "tenant_id": tenant_id,
            "title": title,
            "filename": document.filename,
            "description": document.description,
            "file_type": document.file_type,
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "updated_at": document.updated_at.isoformat() if document.updated_at else None,
            "file_size": document.file_size,
            "mime_type": document.mime_type,
            "category": document.category,
            "tags": [tag.name for tag in document.tags] if hasattr(document, "tags") and document.tags else [],
            "created_by": str(document.created_by),
        }

        logger.info("📥 Indexando en Weaviate documento %s", document.id)
        vector_success = await doc_service.vector_service.add_document(
            doc_id=str(document.id),
            text=text_content,
            metadata=document_metadata,
        )

        if not vector_success:
            raise ValueError("VectorService.add_document devolvió False")

        # Indexar en Elasticsearch
        es_metadata = {
            "file_type": document.file_type,
            "category": document.category,
            "tags": [tag.name for tag in document.tags] if hasattr(document, "tags") and document.tags else [],
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "updated_at": document.updated_at.isoformat() if document.updated_at else None,
            "file_size": document.file_size,
            "tenant_id": str(document.tenant_id),
        }

        logger.info("📥 Indexando en Elasticsearch documento %s", document.id)
        es_success = await elasticsearch_client.index_document(
            tenant_id=tenant_id,
            doc_id=str(document.id),
            title=title,
            content=text_content,
            description=document.description,
            metadata=es_metadata,
        )

        if not es_success:
            raise ValueError("Elasticsearch index_document devolvió False")

        document.indexed = IndexingStatus.INDEXED
        document.indexing_error = None
        db.commit()

        logger.info("✅ Documento %s reindexado correctamente", document.id)
        return True

    except httpx.HTTPStatusError as http_err:
        error_detail = ""
        try:
            error_detail = http_err.response.json().get("detail")  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            error_detail = http_err.response.text or str(http_err)

        logger.error(
            "❌ Error reindexando documento %s: extracción rechazó la petición (%s) - %s",
            document.id,
            http_err.response.status_code,
            error_detail,
        )
        db.rollback()
        retry_document = (
            db.query(Document)
            .filter(Document.id == document.id)
            .one()
        )
        retry_document.indexed = IndexingStatus.INDEXING_ERROR
        retry_document.indexing_error = (
            f"Text extraction failed ({http_err.response.status_code}): {error_detail}"
        )
        db.commit()
        return False

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("❌ Error reindexando documento %s: %s", document.id, exc)
        db.rollback()
        retry_document = (
            db.query(Document)
            .filter(Document.id == document.id)
            .one()
        )
        retry_document.indexed = IndexingStatus.INDEXING_ERROR
        retry_document.indexing_error = str(exc)
        db.commit()
        return False


async def reindex_tenant(tenant: Tenant) -> tuple[int, int]:
    """
    Reindex every document for a tenant.

    Returns tuple(success_count, failure_count).
    """
    tenant_id = str(tenant.id)

    with SessionLocal() as db:
        base_query = (
            db.query(Document)
            .filter(Document.tenant_id == tenant.id)
            .order_by(Document.created_at)
        )
        total_documents = base_query.count()

        if not total_documents:
            logger.info("📂 Tenant %s no tiene documentos; nada que reindexar", tenant_id)
            return 0, 0

        status_counter_query = (
            db.query(Document.indexed, func.count(Document.id))
            .filter(Document.tenant_id == tenant.id)
            .group_by(Document.indexed)
        )
        status_counter = {
            IndexingStatus(status).name if status is not None else "UNKNOWN": count
            for status, count in status_counter_query
        }
        status_summary = ", ".join(f"{name}={count}" for name, count in sorted(status_counter.items()))

        logger.info(
            "🏢 Tenant %s (%s) - %s documentos | estados actuales: %s",
            tenant_id,
            tenant.name,
            total_documents,
            status_summary or "sin registros",
        )

        document_ids = [
            doc_id for (doc_id,) in base_query.with_entities(Document.id).all()
        ]

        successes = 0
        failures = 0
        for batch_start in range(0, len(document_ids), REINDEX_BATCH_SIZE):
            batch_ids = document_ids[batch_start: batch_start + REINDEX_BATCH_SIZE]
            batch_number = (batch_start // REINDEX_BATCH_SIZE) + 1
            logger.info(
                "🧩 Procesando lote %s de tamaño %s para tenant %s",
                batch_number,
                len(batch_ids),
                tenant_id,
            )

            for relative_index, doc_id in enumerate(batch_ids, start=batch_start + 1):
                logger.info(
                    "🔄 Reindexando documento %s (%s/%s) para tenant %s",
                    doc_id,
                    relative_index,
                    total_documents,
                    tenant_id,
                )

                with SessionLocal() as doc_session:
                    document = (
                        doc_session.query(Document)
                        .options(selectinload(Document.tags))
                        .filter(Document.id == doc_id)
                        .one_or_none()
                    )

                    if not document:
                        logger.warning("⚠️ Documento %s no encontrado durante reindexado", doc_id)
                        failures += 1
                        continue

                    result = await _reindex_single_document(tenant_id, doc_session, document)

                if result:
                    successes += 1
                else:
                    failures += 1

    return successes, failures


async def main():
    logger.info("🚀 Iniciando reindexado completo (contenido real de documentos)")

    with SessionLocal() as db:
        tenants = db.query(Tenant).order_by(Tenant.created_at).all()

    if not tenants:
        logger.info("No se encontraron tenants en la base de datos")
        return

    logger.info("⚙️ Tamaño de lote configurado en %s documentos", REINDEX_BATCH_SIZE)
    logger.info("📊 Encontrados %s tenants para reindexar", len(tenants))

    total_success = 0
    total_failures = 0

    for tenant in tenants:
        success, failure = await reindex_tenant(tenant)
        total_success += success
        total_failures += failure
        logger.info(
            "🧾 Resumen tenant %s: %s éxitos, %s fallos",
            tenant.id,
            success,
            failure,
        )

    logger.info(
        "🎉 Reindexado finalizado | éxitos=%s fallos=%s",
        total_success,
        total_failures,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Reindexador interrumpido por el usuario")

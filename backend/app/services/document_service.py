import logging
import os
import uuid
import datetime
import io
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.models import Document, Tag
from app.db.database import SessionLocal
from app.schemas.enums import IndexingStatus
from app.services.storage_factory import StorageServiceFactory
from app.services.embedding_service import EmbeddingService
from app.services.weaviate_client import weaviate_client
from app.services.text_extraction_client import TextExtractionClient
from app.services.elasticsearch_client import elasticsearch_client  # Added Elasticsearch Client
from app.services.langextract_client import langextract_client

logger = logging.getLogger(__name__)


class DocumentService:
    """Servicio para gestión de documentos"""
    
    def __init__(self, tenant_id: str = None, user_id: str = None):
        """
        Inicializa el servicio de documentos.
        
        Args:
            tenant_id: ID del tenant (debe ser un UUID válido)
            user_id: ID del usuario actual
        """
        # Si tenant_id es None o el string "default", obtener el UUID real del tenant por defecto
        if not tenant_id or tenant_id == settings.DEFAULT_TENANT:
            from app.db.database import SessionLocal
            from app.db.models import Tenant
            db = SessionLocal()
            try:
                default_tenant = db.query(Tenant).filter(Tenant.name == settings.DEFAULT_TENANT).first()
                if default_tenant:
                    self.tenant_id = str(default_tenant.id)
                else:
                    raise ValueError(f"Default tenant '{settings.DEFAULT_TENANT}' not found in database")
                
                # Crear storage service con la sesión de BD para obtener bucket_name
                self.storage_service = StorageServiceFactory.create_storage_service(self.tenant_id, user_id, db)
            finally:
                db.close()
        else:
            self.tenant_id = tenant_id
            # Para tenants existentes, crear nueva sesión para el storage service
            from app.db.database import SessionLocal
            db = SessionLocal()
            try:
                self.storage_service = StorageServiceFactory.create_storage_service(self.tenant_id, user_id, db)
            finally:
                db.close()
            
        self.user_id = user_id
        self.embedding_service = EmbeddingService(self.tenant_id)
        self.collection_name = f"Nouxcube_{self.tenant_id.replace('-', '_')}_documents"
        self.text_extraction_client = TextExtractionClient(self.tenant_id, self.user_id)

    async def _validate_file(self, file: UploadFile, filename: str) -> tuple[str, bytes, int]:
        """
        Validates the uploaded file, checks its extension and size.
        Returns the file extension, its contents as bytes, and its size.
        """
        if not file:
            raise HTTPException(status_code=400, detail="Archivo no proporcionado")

        contents = await file.read()
        await file.seek(0) 

        file_size = len(contents)
        file_ext = os.path.splitext(filename)[1][1:].lower() if "." in filename else ""

        if not file_ext or file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de archivo no permitido. Permitidos: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )
        
        if file_size == 0:
             raise HTTPException(status_code=400, detail="El archivo está vacío.")

        if file_size > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Tamaño de archivo excede el límite de {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB"
            )
        
        return file_ext, contents, file_size

    def _create_document_record(
        self, 
        db: Session, 
        title: str, 
        description: Optional[str], 
        filename: str, 
        file_ext: str, 
        file_size: int, 
        tags: Optional[List[str]]
    ) -> Document:
        """
        Creates the Document ORM object, generates doc_id, constructs file_path,
        and handles tags. Adds to session but does not commit.
        """
        doc_id = str(uuid.uuid4())
        file_path = filename

        db_document = Document(
            id=doc_id,
            title=title,
            description=description or "",
            filename=filename,
            file_path=file_path,
            file_type=file_ext,
            file_size=file_size,
            tenant_id=self.tenant_id,
            created_by=self.user_id,
            indexed=IndexingStatus.PROCESSING
        )

        if tags:
            for tag_name in tags:
                if tag_name:
                    tag = db.query(Tag).filter(
                        Tag.name == tag_name,
                        Tag.tenant_id == self.tenant_id
                    ).first()
                    if not tag:
                        tag = Tag(name=tag_name, tenant_id=self.tenant_id)
                        db.add(tag)
                        db.flush()
                    db_document.tags.append(tag)
        
        db.add(db_document)
        db.flush()
        db.refresh(db_document)
        return db_document

    async def _upload_file_to_storage(
        self,
        file_contents: bytes,
        file_path: str,
        doc_id: str,
        title: str,
        file_ext: str
    ):
        """
        Uploads the file content to the storage service.
        """
        file_obj = io.BytesIO(file_contents)
        storage_metadata = {
            "doc_id": doc_id,
            "title": title,
            "content_type": f"application/{file_ext}"
        }

        upload_result = await asyncio.to_thread(
            self.storage_service.upload_file,
            file=file_obj,
            object_name=file_path,
            metadata=storage_metadata
        )

        if not upload_result:
            raise Exception("Failed to store document file in cloud storage.")

    async def _extract_and_index_text(
        self, 
        db: Session, 
        db_document: Document, 
        file_contents: bytes, 
        file_ext: str, 
        title: str
    ):
        """
        Extracts text and indexes it directly via LangChain/Qdrant.
        Also extracts entities from the document content.
        """
        try:
            extraction = await self.text_extraction_client.extract_text(
                file_bytes=file_contents,
                filename=db_document.filename or f"{db_document.id}.{file_ext}",
                file_extension=file_ext,
            )
            document_text = extraction.text
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Failed to extract text for document %s: %s", db_document.id, exc)
            db_document.indexed = IndexingStatus.INDEXING_ERROR
            db_document.extracted_entities = []
            raise

        if not document_text:
            db_document.indexed = IndexingStatus.INDEXING_ERROR
            db_document.extracted_entities = []
            return

        # Store the extracted text preview
        db_document.content = document_text[:10000]

        # Store metadata from extraction
        extraction_metadata = {
            "language": extraction.language,
            "characters": extraction.characters,
            **(extraction.metadata or {}),
        }
        current_metadata = db_document.document_metadata or {}
        current_metadata["text_extraction"] = extraction_metadata
        db_document.document_metadata = current_metadata

        # Extract entities using LangExtract microservice
        try:
            entities_result = await langextract_client.extract_entities(
                text=document_text,
                document_type=db_document.category or "general",
                filename=db_document.filename,
            )
            if entities_result.get("success"):
                db_document.extracted_entities = entities_result.get("extractions", [])
                logger.info(
                    "Extracted %s entities from document %s",
                    len(db_document.extracted_entities or []),
                    db_document.id,
                )
            else:
                db_document.extracted_entities = []
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to extract entities from document %s: %s", db_document.id, exc)
            db_document.extracted_entities = []

        # Prepare metadata for downstream services
        document_metadata = {
            "doc_id": str(db_document.id),
            "tenant_id": self.tenant_id,
            "title": title,
            "filename": db_document.filename,
            "description": db_document.description,
            "file_type": file_ext,
            "created_at": db_document.created_at.isoformat() if db_document.created_at else None,
            "updated_at": db_document.updated_at.isoformat() if db_document.updated_at else None,
            "file_size": db_document.file_size,
            "mime_type": db_document.mime_type,
            "category": db_document.category,
            "created_by": self.user_id or "system",
        }

        # Parallel Indexing: Weaviate + Elasticsearch
        logger.info(f"Starting parallel indexing for document {db_document.id}")

        # Task 1: Weaviate (Vector Store)
        weaviate_document_data = {
            "doc_id": str(db_document.id),
            "text": document_text,
            "metadata": document_metadata,
        }
        weaviate_task = weaviate_client.add_document(
            collection_name=self.collection_name,
            document_data=weaviate_document_data
        )

        # Task 2: Elasticsearch (Keyword/Hybrid) with ACL
        # For new documents, default to owner-only access (created_by)
        # ACL will be synced later when permissions are granted
        elasticsearch_task = elasticsearch_client.index_document(
            tenant_id=self.tenant_id,
            doc_id=str(db_document.id),
            title=title,
            content=document_text,
            description=db_document.description,
            metadata=document_metadata,
            # ACL fields - new documents start with owner-only access
            created_by=self.user_id or "system",
            acl_user_ids=[],
            acl_role_ids=[],
            acl_everyone=True  # Default to everyone for backward compatibility
        )

        # Execute both
        results = await asyncio.gather(weaviate_task, elasticsearch_task, return_exceptions=True)
        
        weaviate_result = results[0]
        es_result = results[1]

        # Analyze results
        weaviate_success = isinstance(weaviate_result, dict) and weaviate_result.get("success", False)
        es_success = isinstance(es_result, bool) and es_result

        # Log outcomes
        if isinstance(weaviate_result, Exception):
            logger.error(f"❌ Weaviate indexing failed for {db_document.id}: {weaviate_result}")
        elif weaviate_success:
            logger.info(f"✅ Weaviate indexing success for {db_document.id}")
        else:
            logger.warning(f"⚠️ Weaviate indexing returned False for {db_document.id}")

        if isinstance(es_result, Exception):
            logger.error(f"❌ Elasticsearch indexing failed for {db_document.id}: {es_result}")
        elif es_success:
            logger.info(f"✅ Elasticsearch indexing success for {db_document.id}")
        else:
            logger.warning(f"⚠️ Elasticsearch indexing returned False for {db_document.id}")

        # Final Status Determination
        if es_success: # Elasticsearch is primary for general search indexing
            db_document.indexed = IndexingStatus.INDEXED
            if not weaviate_success:
                logger.warning(f"⚠️ Document {db_document.id} indexed in ES but Weaviate failed. Will retry vectorization.")
                # TODO: Trigger background retry for Weaviate if it fails
        else:
            db_document.indexed = IndexingStatus.INDEXING_ERROR
            logger.error(f"❌ Document {db_document.id} failed to index in Elasticsearch (primary). Weaviate status: {weaviate_success}")
   
    async def process_document(
        self, 
        db: Session,
        file: UploadFile, 
        title: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Procesa un documento con commits parciales para evitar que la vectorización bloquee la subida.
        """
        db_document = None
        
        try:
            filename = file.filename
            
            # 1. Validate file
            file_ext, file_contents, file_size = await self._validate_file(file, filename)

            # 2. Create document record in DB
            db_document = self._create_document_record(
                db=db,
                title=title,
                description=description,
                filename=filename,
                file_ext=file_ext,
                file_size=file_size,
                tags=tags
            )
            
            doc_id_str = str(db_document.id)
            file_path_str = db_document.file_path

            # 3. Upload file to storage
            await self._upload_file_to_storage(
                file_contents=file_contents,
                file_path=file_path_str,
                doc_id=doc_id_str,
                title=db_document.title,
                file_ext=db_document.file_type
            )

            # 4. COMMIT PARTIAL - Document is now successfully uploaded and available
            db.commit()
            db.refresh(db_document)
            logger.info(f"Document {doc_id_str} uploaded successfully, starting vectorization...")

            # 5. Try vectorization (separate operation - won't block upload success)
            try:
                await self._extract_and_index_text(
                    db=db,
                    db_document=db_document,
                    file_contents=file_contents,
                    file_ext=db_document.file_type,
                    title=db_document.title
                )
                # If vectorization succeeds, status is already set to INDEXED
                db.commit()
                logger.info(f"Document {doc_id_str} vectorization completed successfully")
                
            except Exception as vector_error:
                # Vectorization failed, but document upload was successful
                logger.error(f"Vectorization failed for document {doc_id_str}: {vector_error}")
                db_document.indexed = IndexingStatus.INDEXING_ERROR
                db.commit()
                
                # Don't raise the error - document upload was successful
                logger.warning(f"Document {doc_id_str} uploaded but vectorization failed - can retry later")
            
            # 6. Return successful response (regardless of vectorization outcome)
            db.refresh(db_document)
            return {
                "id": str(db_document.id),
                "title": db_document.title,
                "description": db_document.description,
                "filename": db_document.filename,
                "file_type": db_document.file_type,
                "file_size": db_document.file_size,
                "tenant_id": str(db_document.tenant_id),
                "created_by": str(db_document.created_by),
                "indexed": db_document.indexed,
                "created_at": db_document.created_at.isoformat(),
                "updated_at": db_document.updated_at.isoformat(),
                "tags": [tag.name for tag in db_document.tags],
                "extracted_entities": db_document.extracted_entities or []
            }
            
        except HTTPException:
            # HTTP exceptions should be re-raised as-is
            if db_document:
                db.rollback()
            raise
            
        except Exception as e:
            # Only rollback if we haven't committed the document yet
            if db_document:
                try:
                    # Check if document was committed (has an ID and is in DB)
                    existing = db.query(Document).filter(Document.id == db_document.id).first()
                    if not existing:
                        db.rollback()
                except:
                    db.rollback()
            else:
                db.rollback()
                
            logger.exception(f"Error processing document: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while processing the document.")
    
    def get_document(self, db: Session, doc_id: str) -> Dict[str, Any]: # Added db: Session
        """
        Obtiene información detallada de un documento.
        """
        # db = SessionLocal() # Removed
        
        try:
            document = db.query(Document).options(
                joinedload(Document.tags)
            ).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # TODO: Implementar chunks cuando el modelo DocumentChunk esté disponible
            # chunks = db.query(DocumentChunk).filter(
            #     DocumentChunk.document_id == doc_id
            # ).order_by(
            #     DocumentChunk.chunk_index
            # ).limit(3).all()
            
            chunks_dict = []
            # for chunk in chunks:
            #     chunks_dict.append({
            #         "id": chunk.id,
            #         "document_id": str(chunk.document_id),
            #         "chunk_index": chunk.chunk_index,
            #         "content": chunk.content
            #     })
            
            result = {
                "id": str(document.id),
                "title": document.title,
                "description": document.description,
                "filename": document.filename,
                "file_path": document.file_path,
                "file_type": document.file_type,
                "file_size": document.file_size,
                "tenant_id": str(document.tenant_id),
                "created_by": str(document.created_by),
                "indexed": document.indexed,
                "created_at": document.created_at.isoformat(),
                "updated_at": document.updated_at.isoformat(),
                "tags": [{"id": tag.id, "name": tag.name, "tenant_id": str(tag.tenant_id), "created_at": tag.created_at.isoformat()} for tag in document.tags],
                "extracted_entities": document.extracted_entities or [],
                "preview_chunks": chunks_dict
            }
            
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while retrieving the document.")
        # finally: # Removed
            # db.close() # Removed
    
    async def delete_document(self, db: Session, doc_id: str) -> Dict[str, Any]: # Added db: Session
        """
        Elimina un documento y todos sus datos asociados.
        """
        # db = SessionLocal() # Removed
        
        try:
            document = db.query(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Eliminar archivo del almacenamiento
            storage_deleted = await asyncio.to_thread(self.storage_service.delete_file, document.file_path)
            if not storage_deleted:
                logger.warning(f"Failed to delete file from storage: {document.file_path}")
            
            # Eliminar del vector store
            await weaviate_client.delete_document(collection_name=self.collection_name, doc_id=doc_id)
            
            # Note: Document chunks are managed by the vector service, not in the main database
            # Eliminar documento de la base de datos
            db.delete(document)
            db.commit()
            
            message = f"Document {doc_id} deleted successfully"
            if not storage_deleted:
                message += " (warning: file may still exist in storage)"
            return {"message": message}
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Error deleting document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while deleting the document.")
        # finally: # Removed
            # db.close() # Removed
    
    def generate_summary(self, db: Session, doc_id: str) -> Dict[str, str]: # Added db: Session
        """
        Genera un resumen del documento utilizando el LLM.
        """
        # db = SessionLocal() # Removed
        
        try:
            # Verificar acceso al documento
            document = db.query(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # TODO: Implementar chunks cuando el modelo DocumentChunk esté disponible
            # chunks = db.query(DocumentChunk).filter(
            #     DocumentChunk.document_id == doc_id
            # ).order_by(
            #     DocumentChunk.chunk_index
            # ).all()
            
            chunks = []  # Temporal: lista vacía
            
            # TODO: Implementar con chunks cuando esté disponible
            # Por ahora, usar descripción del documento como contenido
            text = document.description or "Document content not available yet. Chunks feature is being implemented."
            
            if len(text) < 10:  # Si es muy corto, usar un texto más descriptivo
                text = f"Document '{document.title}' content will be available when the chunks feature is implemented."
            
            # Limitar longitud si es demasiado grande
            max_chars = 100000
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            
            summary = self._create_simple_summary(text, document.filename or document.id)
            
            return {"summary": summary}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error generating summary for document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while generating the summary.")
        # finally: # Removed
            # db.close() # Removed
    
    def add_tag(self, db: Session, doc_id: str, tag_name: str) -> Dict[str, str]: # Added db: Session
        """
        Añade una etiqueta a un documento.
        """
        # db = SessionLocal() # Removed
        
        try:
            document = db.query(Document).options(
                joinedload(Document.tags)
            ).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Verificar si la etiqueta ya está asignada
            for tag in document.tags:
                if tag.name == tag_name:
                    return {"message": f"Tag '{tag_name}' already assigned to document"}
            
            # Buscar etiqueta existente o crear nueva
            tag = db.query(Tag).filter(
                Tag.name == tag_name,
                Tag.tenant_id == self.tenant_id
            ).first()
            
            if not tag:
                tag = Tag(name=tag_name, tenant_id=self.tenant_id)
                db.add(tag)
            
            # Asignar etiqueta al documento
            document.tags.append(tag)
            db.commit()
            
            return {"message": f"Tag '{tag_name}' added to document"}
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Error adding tag to document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while adding the tag.")
        # finally: # Removed
            # db.close() # Removed
    
    def remove_tag(self, db: Session, doc_id: str, tag_name: str) -> Dict[str, str]: # Added db: Session
        """
        Elimina una etiqueta de un documento.
        """
        # db = SessionLocal() # Removed
        
        try:
            document = db.query(Document).options(
                joinedload(Document.tags)
            ).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Buscar etiqueta
            tag = db.query(Tag).filter(
                Tag.name == tag_name,
                Tag.tenant_id == self.tenant_id
            ).first()
            
            if not tag:
                raise HTTPException(status_code=404, detail=f"Tag '{tag_name}' not found")
            
            # Eliminar asociación
            if tag in document.tags:
                document.tags.remove(tag)
                db.commit()
                return {"message": f"Tag '{tag_name}' removed from document"}
            else:
                return {"message": f"Tag '{tag_name}' not assigned to document"}
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Error removing tag from document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while removing the tag.")

    def _create_simple_summary(self, text: str, filename: str) -> str:
        """Fallback summary generator when Elysia is unavailable in sync contexts."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        preview = " ".join(lines[:3]) if lines else text
        preview = preview[:220] if preview else ""
        if not preview:
            preview = "Resumen no disponible."
        return f"{filename}: {preview}"
        # finally: # Removed
            # db.close() # Removed
    
    # get_signed_download_url method removed for security reasons
    # Use stream_document endpoint instead for all document access
    
    # get_signed_upload_url method removed for security reasons
    # Use direct upload via /upload endpoint instead

    def get_documents(
        self, 
        db: "Session", # Added db: Session
        page: int = 1, 
        per_page: int = 10, 
        search: str = None,
        tags: List[str] = None, 
        date_from: str = None, 
        date_to: str = None
    ) -> Dict[str, Any]:
        """
        Obtiene lista paginada de documentos con filtros opcionales.
        
        Args:
            db: SQLAlchemy Session
            page: Número de página
            per_page: Documentos por página
            search: Texto para buscar en título, descripción y filename
            tags: Lista de etiquetas para filtrar
            date_from: Fecha inicial (formato ISO)
            date_to: Fecha final (formato ISO)
            
        Returns:
            Diccionario con documentos y metadatos de paginación
        """
        # db = next(get_db()) # Removed this line
        
        try:
            query = db.query(Document).filter(Document.tenant_id == self.tenant_id)
            
            # Aplicar filtros
            if search:
                search_filter = f"%{search}%"
                query = query.filter(
                    (Document.title.ilike(search_filter)) |
                    (Document.description.ilike(search_filter)) |
                    (Document.filename.ilike(search_filter))
                )
            
            if tags:
                for tag_name in tags:
                    query = query.filter(Document.tags.any(Tag.name == tag_name))
            
            if date_from:
                try:
                    from_date = datetime.datetime.fromisoformat(date_from)
                    query = query.filter(Document.created_at >= from_date)
                except ValueError:
                    # logger.warning(f"Invalid date_from format: {date_from}")
                    raise HTTPException(status_code=400, detail="Invalid date format provided for 'date_from'. Please use ISO format.")
            
            if date_to:
                try:
                    to_date = datetime.datetime.fromisoformat(date_to)
                    query = query.filter(Document.created_at <= to_date)
                except ValueError:
                    # logger.warning(f"Invalid date_to format: {date_to}")
                    raise HTTPException(status_code=400, detail="Invalid date format provided for 'date_to'. Please use ISO format.")
            
            # Contar total
            total = query.count()
            
            # Aplicar paginación
            offset = (page - 1) * per_page
            documents = query.order_by(Document.created_at.desc()).offset(offset).limit(per_page).all()
            
            # Convertir a diccionarios
            documents_dict = []
            for doc in documents:
                doc_dict = {
                    "id": str(doc.id),
                    "title": doc.title,
                    "description": doc.description,
                    "filename": doc.filename,
                    "file_path": doc.file_path,
                    "file_type": doc.file_type,
                    "file_size": doc.file_size,
                    "indexed": doc.indexed,
                    "created_at": doc.created_at.isoformat(),
                    "updated_at": doc.updated_at.isoformat(),
                    "tags": [tag.name for tag in doc.tags]
                }
                documents_dict.append(doc_dict)
            
            return {
                "documents": documents_dict,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "pages": (total + per_page - 1) // per_page
                }
            }
            
        except Exception as e:
            logger.exception(f"Error getting documents: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while retrieving documents.")
    
    def get_document(self, db: "Session", doc_id: str) -> Document: # Changed return type
        """
        Obtiene información detallada de un documento.
        
        Args:
            db: SQLAlchemy Session
            doc_id: ID del documento
            
        Returns:
            Modelo Document de SQLAlchemy
        """
        
        try:
            document = db.query(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Devolver directamente el objeto documento
            # Pydantic se encargará de la serialización usando from_attributes=True
            return document
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while retrieving the document.")
    
    def generate_summary(self, db: "Session", doc_id: str) -> Dict[str, str]: # Added db: Session
        """
        Genera un resumen del documento utilizando el LLM.
        
        Args:
            db: SQLAlchemy Session
            doc_id: ID del documento
            
        Returns:
            Texto del resumen
        """
        # db = next(get_db()) # Removed this line
        
        try:
            # Verificar acceso al documento
            document = db.query(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # TODO: Implementar chunks cuando el modelo DocumentChunk esté disponible
            # chunks = db.query(DocumentChunk).filter(
            #     DocumentChunk.document_id == doc_id
            # ).order_by(
            #     DocumentChunk.chunk_index
            # ).all()
            
            chunks = []  # Temporal: lista vacía
            
            # TODO: Implementar con chunks cuando esté disponible
            # Por ahora, usar descripción del documento como contenido
            text = document.description or "Document content not available yet. Chunks feature is being implemented."
            
            if len(text) < 10:  # Si es muy corto, usar un texto más descriptivo
                text = f"Document '{document.title}' content will be available when the chunks feature is implemented."
            
            # Limitar longitud si es demasiado grande
            max_chars = 100000  # Ajustar según limitaciones del LLM
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            
            summary = self._create_simple_summary(text, document.filename or document.id)
            
            return {"summary": summary}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error generating summary for document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while generating the summary.")
    
    def add_tag(self, db: "Session", doc_id: str, tag_name: str) -> Dict[str, str]: # Added db: Session
        """
        Añade una etiqueta a un documento.
        
        Args:
            db: SQLAlchemy Session
            doc_id: ID del documento
            tag_name: Nombre de la etiqueta
            
        Returns:
            Mensaje de confirmación
        """
        # db = next(get_db()) # Removed this line
        
        try:
            document = db.query(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Verificar si la etiqueta ya está asignada
            for tag in document.tags:
                if tag.name == tag_name:
                    return {"message": f"Tag '{tag_name}' already assigned to document"}
            
            # Buscar etiqueta existente o crear nueva
            tag = db.query(Tag).filter(
                Tag.name == tag_name,
                Tag.tenant_id == self.tenant_id
            ).first()
            
            if not tag:
                tag = Tag(name=tag_name, tenant_id=self.tenant_id)
                db.add(tag)
            
            # Asignar etiqueta al documento
            document.tags.append(tag)
            db.commit()
            
            return {"message": f"Tag '{tag_name}' added to document"}
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Error adding tag to document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while adding the tag.")
    
    def remove_tag(self, db: "Session", doc_id: str, tag_name: str) -> Dict[str, str]: # Added db: Session
        """
        Elimina una etiqueta de un documento.
        
        Args:
            db: SQLAlchemy Session
            doc_id: ID del documento
            tag_name: Nombre de la etiqueta
            
        Returns:
            Mensaje de confirmación
        """
        # db = next(get_db()) # Removed this line
        
        try:
            document = db.query(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Buscar etiqueta
            tag = db.query(Tag).filter(
                Tag.name == tag_name,
                Tag.tenant_id == self.tenant_id
            ).first()
            
            if not tag:
                raise HTTPException(status_code=404, detail=f"Tag '{tag_name}' not found")
            
            # Eliminar asociación
            if tag in document.tags:
                document.tags.remove(tag)
                db.commit()
                return {"message": f"Tag '{tag_name}' removed from document"}
            else:
                return {"message": f"Tag '{tag_name}' not assigned to document"}
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Error removing tag from document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while removing the tag.")
    
    def get_signed_download_url(self, db: "Session", doc_id: str) -> Dict[str, Any]: # Added db: Session
        """
        Genera una URL firmada para descargar un documento.
        
        Args:
            db: SQLAlchemy Session
            doc_id: ID del documento
            
        Returns:
            URL firmada y fecha de expiración
        """
        # db = next(get_db()) # Removed this line
        
        try:
            document = db.query(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Generar URL firmada
            url, expires_at = self.storage_service.generate_download_signed_url(
                object_name=document.file_path
            )
            
            return {
                "url": url,
                "expires_at": expires_at.isoformat(),
                "filename": document.filename
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error generating signed URL for document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while generating the download URL.")
    
    def get_signed_upload_url(self, filename: str, content_type: str) -> Dict[str, Any]:
        """
        Genera una URL firmada para subir un documento.
        
        Args:
            filename: Nombre del archivo
            content_type: Tipo de contenido MIME
            
        Returns:
            URL firmada, fecha de expiración y path de destino
        """
        try:
            # Verificar extensión
            file_ext = os.path.splitext(filename)[1][1:].lower() if "." in filename else ""
            if not file_ext or file_ext not in settings.ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Tipo de archivo no permitido. Permitidos: {', '.join(settings.ALLOWED_EXTENSIONS)}"
                )
            
            # Generar ID único para el futuro documento
            doc_id = str(uuid.uuid4())
            
            # Definir ruta en el almacenamiento
            file_path = f"documents/{doc_id}/{filename}"
            
            # Generar URL firmada
            url, expires_at = self.storage_service.generate_upload_signed_url(
                object_name=file_path,
                content_type=content_type
            )
            
            return {
                "upload_url": url,
                "expires_at": expires_at.isoformat(),
                "file_path": file_path,
                "doc_id": doc_id
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error generating signed upload URL: {str(e)}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred while generating the upload URL.")

import logging
import os
import uuid
import datetime
import io
from typing import List, Dict, Any, Optional, BinaryIO, Union
from fastapi import UploadFile, HTTPException
import PyPDF2
from docx import Document as DocxDocument
import csv
import openpyxl
import chardet

from app.core.config import settings
from app.db.models import Document, DocumentChunk, Tag
from app.db.database import get_db
from app.services.storage_service import StorageService
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class DocumentService:
    """Servicio para gestión de documentos"""
    
    def __init__(self, tenant_id: str = None, user_id: str = None):
        """
        Inicializa el servicio de documentos.
        
        Args:
            tenant_id: ID del tenant
            user_id: ID del usuario actual
        """
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        self.user_id = user_id
        self.storage_service = StorageService(tenant_id)
        self.embedding_service = EmbeddingService(tenant_id)
        self.llm_service = LLMService()
    
    async def process_document(
        self, 
        file: UploadFile, 
        title: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Procesa un documento: lo almacena, extrae texto, genera embeddings y lo indexa.
        
        Args:
            file: Objeto de archivo
            title: Título del documento
            description: Descripción del documento
            tags: Lista de etiquetas
            
        Returns:
            Información del documento procesado
        """
        db = next(get_db())
        
        try:
            # Validar el archivo
            if not file:
                raise HTTPException(status_code=400, detail="Archivo no proporcionado")
            
            filename = file.filename
            file_size = 0  # Se calculará después
            
            # Obtener el tipo de archivo
            file_ext = os.path.splitext(filename)[1][1:].lower() if "." in filename else ""
            if not file_ext or file_ext not in settings.ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Tipo de archivo no permitido. Permitidos: {', '.join(settings.ALLOWED_EXTENSIONS)}"
                )
            
            # Generar ID único para el documento
            doc_id = str(uuid.uuid4())
            
            # Definir ruta en el almacenamiento
            file_path = f"documents/{doc_id}/{filename}"
            
            # Leer contenido del archivo para procesamiento
            contents = await file.read()
            file_size = len(contents)
            
            if file_size > settings.MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tamaño de archivo excede el límite de {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB"
                )
            
            # Crear registro en la base de datos
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
                indexed=0  # No indexado aún
            )
            
            # Añadir etiquetas
            if tags:
                for tag_name in tags:
                    if tag_name:
                        # Buscar etiqueta existente o crear nueva
                        tag = db.query(Tag).filter(
                            Tag.name == tag_name,
                            Tag.tenant_id == self.tenant_id
                        ).first()
                        
                        if not tag:
                            tag = Tag(name=tag_name, tenant_id=self.tenant_id)
                            db.add(tag)
                            db.flush()  # Para obtener el ID
                        
                        db_document.tags.append(tag)
            
            db.add(db_document)
            db.commit()
            db.refresh(db_document)
            
            # Subir archivo al almacenamiento
            file_obj = io.BytesIO(contents)
            storage_metadata = {
                "doc_id": doc_id,
                "title": title,
                "content_type": f"application/{file_ext}"
            }
            
            upload_success = self.storage_service.upload_file(
                file=file_obj,
                object_name=file_path,
                metadata=storage_metadata
            )
            
            if not upload_success:
                raise Exception("Failed to store document file")
            
            # Extraer texto del documento
            file_obj.seek(0)  # Rebobinar para lectura
            document_text = self._extract_text(file_obj, file_ext)
            
            # Actualizar documento con estado de indexación
            if document_text:
                # Dividir en chunks y guardar
                chunks_data = self.embedding_service.chunk_text(document_text)
                
                for i, chunk_data in enumerate(chunks_data):
                    chunk = DocumentChunk(
                        document_id=doc_id,
                        chunk_index=i,
                        content=chunk_data["text"]
                    )
                    db.add(chunk)
                
                # Generar embeddings e indexar
                indexing_success = self.embedding_service.add_document(
                    doc_id=doc_id,
                    text=document_text,
                    metadata={
                        "doc_id": doc_id,
                        "title": title,
                        "file_type": file_ext,
                        "tenant_id": self.tenant_id
                    }
                )
                
                # Actualizar estado de indexación
                db_document.indexed = 1 if indexing_success else 2  # 1: indexado, 2: error
                db.commit()
            else:
                db_document.indexed = 2  # Error: no se pudo extraer texto
                db.commit()
            
            # Formatear respuesta
            return {
                "id": str(db_document.id),
                "title": db_document.title,
                "description": db_document.description,
                "filename": db_document.filename,
                "file_type": db_document.file_type,
                "file_size": db_document.file_size,
                "indexed": db_document.indexed,
                "created_at": db_document.created_at.isoformat(),
                "tags": [tag.name for tag in db_document.tags]
            }
            
        except HTTPException as http_exc:
            db.rollback()
            raise http_exc
        except Exception as e:
            db.rollback()
            logger.exception(f"Error processing document: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")
    
    def _extract_text(self, file: BinaryIO, file_type: str) -> str:
        """
        Extrae texto de un archivo según su tipo.
        
        Args:
            file: Objeto de archivo
            file_type: Tipo de archivo (pdf, docx, txt, etc.)
            
        Returns:
            Texto extraído del documento
        """
        try:
            # Rebobinar para asegurar lectura desde el inicio
            file.seek(0)
            
            # Extraer texto según el tipo de archivo
            if file_type == 'pdf':
                return self._extract_pdf_text(file)
            elif file_type in ['docx', 'doc']:
                return self._extract_docx_text(file)
            elif file_type == 'txt':
                # Detectar codificación
                content = file.read()
                detected = chardet.detect(content)
                encoding = detected['encoding'] or 'utf-8'
                return content.decode(encoding, errors='ignore')
            elif file_type == 'csv':
                return self._extract_csv_text(file)
            elif file_type in ['xlsx', 'xls']:
                return self._extract_excel_text(file)
            elif file_type == 'md':
                content = file.read()
                return content.decode('utf-8', errors='ignore')
            else:
                logger.warning(f"Unsupported file type for text extraction: {file_type}")
                return ""
                
        except Exception as e:
            logger.exception(f"Error extracting text from document: {str(e)}")
            return ""
    
    def _extract_pdf_text(self, file: BinaryIO) -> str:
        """Extrae texto de un archivo PDF"""
        text = ""
        try:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text() + "\n\n"
            return text
        except Exception as e:
            logger.exception(f"Error extracting text from PDF: {str(e)}")
            return ""
    
    def _extract_docx_text(self, file: BinaryIO) -> str:
        """Extrae texto de un archivo DOCX"""
        try:
            doc = DocxDocument(file)
            text = ""
            for para in doc.paragraphs:
                text += para.text + "\n"
            return text
        except Exception as e:
            logger.exception(f"Error extracting text from DOCX: {str(e)}")
            return ""
    
    def _extract_csv_text(self, file: BinaryIO) -> str:
        """Extrae texto de un archivo CSV"""
        try:
            text = ""
            # Detectar codificación
            file.seek(0)
            sample = file.read(4096)
            detected = chardet.detect(sample)
            encoding = detected['encoding'] or 'utf-8'
            
            # Rebobinar archivo
            file.seek(0)
            content = file.read().decode(encoding, errors='ignore')
            file_content = io.StringIO(content)
            
            # Detectar delimitador
            dialect = csv.Sniffer().sniff(file_content.read(1024))
            file_content.seek(0)
            
            csv_reader = csv.reader(file_content, dialect)
            for row in csv_reader:
                text += ", ".join(row) + "\n"
            return text
        except Exception as e:
            logger.exception(f"Error extracting text from CSV: {str(e)}")
            return ""
    
    def _extract_excel_text(self, file: BinaryIO) -> str:
        """Extrae texto de un archivo Excel"""
        try:
            text = ""
            workbook = openpyxl.load_workbook(file, read_only=True)
            
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                text += f"Sheet: {sheet_name}\n"
                
                for row in sheet.iter_rows(values_only=True):
                    row_text = ", ".join([str(cell) if cell is not None else "" for cell in row])
                    text += row_text + "\n"
                
                text += "\n"
            
            return text
        except Exception as e:
            logger.exception(f"Error extracting text from Excel: {str(e)}")
            return ""
    
    def get_documents(
        self, 
        page: int = 1, 
        per_page: int = 10, 
        tags: List[str] = None, 
        date_from: str = None, 
        date_to: str = None
    ) -> Dict[str, Any]:
        """
        Obtiene lista paginada de documentos con filtros opcionales.
        
        Args:
            page: Número de página
            per_page: Documentos por página
            tags: Lista de etiquetas para filtrar
            date_from: Fecha inicial (formato ISO)
            date_to: Fecha final (formato ISO)
            
        Returns:
            Diccionario con documentos y metadatos de paginación
        """
        db = next(get_db())
        
        try:
            query = db.query(Document).filter(Document.tenant_id == self.tenant_id)
            
            # Aplicar filtros
            if tags:
                for tag_name in tags:
                    query = query.filter(Document.tags.any(Tag.name == tag_name))
            
            if date_from:
                try:
                    from_date = datetime.datetime.fromisoformat(date_from)
                    query = query.filter(Document.created_at >= from_date)
                except ValueError:
                    logger.warning(f"Invalid date_from format: {date_from}")
            
            if date_to:
                try:
                    to_date = datetime.datetime.fromisoformat(date_to)
                    query = query.filter(Document.created_at <= to_date)
                except ValueError:
                    logger.warning(f"Invalid date_to format: {date_to}")
            
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
            raise HTTPException(status_code=500, detail=f"Error retrieving documents: {str(e)}")
    
    def get_document(self, doc_id: str) -> Dict[str, Any]:
        """
        Obtiene información detallada de un documento.
        
        Args:
            doc_id: ID del documento
            
        Returns:
            Diccionario con información del documento
        """
        db = next(get_db())
        
        try:
            document = db.query(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Obtener primeros chunks para vista previa
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == doc_id
            ).order_by(
                DocumentChunk.chunk_index
            ).limit(3).all()
            
            chunks_dict = []
            for chunk in chunks:
                chunks_dict.append({
                    "id": chunk.id,
                    "document_id": str(chunk.document_id),
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content
                })
            
            result = {
                "id": str(document.id),
                "title": document.title,
                "description": document.description,
                "filename": document.filename,
                "file_path": document.file_path,
                "file_type": document.file_type,
                "file_size": document.file_size,
                "indexed": document.indexed,
                "created_at": document.created_at.isoformat(),
                "updated_at": document.updated_at.isoformat(),
                "tags": [tag.name for tag in document.tags],
                "preview_chunks": chunks_dict
            }
            
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error retrieving document: {str(e)}")
    
    def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """
        Elimina un documento y todos sus datos asociados.
        
        Args:
            doc_id: ID del documento
            
        Returns:
            Mensaje de confirmación
        """
        db = next(get_db())
        
        try:
            document = db.query(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Eliminar archivo del almacenamiento
            self.storage_service.delete_file(document.file_path)
            
            # Eliminar del vector store
            self.embedding_service.delete_document(doc_id)
            
            # Eliminar de la base de datos
            db.delete(document)
            db.commit()
            
            return {"message": f"Document {doc_id} deleted successfully"}
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.exception(f"Error deleting document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")
    
    def generate_summary(self, doc_id: str) -> Dict[str, str]:
        """
        Genera un resumen del documento utilizando el LLM.
        
        Args:
            doc_id: ID del documento
            
        Returns:
            Texto del resumen
        """
        db = next(get_db())
        
        try:
            # Verificar acceso al documento
            document = db.query(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Obtener texto de los chunks
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == doc_id
            ).order_by(
                DocumentChunk.chunk_index
            ).all()
            
            if not chunks:
                raise HTTPException(status_code=404, detail="Document content not found")
            
            # Unir texto de los chunks
            text = "\n\n".join([chunk.content for chunk in chunks])
            
            # Limitar longitud si es demasiado grande
            max_chars = 100000  # Ajustar según limitaciones del LLM
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            
            # Generar resumen usando el servicio LLM
            summary = self.llm_service.summarize_text(text)
            
            return {"summary": summary}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error generating summary for document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")
    
    def add_tag(self, doc_id: str, tag_name: str) -> Dict[str, str]:
        """
        Añade una etiqueta a un documento.
        
        Args:
            doc_id: ID del documento
            tag_name: Nombre de la etiqueta
            
        Returns:
            Mensaje de confirmación
        """
        db = next(get_db())
        
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
            raise HTTPException(status_code=500, detail=f"Error adding tag: {str(e)}")
    
    def remove_tag(self, doc_id: str, tag_name: str) -> Dict[str, str]:
        """
        Elimina una etiqueta de un documento.
        
        Args:
            doc_id: ID del documento
            tag_name: Nombre de la etiqueta
            
        Returns:
            Mensaje de confirmación
        """
        db = next(get_db())
        
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
            raise HTTPException(status_code=500, detail=f"Error removing tag: {str(e)}")
    
    def get_signed_download_url(self, doc_id: str) -> Dict[str, Any]:
        """
        Genera una URL firmada para descargar un documento.
        
        Args:
            doc_id: ID del documento
            
        Returns:
            URL firmada y fecha de expiración
        """
        db = next(get_db())
        
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
            raise HTTPException(status_code=500, detail=f"Error generating download URL: {str(e)}")
    
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
            raise HTTPException(status_code=500, detail=f"Error generating upload URL: {str(e)}")
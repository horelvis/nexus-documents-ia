"""
Async version of DocumentService for use with AsyncSession
"""
import logging
import os
import uuid
import datetime
import io
import asyncio
from typing import List, Dict, Any, Optional, BinaryIO, Union
from fastapi import UploadFile, HTTPException
import PyPDF2
from docx import Document as DocxDocument
import csv
import openpyxl
import chardet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload, joinedload

from app.core.config import settings
from app.db.models import Document, Tag, Tenant
from app.db.async_database import AsyncSessionLocal
from app.schemas.enums import IndexingStatus
from app.services.async_storage_factory import AsyncStorageServiceFactory
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class AsyncDocumentService:
    """Async version of Document Service"""
    
    def __init__(self, tenant_id: str = None, user_id: str = None):
        """
        Initialize async document service
        Note: The async init pattern requires using a factory method
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.storage_service = None
        self.embedding_service = None
        self.vector_service = None
        self.llm_service = None
        self._initialized = False
    
    @classmethod
    async def create(cls, tenant_id: str = None, user_id: str = None):
        """
        Factory method to create and initialize AsyncDocumentService
        """
        service = cls(tenant_id, user_id)
        await service._initialize()
        return service
    
    async def _initialize(self):
        """Initialize the service with async operations"""
        # If tenant_id is None or "default", get the real UUID
        if not self.tenant_id or self.tenant_id == settings.DEFAULT_TENANT:
            async with AsyncSessionLocal() as db:
                stmt = select(Tenant).filter(Tenant.name == settings.DEFAULT_TENANT)
                result = await db.execute(stmt)
                default_tenant = result.scalar_one_or_none()
                
                if default_tenant:
                    self.tenant_id = str(default_tenant.id)
                else:
                    raise ValueError(f"Default tenant '{settings.DEFAULT_TENANT}' not found in database")
                
                # Create storage service using async factory
                self.storage_service = await AsyncStorageServiceFactory.create_storage_service(
                    self.tenant_id, self.user_id, db
                )
        else:
            async with AsyncSessionLocal() as db:
                self.storage_service = await AsyncStorageServiceFactory.create_storage_service(
                    self.tenant_id, self.user_id, db
                )
        
        self.embedding_service = EmbeddingService(self.tenant_id)
        self.vector_service = VectorService(self.tenant_id, self.user_id)
        self.llm_service = LLMService()
        self._initialized = True
    
    async def _validate_file(self, file: UploadFile, filename: str) -> tuple[str, bytes, int]:
        """Validates the uploaded file"""
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
    
    async def get_documents(
        self, 
        db: AsyncSession,
        page: int = 1,
        per_page: int = 10,
        search: Optional[str] = None,
        tags: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get paginated list of documents with filters"""
        try:
            # Base query
            query = select(Document).filter(
                Document.tenant_id == self.tenant_id
            ).options(
                selectinload(Document.tags),
                selectinload(Document.creator)
            )
            
            # Apply filters
            if search:
                query = query.filter(
                    or_(
                        Document.title.ilike(f"%{search}%"),
                        Document.description.ilike(f"%{search}%")
                    )
                )
            
            if category:
                query = query.filter(Document.category == category)
            
            if tags:
                # Join with tags
                query = query.join(Document.tags).filter(
                    Tag.name.in_(tags)
                )
            
            if date_from:
                date_from_obj = datetime.datetime.fromisoformat(date_from)
                query = query.filter(Document.created_at >= date_from_obj)
            
            if date_to:
                date_to_obj = datetime.datetime.fromisoformat(date_to)
                query = query.filter(Document.created_at <= date_to_obj)
            
            # Count total
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await db.execute(count_query)
            total = total_result.scalar()
            
            # Apply pagination
            offset = (page - 1) * per_page
            query = query.offset(offset).limit(per_page).order_by(Document.created_at.desc())
            
            # Execute query
            result = await db.execute(query)
            documents = result.scalars().all()
            
            # Convert to dict
            items = []
            for doc in documents:
                doc_dict = {
                    "id": str(doc.id),
                    "title": doc.title,
                    "description": doc.description,
                    "filename": doc.filename,
                    "file_type": doc.file_type,
                    "file_size": doc.file_size,
                    "mime_type": doc.mime_type,
                    "indexed": self._get_indexed_status_string(doc.indexed),
                    "category": doc.category if hasattr(doc, 'category') else None,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                    "tags": [{"id": str(tag.id), "name": tag.name} for tag in doc.tags],
                    "created_by": {
                        "id": str(doc.creator.id),
                        "email": doc.creator.email,
                        "full_name": doc.creator.full_name
                    } if doc.creator else None
                }
                items.append(doc_dict)
            
            return {
                "items": items,
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page
            }
            
        except Exception as e:
            logger.error(f"Error getting documents: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def upload_document(
        self,
        db: AsyncSession,
        file: UploadFile,
        title: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None
    ) -> Document:
        """Upload a new document"""
        try:
            # Validate file
            file_ext, contents, file_size = await self._validate_file(file, file.filename)
            
            # Generate unique filename
            file_id = str(uuid.uuid4())
            stored_filename = f"{file_id}.{file_ext}"
            
            # Create document record
            doc = Document(
                id=uuid.uuid4(),
                title=title,
                description=description,
                filename=file.filename,
                file_path=stored_filename,
                file_type=file_ext,
                file_size=file_size,
                mime_type=file.content_type,
                category=category,
                tenant_id=self.tenant_id,
                created_by=self.user_id
            )
            
            # Upload to storage
            upload_result = await self.storage_service.upload_file(
                file_data=io.BytesIO(contents),
                file_name=stored_filename,
                content_type=file.content_type
            )
            
            if not upload_result["success"]:
                raise HTTPException(status_code=500, detail="Error uploading file")
            
            # Add to database
            db.add(doc)
            await db.flush()
            
            # Handle tags
            if tags:
                for tag_name in tags:
                    # Check if tag exists
                    stmt = select(Tag).filter(
                        Tag.name == tag_name,
                        Tag.tenant_id == self.tenant_id
                    )
                    result = await db.execute(stmt)
                    tag = result.scalar_one_or_none()
                    
                    if not tag:
                        tag = Tag(
                            id=uuid.uuid4(),
                            name=tag_name,
                            tenant_id=self.tenant_id
                        )
                        db.add(tag)
                    
                    doc.tags.append(tag)
            
            await db.commit()
            await db.refresh(doc)
            
            # Extract text and index asynchronously
            asyncio.create_task(self._process_document_async(str(doc.id), contents, file_ext))
            
            return doc
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error uploading document: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _process_document_async(self, doc_id: str, contents: bytes, file_ext: str):
        """Process document in background"""
        try:
            # Extract text
            text = await self._extract_text_async(contents, file_ext)
            
            if text:
                # Generate embeddings
                embeddings = await self.embedding_service.generate_embeddings(text)
                
                # Store in vector DB
                await self.vector_service.add_document(
                    document_id=doc_id,
                    content=text,
                    embeddings=embeddings,
                    metadata={"file_type": file_ext}
                )
                
                # Update document status
                async with AsyncSessionLocal() as db:
                    stmt = select(Document).filter(Document.id == doc_id)
                    result = await db.execute(stmt)
                    doc = result.scalar_one_or_none()
                    
                    if doc:
                        doc.indexed = IndexingStatus.INDEXED
                        doc.content = text[:1000]  # Store first 1000 chars
                        await db.commit()
                
                # Queue document for auto-categorization
                from app.services.queue_service import queue_service
                await queue_service.enqueue_document_categorization(
                    document_id=doc_id,
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                    priority="default"
                )
                logger.info(f"Document {doc_id} queued for categorization")
            
        except Exception as e:
            logger.error(f"Error processing document {doc_id}: {e}")
            # Update error status
            async with AsyncSessionLocal() as db:
                stmt = select(Document).filter(Document.id == doc_id)
                result = await db.execute(stmt)
                doc = result.scalar_one_or_none()
                
                if doc:
                    doc.indexed = IndexingStatus.FAILED
                    doc.indexing_error = str(e)
                    await db.commit()
    
    async def _extract_text_async(self, contents: bytes, file_ext: str) -> Optional[str]:
        """Extract text from document asynchronously"""
        # This is a simplified version - in production you'd want proper async extraction
        return await asyncio.to_thread(self._extract_text_sync, contents, file_ext)
    
    def _extract_text_sync(self, contents: bytes, file_ext: str) -> Optional[str]:
        """Synchronous text extraction"""
        try:
            if file_ext == "pdf":
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(contents))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
            
            elif file_ext == "txt":
                encoding = chardet.detect(contents)['encoding'] or 'utf-8'
                return contents.decode(encoding)
            
            elif file_ext == "docx":
                doc = DocxDocument(io.BytesIO(contents))
                return "\n".join([paragraph.text for paragraph in doc.paragraphs])
            
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            return None
    
    async def get_document(self, db: AsyncSession, doc_id: str) -> Document:
        """Get single document by ID"""
        stmt = select(Document).filter(
            Document.id == doc_id,
            Document.tenant_id == self.tenant_id
        ).options(
            selectinload(Document.tags),
            selectinload(Document.creator)
        )
        
        result = await db.execute(stmt)
        doc = result.scalar_one_or_none()
        
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return doc
    
    async def delete_document(self, db: AsyncSession, doc_id: str) -> Dict[str, Any]:
        """Delete a document"""
        doc = await self.get_document(db, doc_id)
        
        # Mark document as deleted by removing it from database
        # Note: Consider implementing soft delete with is_active field if needed
        
        # Delete from vector DB
        try:
            await self.vector_service.delete_document(str(doc.id))
        except Exception as e:
            logger.error(f"Error deleting from vector DB: {e}")
        
        # Delete from storage
        try:
            await self.storage_service.delete_file(doc.file_path)
        except Exception as e:
            logger.error(f"Error deleting from storage: {e}")
        
        # Delete from database
        await db.delete(doc)
        await db.commit()
        
        return {"success": True, "message": "Document deleted successfully"}
    
    async def _auto_categorize_document(self, doc_id: str, text_content: str):
        """Auto-categorize document using the LangChain service"""
        try:
            import httpx
            from app.core.config import settings
            
            async with AsyncSessionLocal() as db:
                # Get document info
                stmt = select(Document).filter(Document.id == doc_id)
                result = await db.execute(stmt)
                doc = result.scalar_one_or_none()
                
                if not doc:
                    return
                
                # First try LangChain service for simple categorization
                try:
                    async with httpx.AsyncClient() as client:
                        # Use LangChain service for document analysis
                        response = await client.post(
                            f"{settings.LANGCHAIN_SERVICE_URL}/api/v1/chat/completions",
                            json={
                                "messages": [{
                                    "role": "system",
                                    "content": """You are a document categorization expert. Analyze the document and categorize it into one of these categories:
                                    - contract: Legal contracts, agreements, terms
                                    - invoice: Invoices, bills, receipts
                                    - report: Reports, analysis, research documents
                                    - legal: Legal documents, policies, regulations
                                    - financial: Financial statements, budgets, accounting
                                    - technical: Technical documentation, manuals, specifications
                                    - correspondence: Letters, emails, memos
                                    - presentation: Slides, presentations
                                    - general: Other documents
                                    
                                    Respond with ONLY the category name, nothing else."""
                                }, {
                                    "role": "user", 
                                    "content": f"Document name: {doc.filename}\nContent preview: {text_content[:1000]}"
                                }],
                                "model": settings.OLLAMA_MODEL,
                                "max_tokens": 50,
                                "temperature": 0.1
                            },
                            headers={
                                "X-API-Key": settings.MICROSERVICES_API_KEY,
                                "Content-Type": "application/json"
                            },
                            timeout=30.0
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            category = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip().lower()
                            
                            # Validate category
                            valid_categories = ["contract", "invoice", "report", "legal", "financial", 
                                              "technical", "correspondence", "presentation", "general"]
                            if category not in valid_categories:
                                category = "general"
                            
                            # Update document category
                            doc.category = category
                            doc.document_metadata = doc.document_metadata or {}
                            doc.document_metadata["auto_categorization"] = {
                                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                "method": "langchain",
                                "model": settings.OLLAMA_MODEL
                            }
                            await db.commit()
                            
                            logger.info(f"Document {doc_id} auto-categorized as '{category}'")
                        else:
                            logger.warning(f"Failed to auto-categorize document {doc_id}: HTTP {response.status_code}")
                            
                except Exception as e:
                    logger.warning(f"LangChain categorization failed for {doc_id}: {e}")
                    # Fallback to simple rule-based categorization
                    category = self._simple_categorize(doc.filename, text_content)
                    doc.category = category
                    doc.document_metadata = doc.document_metadata or {}
                    doc.document_metadata["auto_categorization"] = {
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "method": "rule_based"
                    }
                    await db.commit()
                    logger.info(f"Document {doc_id} categorized as '{category}' using rules")
                        
        except Exception as e:
            logger.error(f"Error auto-categorizing document {doc_id}: {e}")
            # Don't fail the whole process if categorization fails
    
    def _simple_categorize(self, filename: str, content: str) -> str:
        """Simple rule-based categorization as fallback"""
        filename_lower = filename.lower()
        content_lower = content.lower()[:1000]  # Check first 1000 chars
        
        # Check filename and content for patterns
        if any(word in filename_lower for word in ["contract", "agreement", "terms"]):
            return "contract"
        elif any(word in filename_lower for word in ["invoice", "bill", "receipt"]):
            return "invoice"
        elif any(word in filename_lower for word in ["report", "analysis"]):
            return "report"
        elif any(word in content_lower for word in ["whereas", "agreement", "party", "shall"]):
            return "contract"
        elif any(word in content_lower for word in ["invoice", "total", "payment due", "bill to"]):
            return "invoice"
        elif any(word in content_lower for word in ["executive summary", "findings", "conclusion"]):
            return "report"
        elif filename_lower.endswith((".pptx", ".ppt")):
            return "presentation"
        else:
            return "general"
    
    def _get_indexed_status_string(self, indexed_value: int) -> str:
        """Convert indexed integer value to string representation"""
        if indexed_value == IndexingStatus.INDEXED:
            return "INDEXED"
        elif indexed_value == IndexingStatus.PROCESSING:
            return "PROCESSING"
        elif indexed_value == IndexingStatus.INDEXING_ERROR:
            return "INDEXING_ERROR"
        else:  # NOT_INDEXED or unknown
            return "NOT_INDEXED"
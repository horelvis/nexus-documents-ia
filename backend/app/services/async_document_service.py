"""
Async version of DocumentService for use with AsyncSession
"""
import logging
import os
import uuid
import datetime
import io
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload, joinedload

from app.core.config import settings
from app.db.models import Document, Tag, Tenant, DocumentView, FolderMarker
from app.db.async_database import AsyncSessionLocal
from app.schemas.enums import IndexingStatus
from app.services.async_storage_factory import AsyncStorageServiceFactory
from app.services.weaviate_client import weaviate_client
from app.services.elasticsearch_client import elasticsearch_client
from app.services.queue_service import queue_service
from app.services.text_extraction_client import TextExtractionClient
from app.services.langextract_client import langextract_client
from app.services.folder_classification_service import classify_document as classify_document_folder
from .document_classifier import classify_document_type

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
        self.collection_name = None  # Weaviate collection name
        self.elasticsearch_service = None  # NEW: Elasticsearch for hybrid search
        self._initialized = False

    async def _call_cag_query(
        self,
        query: str,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: float = 45.0
    ) -> Optional[str]:
        """
        Helper to call the CAG microservice and return the LLM answer.
        Falls back quietly if the service is unavailable.
        """
        import httpx

        tenant = tenant_id or self.tenant_id or settings.DEFAULT_TENANT
        user = user_id or self.user_id or "system"
        payload = {
            "query": query,
            "tenant_id": str(tenant),
            "user_id": str(user),
            "context": context or {}
        }
        headers = {
            "X-API-Key": settings.MICROSERVICES_API_KEY,
            "X-Tenant-ID": str(tenant)
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{settings.CAG_SERVICE_URL.rstrip('/')}/api/v1/cag/query",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
                answer = data.get("answer")
                if answer:
                    return answer.strip()
        except Exception as exc:
            logger.warning(
                "CAG query failed | tenant=%s user=%s error=%s",
                tenant,
                user,
                exc
            )
        return None

    @staticmethod
    def _normalize_category(answer: str) -> str:
        """Extract a valid category label from a free-form LLM answer."""
        valid_categories = [
            "contract", "invoice", "report", "legal", "financial",
            "technical", "correspondence", "presentation", "general"
        ]
        if not answer:
            return "general"

        clean = answer.strip().lower()
        for category in valid_categories:
            if category in clean:
                return category

        first_word = clean.split()[0]
        return first_word if first_word in valid_categories else "general"

    @staticmethod
    def _build_categorization_preview(
        doc: Document,
        text_content: Optional[str] = None
    ) -> Optional[str]:
        """Build the snippet used for LLM categorization."""
        candidates: List[Optional[str]] = [text_content]
        metadata = doc.document_metadata or {}
        candidates.extend([
            metadata.get("text_preview"),
            metadata.get("summary"),
            doc.description,
            doc.title,
            doc.filename,
        ])
        for candidate in candidates:
            if not candidate:
                continue
            text = str(candidate).strip()
            if text:
                return text[:1200]
        return None
    
    @classmethod
    async def create(cls, tenant_id: str = None, user_id: str = None, db: AsyncSession = None):
        """
        Factory method to create and initialize AsyncDocumentService
        """
        service = cls(tenant_id, user_id)
        await service._initialize(db)
        return service
    
    async def _initialize(self, db: AsyncSession = None):
        """Initialize the service with async operations"""
        # If tenant_id is None or "default", get the real UUID
        if not self.tenant_id or self.tenant_id == settings.DEFAULT_TENANT:
            if db:
                # Use provided session
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
                # Create new session only if not provided
                async with AsyncSessionLocal() as new_db:
                    stmt = select(Tenant).filter(Tenant.name == settings.DEFAULT_TENANT)
                    result = await new_db.execute(stmt)
                    default_tenant = result.scalar_one_or_none()
                    
                    if default_tenant:
                        self.tenant_id = str(default_tenant.id)
                    else:
                        raise ValueError(f"Default tenant '{settings.DEFAULT_TENANT}' not found in database")
                    
                    # Create storage service using async factory
                    self.storage_service = await AsyncStorageServiceFactory.create_storage_service(
                        self.tenant_id, self.user_id, new_db
                    )
        else:
            if db:
                self.storage_service = await AsyncStorageServiceFactory.create_storage_service(
                    self.tenant_id, self.user_id, db
                )
            else:
                async with AsyncSessionLocal() as new_db:
                    self.storage_service = await AsyncStorageServiceFactory.create_storage_service(
                        self.tenant_id, self.user_id, new_db
                    )
        
        self.collection_name = f"Nexus_{self.tenant_id.replace('-', '_')}_documents"
        # Elasticsearch service is now a microservice - no local initialization needed
        logger.info(f"✅ Elasticsearch microservice ready for tenant {self.tenant_id}")
        self.text_extraction_client = TextExtractionClient(self.tenant_id, self.user_id)
        
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
        category: Optional[str] = None,
        document_ids: Optional[List] = None,  # ACL: Filter by accessible document IDs
        folder: Optional[str] = None,  # Filter by folder path (Google Drive style)
    ) -> Dict[str, Any]:
        """Get paginated list of documents with filters using hybrid search when applicable.

        Google Drive style: Returns folders + documents in a single list.
        Folders are returned as items with type="folder" at the beginning.

        Args:
            document_ids: If provided, only return documents in this list (used for ACL filtering).
                         If None, returns all documents in tenant (legacy behavior for admins).
            folder: If provided, filter by folder_path. Returns immediate subfolders as items.
        """
        try:
            # ACL: If document_ids is provided and empty, return no results
            if document_ids is not None and len(document_ids) == 0:
                return {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": 0,
                    "search_engine": "acl_filtered"
                }

            # If we have a search term, REQUIRE Elasticsearch to work
            if search and search.strip():
                if not self.elasticsearch_service:
                    raise HTTPException(
                        status_code=503,
                        detail="Search functionality unavailable: Elasticsearch service not initialized"
                    )

                logger.info(f"🔍 Using Elasticsearch hybrid search for query: '{search}' (NO FALLBACK)")

                # Prepare filters for Elasticsearch
                es_filters = {}
                if category:
                    es_filters["category"] = category
                if tags:
                    es_filters["tags"] = tags
                if date_from:
                    es_filters["date_from"] = date_from
                if date_to:
                    es_filters["date_to"] = date_to
                # ACL: Add document_ids filter for Elasticsearch
                if document_ids is not None:
                    es_filters["document_ids"] = [str(doc_id) for doc_id in document_ids]

                # Build user context for ACL filtering
                from app.services.elasticsearch_client import SearchUserContext
                user_context = None
                if self.user_id:
                    # Get user roles from database if needed
                    user_role_ids = []
                    try:
                        from app.db.models import User
                        user_result = await db.execute(
                            select(User).options(selectinload(User.roles)).filter(User.id == uuid.UUID(self.user_id))
                        )
                        user = user_result.scalars().first()
                        if user:
                            user_role_ids = [str(role.id) for role in user.roles] if user.roles else []
                            user_context = SearchUserContext(
                                user_id=self.user_id,
                                role_ids=user_role_ids,
                                is_admin=user.is_admin
                            )
                    except Exception as ctx_exc:
                        logger.warning(f"Could not build user context for ACL filtering: {ctx_exc}")

                # Perform hybrid search via microservice with ACL filtering
                es_results = await elasticsearch_client.hybrid_search(
                    tenant_id=self.tenant_id,
                    query=search,
                    limit=per_page * 2,  # Get more results to account for filtering
                    filters=es_filters,
                    user_context=user_context
                )
                
                logger.info(f"✅ Elasticsearch returned {len(es_results)} results")
                
                # Extract document IDs from ES results
                doc_ids = [result["document"]["id"] for result in es_results]
                
                # Get full document objects from database in the same order
                if doc_ids:
                    # Create case statement to preserve ES ranking order
                    when_clauses = []
                    for i, doc_id in enumerate(doc_ids):
                        when_clauses.append((Document.id == doc_id, i))
                    
                    order_case = func.case(
                        *when_clauses,
                        else_=len(doc_ids)
                    )
                    
                    # Apply pagination to the ordered ES results
                    offset = (page - 1) * per_page
                    paginated_doc_ids = doc_ids[offset:offset + per_page]
                    
                    if paginated_doc_ids:
                        query = select(Document).filter(
                            Document.id.in_(paginated_doc_ids),
                            Document.tenant_id == self.tenant_id
                        ).options(
                            selectinload(Document.tags),
                            selectinload(Document.creator)
                        ).order_by(order_case)
                        
                        result = await db.execute(query)
                        documents = result.scalars().all()
                        
                        # Build response with ES scores
                        items = []
                        es_scores = {res["document"]["id"]: res["score"] for res in es_results}
                        
                        for doc in documents:
                            doc_dict = self._document_to_dict(doc)
                            doc_dict["search_score"] = es_scores.get(str(doc.id), 0.0)
                            doc_dict["search_matches"] = [
                                match for res in es_results 
                                if res["document"]["id"] == str(doc.id)
                                for match in res.get("matches", [])
                            ]
                            items.append(doc_dict)
                        
                        return {
                            "items": items,
                            "total": len(doc_ids),
                            "page": page,
                            "per_page": per_page,
                            "total_pages": (len(doc_ids) + per_page - 1) // per_page,
                            "search_engine": "elasticsearch_hybrid"
                        }
                    else:
                        # No results for this page
                        return {
                            "items": [],
                            "total": len(doc_ids),
                            "page": page,
                            "per_page": per_page,
                            "total_pages": (len(doc_ids) + per_page - 1) // per_page,
                            "search_engine": "elasticsearch_hybrid"
                        }
                else:
                    # No documents found - this is a valid result, not an error
                    return {
                        "items": [],
                        "total": 0,
                        "page": page,
                        "per_page": per_page,
                        "total_pages": 0,
                        "search_engine": "elasticsearch_hybrid"
                    }
            
            # Fallback to SQL search or when no search term provided
            logger.info("Using SQL-based document search")

            # Base query with ACL filter
            base_filters = [Document.tenant_id == self.tenant_id]

            # ACL: Filter by accessible document IDs
            if document_ids is not None:
                base_filters.append(Document.id.in_(document_ids))

            # Folder filtering (Google Drive style)
            folder_items = []  # Subfolders to include at the beginning
            if folder is not None:
                # Normalize folder path
                current_folder = folder.strip() if folder else ""
                if current_folder and not current_folder.startswith("/"):
                    current_folder = "/" + current_folder

                if current_folder:
                    # Filter documents in this specific folder only (not subfolders)
                    base_filters.append(Document.folder_path == current_folder)
                else:
                    # Root folder: show documents with no folder or empty folder_path
                    base_filters.append(
                        or_(
                            Document.folder_path.is_(None),
                            Document.folder_path == "",
                            Document.folder_path == "/"
                        )
                    )

                # Get immediate subfolders as items (Google Drive style)
                # Query to find distinct folder_path values that are direct children
                from sqlalchemy import distinct, case, literal

                if current_folder:
                    # Find folders that start with current_folder/ but are only one level deeper
                    subfolder_query = (
                        select(
                            Document.folder_path,
                            func.count(Document.id).label("document_count")
                        )
                        .where(Document.tenant_id == self.tenant_id)
                        .where(Document.folder_path.isnot(None))
                        .where(Document.folder_path.startswith(current_folder + "/"))
                        .group_by(Document.folder_path)
                    )
                else:
                    # Root: find all top-level folders
                    subfolder_query = (
                        select(
                            Document.folder_path,
                            func.count(Document.id).label("document_count")
                        )
                        .where(Document.tenant_id == self.tenant_id)
                        .where(Document.folder_path.isnot(None))
                        .where(Document.folder_path != "")
                        .where(Document.folder_path != "/")
                        .group_by(Document.folder_path)
                    )

                # ACL: Filter subfolders by accessible document IDs
                if document_ids is not None:
                    subfolder_query = subfolder_query.where(Document.id.in_(document_ids))

                subfolder_result = await db.execute(subfolder_query)
                all_subpaths = subfolder_result.all()

                # Extract immediate children only
                seen_folders = set()
                prefix_len = len(current_folder) + 1 if current_folder else 1

                for full_path, count in all_subpaths:
                    if not full_path:
                        continue
                    # Get the immediate child folder name
                    remaining = full_path[prefix_len:] if prefix_len <= len(full_path) else full_path
                    if "/" in remaining:
                        # This is a nested folder, get only the first level
                        immediate_child = remaining.split("/")[0]
                    else:
                        immediate_child = remaining

                    if immediate_child and immediate_child not in seen_folders:
                        seen_folders.add(immediate_child)
                        child_path = f"{current_folder}/{immediate_child}" if current_folder else f"/{immediate_child}"

                        # Count documents in this subfolder (recursively)
                        subfolder_count_query = (
                            select(func.count(Document.id))
                            .where(Document.tenant_id == self.tenant_id)
                            .where(Document.folder_path.startswith(child_path))
                        )
                        if document_ids is not None:
                            subfolder_count_query = subfolder_count_query.where(Document.id.in_(document_ids))

                        count_result = await db.execute(subfolder_count_query)
                        subfolder_doc_count = count_result.scalar() or 0

                        folder_items.append({
                            "id": f"folder:{child_path}",
                            "type": "folder",
                            "title": immediate_child,
                            "filename": immediate_child,
                            "folder_path": child_path,
                            "document_count": subfolder_doc_count,
                            "file_type": "folder",
                            "file_size": 0,
                            "mime_type": "inode/directory",
                            "indexed": "N/A",
                            "category": None,
                            "created_at": None,
                            "updated_at": None,
                            "tags": [],
                            "created_by": None
                        })

                # Also include empty folders (FolderMarkers) at this level
                if current_folder:
                    # Find markers that start with current_folder/ but are one level deeper
                    marker_query = (
                        select(FolderMarker.folder_path, FolderMarker.created_at)
                        .where(FolderMarker.tenant_id == self.tenant_id)
                        .where(FolderMarker.folder_path.startswith(current_folder + "/"))
                    )
                else:
                    # Root: find all top-level folder markers
                    marker_query = (
                        select(FolderMarker.folder_path, FolderMarker.created_at)
                        .where(FolderMarker.tenant_id == self.tenant_id)
                        .where(FolderMarker.folder_path != "")
                        .where(FolderMarker.folder_path != "/")
                    )

                marker_result = await db.execute(marker_query)
                all_markers = marker_result.all()

                # Add immediate children from markers that aren't already in seen_folders
                for marker_path, marker_created_at in all_markers:
                    if not marker_path:
                        continue
                    remaining = marker_path[prefix_len:] if prefix_len <= len(marker_path) else marker_path
                    if "/" in remaining:
                        immediate_child = remaining.split("/")[0]
                    else:
                        immediate_child = remaining

                    if immediate_child and immediate_child not in seen_folders:
                        seen_folders.add(immediate_child)
                        child_path = f"{current_folder}/{immediate_child}" if current_folder else f"/{immediate_child}"

                        folder_items.append({
                            "id": f"folder:{child_path}",
                            "type": "folder",
                            "title": immediate_child,
                            "filename": immediate_child,
                            "folder_path": child_path,
                            "document_count": 0,  # Empty folder
                            "file_type": "folder",
                            "file_size": 0,
                            "mime_type": "inode/directory",
                            "indexed": "N/A",
                            "category": None,
                            "created_at": marker_created_at.isoformat() if marker_created_at else None,
                            "updated_at": None,
                            "tags": [],
                            "created_by": None
                        })

                # Sort folders alphabetically
                folder_items.sort(key=lambda x: x["title"].lower())

            query = select(Document).filter(
                *base_filters
            ).options(
                selectinload(Document.tags),
                selectinload(Document.creator)
            )

            # Apply filters
            if search:
                query = query.filter(
                    or_(
                        Document.title.ilike(f"%{search}%"),
                        Document.description.ilike(f"%{search}%"),
                        Document.filename.ilike(f"%{search}%")
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

            # Count total documents (not including folders)
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await db.execute(count_query)
            total_docs = total_result.scalar()

            # Total items = folders + documents
            total = len(folder_items) + total_docs

            # Pagination logic accounting for folders
            # Folders are always shown first on page 1
            offset = (page - 1) * per_page

            if page == 1:
                # First page: show folders first, then documents
                docs_to_fetch = per_page - len(folder_items)
                query = query.offset(0).limit(max(0, docs_to_fetch)).order_by(Document.created_at.desc())
            else:
                # Other pages: adjust offset for folders shown on page 1
                adjusted_offset = offset - len(folder_items)
                query = query.offset(max(0, adjusted_offset)).limit(per_page).order_by(Document.created_at.desc())

            # Execute query
            result = await db.execute(query)
            documents = result.scalars().all()

            # Convert documents to dict with type="document"
            doc_items = []
            for doc in documents:
                doc_dict = {
                    "id": str(doc.id),
                    "type": "document",
                    "title": doc.title,
                    "description": doc.description,
                    "filename": doc.filename,
                    "folder_path": doc.folder_path,
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
                doc_items.append(doc_dict)

            # Combine: folders first (only on page 1), then documents
            if page == 1:
                items = folder_items + doc_items
            else:
                items = doc_items

            return {
                "items": items,
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page,
                "search_engine": "sql",
                "current_folder": folder if folder is not None else None,
                "folder_count": len(folder_items) if page == 1 else 0,
                "document_count": total_docs
            }
            
        except Exception as e:
            logger.error(f"Error getting documents: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def _document_to_dict(self, doc: Document) -> Dict[str, Any]:
        """Convert Document model to dictionary"""
        return {
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
    
    async def upload_document(
        self,
        db: AsyncSession,
        file: UploadFile,
        title: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
        cliente: Optional[str] = None,
        periodo: Optional[str] = None,
        tipo_documento: Optional[str] = None,
        folder_path: Optional[str] = None
    ) -> Document:
        """
        Upload a new document.

        If folder_path is provided, the document is placed in that folder
        and marked as manually classified (auto_classified=False).
        This supports Google Drive style navigation where uploading
        while inside a folder places the document there.
        """
        try:
            # Ensure service is initialized
            if not self._initialized:
                await self._initialize(db)
            # Validate file
            file_ext, contents, file_size = await self._validate_file(file, file.filename)
            
            # Generate unique filename
            file_id = str(uuid.uuid4())
            stored_filename = f"{file_id}.{file_ext}"

            # Build document metadata
            document_metadata = {}
            if cliente:
                document_metadata['cliente'] = cliente
            if periodo:
                document_metadata['periodo'] = periodo
            if tipo_documento:
                document_metadata['tipo_documento'] = tipo_documento

            # Determine folder path and classification status
            # If folder_path is provided, it's a manual classification (user uploaded to specific folder)
            # If not provided, default to /Sin Clasificar for future auto-classification
            effective_folder_path = folder_path if folder_path else "/Sin Clasificar"
            is_manually_classified = folder_path is not None and folder_path != "/Sin Clasificar"

            # Normalize folder path
            if not effective_folder_path.startswith("/"):
                effective_folder_path = "/" + effective_folder_path

            # Build file path including folder structure
            file_path_with_folder = f"{effective_folder_path.lstrip('/')}/{stored_filename}"

            # Create document record
            doc = Document(
                id=uuid.uuid4(),
                title=title,
                description=description,
                filename=file.filename,
                file_path=file_path_with_folder,
                folder_path=effective_folder_path,
                file_type=file_ext,
                file_size=file_size,
                mime_type=file.content_type,
                category=category,
                document_metadata=document_metadata if document_metadata else None,
                tenant_id=self.tenant_id,
                created_by=self.user_id,
                indexed=IndexingStatus.PROCESSING,  # Set initial status
                auto_classified=False,  # Manual upload is never auto-classified
                classification_reasoning=f"Subido manualmente a {effective_folder_path}" if is_manually_classified else None
            )
            
            # Upload to storage (using full path with folder structure)
            upload_success = await self.storage_service.upload_file(
                file=io.BytesIO(contents),
                object_name=file_path_with_folder,
                metadata={"content_type": file.content_type}
            )
            
            if not upload_success:
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
            
            # Reload the document with proper eager loading for tags
            stmt = select(Document).filter(
                Document.id == doc.id
            ).options(
                selectinload(Document.tags),
                selectinload(Document.creator)
            )
            result = await db.execute(stmt)
            doc = result.scalar_one()
            
            # Extract text and index asynchronously
            # Pass document info to avoid needing new DB session
            doc_info = {
                "id": str(doc.id),
                "filename": doc.filename,
                "tenant_id": self.tenant_id,
                "user_id": self.user_id
            }
            task = asyncio.create_task(self._process_document_async(doc_info, contents, file_ext))
            # Add error handler for the background task
            task.add_done_callback(lambda t: logger.error(f"Background processing failed: {t.exception()}") if t.exception() else None)
            
            return doc
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error uploading document: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def _process_document_async(self, doc_info: dict, contents: bytes, file_ext: str):
        """Process document in background"""
        doc_id = doc_info["id"]
        try:
            logger.info(f"Starting async processing for document {doc_id}, file type: {file_ext}")
            
            # Extract text via microservice
            extraction = await self.text_extraction_client.extract_text(
                file_bytes=contents,
                filename=doc_info.get("filename"),
                file_extension=file_ext,
            )
            text = extraction.text
            logger.info(
                "Text extraction completed for %s, length=%s, language=%s",
                doc_id,
                len(text) if text else 0,
                extraction.language,
            )
            
            # Auto-classify document type
            if text:
                from app.services.document_classifier import classify_document_type
                tipo_documento = classify_document_type(text[:4000])  # Simple keyword classifier
                logger.info(f"Auto-classified document {doc_id} as: {tipo_documento}")
            
            if text:
                try:
                    # Limit text length for embedding generation to avoid timeouts
                    # With all-minilm, we can process text faster but let's be conservative
                    max_text_length = 30000  # Limit to ~30k characters for faster processing
                    if len(text) > max_text_length:
                        logger.warning(f"Text too long ({len(text)} chars), truncating to {max_text_length} for embeddings")
                        text_for_embedding = text[:max_text_length]
                    else:
                        text_for_embedding = text
                    
                    # Note: Embeddings are generated by weaviate-service when storing the document
                    logger.info(f"Document {doc_id} prepared for Weaviate (text length: {len(text_for_embedding)})")
                except Exception as e:
                    logger.error(f"Failed to prepare document {doc_id}: {e}")
                    raise Exception(f"Document preparation failed: {str(e)}")
                
                try:
                    # Get full document info for metadata before storing in vector DB
                    async with AsyncSessionLocal() as db:
                        stmt = (
                            select(Document)
                            .options(selectinload(Document.tags))
                            .filter(Document.id == doc_id)
                        )
                        result = await db.execute(stmt)
                        doc = result.scalar_one_or_none()
                        
                        if not doc:
                            raise Exception("Document not found in database")

                        tags_list = [tag.name for tag in doc.tags] if doc.tags else []
                        metadata = {
                            "file_type": file_ext,
                            "tenant_id": self.tenant_id,
                            "filename": doc.filename,
                            "title": doc.title or doc.filename,
                            "description": doc.description,
                            "created_at": doc.created_at.isoformat() if doc.created_at else None,
                            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                            "file_size": doc.file_size,
                            "mime_type": doc.mime_type,
                            "category": doc.category,
                            "tags": tags_list,
                        }
                    
                    # Store in Weaviate via microservice (it generates embeddings internally)
                    logger.info(f"Storing document {doc_id} in Weaviate collection {self.collection_name}")
                    weaviate_document = {
                        "id": doc_id,
                        "title": doc.title or doc.filename,
                        "content": text_for_embedding,
                        "metadata": metadata,
                        "tenant_id": self.tenant_id,
                        "document_type": doc.category or "general",
                        "tags": tags_list,
                    }
                    await weaviate_client.add_document(self.collection_name, weaviate_document)
                    logger.info(f"✅ Document {doc_id} stored in Weaviate")
                    
                    # Prepare tag information for downstream services
                    tags_list = metadata.get("tags") or []
                    metadata["tags"] = tags_list
                    metadata["language"] = extraction.language
                    metadata["text_extraction"] = {
                        "language": extraction.language,
                        "characters": extraction.characters,
                        **(extraction.metadata or {}),
                    }
                except Exception as e:
                    logger.error(f"Failed to store in vector DB for {doc_id}: {e}")
                    raise Exception(f"Vector storage failed: {str(e)}")
                
                # Update document status and perform routing in single session
                async with AsyncSessionLocal() as db:
                    stmt = select(Document).options(selectinload(Document.tags)).filter(Document.id == doc_id)
                    result = await db.execute(stmt)
                    doc = result.scalar_one_or_none()
                    
                    if doc:
                        doc.indexed = IndexingStatus.PROCESSING
                        # Auto-classify document type
                        # Use langextract for labor classification
                        try:
                            labor_classif = await self.langextract_client.classify_labor_document(text[:4000])
                            tipo_documento = labor_classif.get('tipo_documento', 'otro')
                            logger.info(f"LangExtract classified {doc_id} as: {tipo_documento}")
                        except Exception as e:
                            logger.warning(f"LangExtract classification failed for {doc_id}: {e}, fallback 'otro'")
                            tipo_documento = 'otro'
                        
                        # Generate summary instead of storing first 1000 chars
                        summary = await self._generate_document_summary(text, doc_info["filename"])
                        current_metadata = dict(doc.document_metadata or {})
                        current_metadata["tipo_documento"] = tipo_documento
                        current_metadata["text_extraction"] = metadata.get("text_extraction", {})
                        if summary:
                            current_metadata["summary"] = summary
                            current_metadata.setdefault("text_preview", summary[:500])
                        doc.document_metadata = current_metadata

                        # Cache frequently accessed scalar fields to avoid lazy loads after commit
                        cached_doc = {
                            "title": doc.title,
                            "filename": doc.filename,
                            "description": doc.description,
                            "file_type": doc.file_type,
                            "category": doc.category,
                            "tags": [tag.name for tag in doc.tags] if doc.tags else [],
                            "created_at": doc.created_at.isoformat() if doc.created_at else None,
                            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                            "file_size": doc.file_size,
                            "mime_type": doc.mime_type,
                            "tenant_id": str(doc.tenant_id),
                            "created_by": str(doc.created_by) if doc.created_by else None,
                        }

                        await db.commit()
                        logger.info(f"Document {doc_id} summary generated; starting search indexing pipeline")
                        
                        es_success = False
                        es_error: Optional[str] = None

                        logger.info(
                            f"🔍 MANDATORY Elasticsearch indexing for document {doc_id} "
                            f"(title: {cached_doc['title']})"
                        )
                        
                        # Prepare metadata for Elasticsearch
                        es_metadata = {
                            "file_type": cached_doc["file_type"],
                            "category": cached_doc["category"],
                            "tags": cached_doc["tags"],
                            "created_at": cached_doc["created_at"],
                            "updated_at": cached_doc["updated_at"],
                            "file_size": cached_doc["file_size"],
                            "tenant_id": cached_doc["tenant_id"]
                        }
                        
                        logger.debug(f"ES metadata for {doc_id}: {es_metadata}")

                        # Get ACL data for the document
                        from app.db.models import DocumentACL
                        from datetime import datetime, timezone

                        acl_user_ids = []
                        acl_role_ids = []
                        acl_everyone = False

                        try:
                            now = datetime.now(timezone.utc)
                            acl_result = await db.execute(
                                select(DocumentACL).filter(
                                    and_(
                                        DocumentACL.document_id == doc_id,
                                        DocumentACL.tenant_id == uuid.UUID(self.tenant_id),
                                        DocumentACL.can_view == True,
                                        or_(
                                            DocumentACL.expires_at.is_(None),
                                            DocumentACL.expires_at > now
                                        )
                                    )
                                )
                            )
                            acls = acl_result.scalars().all()

                            for acl in acls:
                                if acl.grantee_type == 'user' and acl.grantee_id:
                                    acl_user_ids.append(str(acl.grantee_id))
                                elif acl.grantee_type == 'role' and acl.grantee_id:
                                    acl_role_ids.append(str(acl.grantee_id))
                                elif acl.grantee_type == 'everyone':
                                    acl_everyone = True
                        except Exception as acl_exc:
                            logger.warning(f"Could not fetch ACLs for document {doc_id}: {acl_exc}")
                            # Default to everyone=True for backward compatibility with legacy documents
                            acl_everyone = True

                        try:
                            es_success = await elasticsearch_client.index_document(
                                tenant_id=self.tenant_id,
                                doc_id=str(doc_id),
                                title=cached_doc["title"],
                                content=text[:5000],  # Index more content for better search
                                description=cached_doc["description"],
                                metadata=es_metadata,
                                # ACL fields
                                created_by=cached_doc["created_by"],
                                acl_user_ids=acl_user_ids,
                                acl_role_ids=acl_role_ids,
                                acl_everyone=acl_everyone
                            )
                        except Exception as es_exc:
                            es_error = str(es_exc)
                            es_success = False
                            logger.error(f"❌ Elasticsearch indexing exception for document {doc_id}: {es_error}")
                        
                        if es_success:
                            logger.info(f"✅ Document {doc_id} successfully indexed in Elasticsearch")

                            # Perform routing analysis in the same session
                            await self._perform_routing_analysis(db, doc_info, text, file_ext)

                            # Entity extraction moved to after auto-categorization (line ~877)
                            # to avoid duplicate LangExtract calls
                        else:
                            logger.error(f"❌ Document {doc_id} failed to index in Elasticsearch")
                        
                        # Finalize indexing status based on both backends
                        indexing_errors = []
                        if not weaviate_success:
                            indexing_errors.append(
                                f"Weaviate: {weaviate_error or 'unknown error (see logs)'}"
                            )
                        if not es_success:
                            indexing_errors.append(
                                f"Elasticsearch: {es_error or 'unknown error (see logs)'}"
                            )

                        if indexing_errors:
                            doc.indexed = IndexingStatus.INDEXING_ERROR
                            doc.indexing_error = " | ".join(indexing_errors)
                            await db.commit()
                            logger.warning(
                                f"Document {doc_id} marked as INDEXING_ERROR due to: {doc.indexing_error}"
                            )
                            try:
                                await queue_service.enqueue_index_retry(
                                    document_id=str(doc.id),
                                    tenant_id=self.tenant_id,
                                    user_id=self.user_id or (str(cached_doc["created_by"]) if cached_doc["created_by"] else None),
                                    priority="high" if not es_success else "default"
                                )
                            except Exception as enqueue_error:
                                logger.error(
                                    f"Failed to enqueue indexing retry for {doc_id}: {enqueue_error}"
                                )
                        else:
                            doc.indexed = IndexingStatus.INDEXED
                            doc.indexing_error = None
                            await db.commit()
                            logger.info(
                                f"Document {doc_id} fully indexed across Elasticsearch and Weaviate"
                            )
                
                # Auto-categorize immediately via CAG/Elysia
                try:
                    category = await self._auto_categorize_document(
                        doc_id,
                        text_content=text_for_embedding,
                        tenant_id=self.tenant_id,
                        user_id=self.user_id,
                        source="auto_ingest",
                    )
                    if category:
                        logger.info(
                            f"Document {doc_id} categorized automatically as '{category}'"
                        )
                except Exception as e:
                    logger.warning(f"Auto-categorization failed for {doc_id}: {e}")

                # Extract entities via LangExtract (generates visualization_html)
                try:
                    # Use CAG category or default to 'general'
                    doc_type = category if category else "general"
                    entity_result = await langextract_client.extract_entities(
                        text=text_for_embedding[:50000],
                        document_type=doc_type,
                        filename=doc_info.get("filename"),
                    )

                    if entity_result.get("success"):
                        async with AsyncSessionLocal() as db:
                            stmt = select(Document).filter(Document.id == doc_id)
                            result = await db.execute(stmt)
                            doc = result.scalar_one_or_none()

                            if doc:
                                # Save extracted entities
                                doc.extracted_entities = entity_result.get("extractions", [])

                                # Save visualization_html and summary in document_metadata
                                # IMPORTANT: Copy dict to trigger SQLAlchemy change detection for JSONB
                                updated_metadata = dict(doc.document_metadata or {})
                                updated_metadata["categorization"] = updated_metadata.get("categorization", {})
                                updated_metadata["categorization"]["visualization_html"] = entity_result.get("visualization_html")
                                updated_metadata["extraction_summary"] = entity_result.get("summary", {})
                                doc.document_metadata = updated_metadata  # Reassign to trigger change

                                await db.commit()
                                logger.info(
                                    f"Document {doc_id}: extracted {len(doc.extracted_entities)} entities with visualization"
                                )
                except Exception as e:
                    logger.warning(f"Entity extraction failed for {doc_id}: {e}")

                # Auto-classify document folder using RAG + LLM (Learn-First approach)
                try:
                    await self._auto_classify_folder(
                        doc_id=doc_id,
                        text_content=text_for_embedding,
                        filename=doc_info.get("filename"),
                        file_type=file_ext,
                    )
                except Exception as e:
                    logger.warning(f"Folder classification failed for {doc_id}: {e}")

                # Routing legacy deshabilitado
            else:
                logger.warning(f"No text extracted from document {doc_id}")
                raise Exception("No text could be extracted from the document")
            
        except Exception as e:
            logger.error(f"Error processing document {doc_id}: {e}", exc_info=True)
            # Update error status
            async with AsyncSessionLocal() as db:
                stmt = select(Document).filter(Document.id == doc_id)
                result = await db.execute(stmt)
                doc = result.scalar_one_or_none()
                
                if doc:
                    doc.indexed = IndexingStatus.INDEXING_ERROR
                    doc.indexing_error = str(e)
                    await db.commit()
                    logger.info(f"Document {doc_id} marked as INDEXING_ERROR: {str(e)}")
    
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
        
        # Delete from Weaviate
        try:
            await weaviate_client.delete_document(self.collection_name, str(doc.id))
        except Exception as e:
            logger.error(f"Error deleting from Weaviate: {e}")
        
        # Delete from storage
        try:
            await self.storage_service.delete_file(doc.file_path)
        except Exception as e:
            logger.error(f"Error deleting from storage: {e}")
        
        # Delete from database
        await db.delete(doc)
        await db.commit()
        
        return {"success": True, "message": "Document deleted successfully"}
    
    async def _auto_categorize_document(
        self,
        doc_id: str,
        text_content: Optional[str] = None,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        source: str = "auto",
        db: Optional[AsyncSession] = None,
    ) -> Optional[str]:
        """Auto-categorize a document using LangExtract (no CAG fallback)."""
        session = db
        owns_session = False
        if session is None:
            session = AsyncSessionLocal()
            owns_session = True
        try:
            stmt = select(Document).filter(Document.id == doc_id)
            result = await session.execute(stmt)
            doc = result.scalar_one_or_none()

            if not doc:
                logger.warning(f"Cannot categorize missing document {doc_id}")
                return None

            snippet = self._build_categorization_preview(doc, text_content)
            if not snippet:
                logger.warning(f"No preview available to categorize document {doc_id}")
                return None

            # Use LangExtract for intelligent categorization
            logger.info(f"📋 Categorizando documento {doc_id} con LangExtract")
            categorization_result = await langextract_client.categorize_document(
                text=snippet,
                filename=doc.filename,
                context=f"Document ID: {doc_id}"
            )

            if categorization_result.get("error"):
                logger.warning(f"LangExtract categorization error: {categorization_result.get('error')}")
                return None

            category = categorization_result.get("detected_type", "general")
            confidence = categorization_result.get("confidence", 0.0)
            reasoning = categorization_result.get("reasoning", "")

            # Update document with categorization
            doc.category = category
            # IMPORTANT: Copy dict to trigger SQLAlchemy change detection for JSONB
            updated_metadata = dict(doc.document_metadata or {})
            updated_metadata["auto_categorization"] = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "method": "langextract",
                "model": "gemini-2.0-flash",
                "source": source,
                "detected_type": category,
                "confidence": confidence,
                "reasoning": reasoning,
            }
            doc.document_metadata = updated_metadata  # Reassign to trigger change
            await session.commit()

            logger.info(f"✅ Document {doc_id} categorized as '{category}' (confidence: {confidence:.2f})")
            return category

        except Exception as e:
            logger.error(f"Error auto-categorizing document {doc_id}: {e}")
            await session.rollback()
            return None
        finally:
            if owns_session:
                await session.close()

    async def _auto_classify_folder(
        self,
        doc_id: str,
        text_content: Optional[str] = None,
        filename: Optional[str] = None,
        file_type: Optional[str] = None,
    ) -> Optional[str]:
        """
        Auto-classify document into folder using RAG + LLM.

        Learn-First approach:
        - If auto_classification_enabled = FALSE → document stays in /Sin Clasificar
        - If enabled → RAG finds similar docs, LLM decides folder
        - If LLM confidence < min_confidence → /Sin Clasificar

        Returns the assigned folder path, or None if classification failed.
        """
        async with AsyncSessionLocal() as session:
            try:
                # Get tenant settings
                stmt = select(Tenant).filter(Tenant.id == self.tenant_id)
                result = await session.execute(stmt)
                tenant = result.scalar_one_or_none()

                if not tenant:
                    logger.warning(f"Tenant {self.tenant_id} not found for folder classification")
                    return None

                # Check if auto-classification is enabled
                if not tenant.auto_classification_enabled:
                    logger.info(
                        f"📁 Folder classification DISABLED for tenant {self.tenant_id}. "
                        f"Document {doc_id} stays in /Sin Clasificar (Learn-First mode)"
                    )
                    return "/Sin Clasificar"

                # Get document
                stmt = select(Document).filter(Document.id == doc_id)
                result = await session.execute(stmt)
                doc = result.scalar_one_or_none()

                if not doc:
                    logger.warning(f"Document {doc_id} not found for folder classification")
                    return None

                # Prepare document dict for classification
                documento = {
                    "doc_id": str(doc_id),
                    "filename": filename or doc.filename,
                    "file_type": file_type or doc.file_type,
                    "content": text_content or "",
                }

                # Run RAG + LLM classification
                logger.info(f"🔍 Running RAG+LLM folder classification for document {doc_id}")
                classification = await classify_document_folder(
                    tenant_id=self.tenant_id,
                    documento=documento,
                    k=tenant.auto_classification_k,
                    min_confidence=tenant.auto_classification_min_confidence,
                )

                # Check confidence threshold
                if classification.confianza < tenant.auto_classification_min_confidence:
                    logger.info(
                        f"📁 Confidence ({classification.confianza:.2f}) below threshold "
                        f"({tenant.auto_classification_min_confidence}). "
                        f"Document {doc_id} goes to /Sin Clasificar"
                    )
                    assigned_folder = "/Sin Clasificar"
                    doc.folder_path = assigned_folder
                    doc.auto_classified = False
                    doc.classification_confidence = classification.confianza
                    doc.classification_reasoning = classification.razonamiento
                else:
                    assigned_folder = classification.carpeta
                    doc.folder_path = assigned_folder
                    doc.auto_classified = True
                    doc.classification_confidence = classification.confianza
                    doc.classification_reasoning = classification.razonamiento
                    logger.info(
                        f"✅ Document {doc_id} auto-classified to '{assigned_folder}' "
                        f"(confidence: {classification.confianza:.2f})"
                    )

                await session.commit()
                return assigned_folder

            except Exception as e:
                logger.error(f"Error in folder classification for document {doc_id}: {e}")
                await session.rollback()
                return None

    async def categorize_document(
        self,
        db: AsyncSession,
        doc_id: str,
        *,
        content_preview: Optional[str],
        tenant_id: str,
        user_id: str,
        source: str = "manual",
    ) -> Dict[str, Any]:
        """Public helper to categorize/re-categorize a document."""
        category = await self._auto_categorize_document(
            doc_id,
            text_content=content_preview,
            tenant_id=tenant_id,
            user_id=user_id,
            source=source,
            db=db,
        )
        if category:
            return {"success": True, "category": category}
        return {"success": False, "error": "Unable to categorize document"}
    
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
    
    async def generate_summary(self, db: AsyncSession, doc_id: str) -> Dict[str, str]:
        """Generate document summary using Elysia and persist it in metadata."""
        try:
            document = await self.get_document(db, doc_id)
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")

            metadata = dict(document.document_metadata or {})
            preview_candidates = [
                metadata.get("text_preview"),
                metadata.get("summary"),
                document.description,
                document.title,
                document.filename,
            ]
            source_text = next((str(value).strip() for value in preview_candidates if value), None)

            if not source_text:
                raise HTTPException(
                    status_code=400,
                    detail="Document has no available preview to summarize"
                )

            summary = await self._call_cag_query(
                query=(
                    "Genera un resumen ejecutivo (máximo 200 palabras) del siguiente contenido.\n"
                    f"Documento: {document.filename}\n\n{source_text}"
                ),
                tenant_id=self.tenant_id,
                user_id=self.user_id or str(document.created_by),
                context={"task": "document_summary", "document_id": str(document.id)},
                timeout=30.0,
            )
            if not summary:
                summary = self._create_simple_summary(source_text, document.filename)

            metadata["summary"] = summary
            metadata.setdefault("text_preview", summary[:500])
            document.document_metadata = metadata
            await db.commit()

            return {
                "summary": summary,
                "status": "generated"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating summary for document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Error generating summary")
    
    async def add_tag(self, db: AsyncSession, doc_id: str, tag_name: str) -> Dict[str, Any]:
        """Add a tag to a document"""
        try:
            # Get document
            stmt = select(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).options(selectinload(Document.tags))
            
            result = await db.execute(stmt)
            document = result.scalar_one_or_none()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Check if tag already exists
            tag_stmt = select(Tag).filter(
                Tag.name == tag_name,
                Tag.tenant_id == self.tenant_id
            )
            tag_result = await db.execute(tag_stmt)
            tag = tag_result.scalar_one_or_none()
            
            if not tag:
                # Create new tag
                tag = Tag(name=tag_name, tenant_id=self.tenant_id)
                db.add(tag)
                await db.flush()
            
            # Add tag to document if not already added
            if tag not in document.tags:
                document.tags.append(tag)
                await db.commit()
            
            return {
                "message": f"Tag '{tag_name}' added successfully",
                "document_id": str(document.id),
                "tags": [t.name for t in document.tags]
            }
            
        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error adding tag to document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Error adding tag")
    
    async def remove_tag(self, db: AsyncSession, doc_id: str, tag_name: str) -> Dict[str, Any]:
        """Remove a tag from a document"""
        try:
            # Get document
            stmt = select(Document).filter(
                Document.id == doc_id,
                Document.tenant_id == self.tenant_id
            ).options(selectinload(Document.tags))
            
            result = await db.execute(stmt)
            document = result.scalar_one_or_none()
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Find and remove the tag
            tag_to_remove = None
            for tag in document.tags:
                if tag.name == tag_name:
                    tag_to_remove = tag
                    break
            
            if tag_to_remove:
                document.tags.remove(tag_to_remove)
                await db.commit()
                
                return {
                    "message": f"Tag '{tag_name}' removed successfully",
                    "document_id": str(document.id),
                    "tags": [t.name for t in document.tags]
                }
            else:
                raise HTTPException(status_code=404, detail=f"Tag '{tag_name}' not found on document")
            
        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error removing tag from document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Error removing tag")
    
    async def mark_document_viewed(
        self, 
        document_id: str, 
        view_duration_seconds: int = None,
        scroll_percentage: float = None
    ) -> str:
        """
        Mark document as viewed by current user
        
        Args:
            document_id: ID of the document being viewed
            view_duration_seconds: Optional duration of view in seconds
            scroll_percentage: Optional percentage of document scrolled
            
        Returns:
            view_id: ID of the created view record
        """
        try:
            async with AsyncSessionLocal() as db:
                # Check if document exists and belongs to tenant
                stmt = select(Document).filter(
                    Document.id == document_id,
                    Document.tenant_id == self.tenant_id
                )
                result = await db.execute(stmt)
                document = result.scalar_one_or_none()
                
                if not document:
                    raise HTTPException(status_code=404, detail="Document not found")
                
                # Create or update document view record
                view_record = DocumentView(
                    user_id=self.user_id,
                    document_id=document_id,
                    tenant_id=self.tenant_id,
                    viewed_at=func.now(),
                    view_duration_seconds=view_duration_seconds,
                    scroll_percentage=scroll_percentage
                )
                
                db.add(view_record)
                await db.commit()
                await db.refresh(view_record)
                
                logger.info(f"Document {document_id} marked as viewed by user {self.user_id}")
                return str(view_record.id)
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error marking document {document_id} as viewed: {str(e)}")
            raise HTTPException(status_code=500, detail="Error marking document as viewed")
    
    async def get_recently_viewed_documents(
        self, 
        limit: int = 10, 
        user_specific: bool = True
    ) -> List[Dict[str, Any]]:
        """Get recently viewed documents for the user or tenant"""
        try:
            async with AsyncSessionLocal() as db:
                # Base query with Document and DocumentView joined
                query = select(
                    Document,
                    func.max(DocumentView.viewed_at).label("last_viewed_at")
                ).join(
                    DocumentView, Document.id == DocumentView.document_id
                ).filter(
                    Document.tenant_id == self.tenant_id
                )
                
                # Filter by user if specified
                if user_specific and self.user_id:
                    query = query.filter(DocumentView.user_id == self.user_id)
                
                # Group by document, order by most recent view, limit results
                query = query.group_by(Document.id).order_by(
                    func.max(DocumentView.viewed_at).desc()
                ).limit(limit)
                
                result = await db.execute(query)
                documents = result.fetchall()
                
                # Format results
                results = []
                for doc, last_viewed_at in documents:
                    results.append({
                        "id": str(doc.id),
                        "filename": doc.filename,
                        "title": doc.title,
                        "description": doc.description,
                        "file_type": doc.file_type,
                        "mime_type": doc.mime_type,
                        "file_size": doc.file_size,
                        "tags": doc.tags or [],
                        "created_at": doc.created_at.isoformat() if doc.created_at else None,
                        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                        "indexed": doc.indexed,
                        "category": doc.category,
                        "tenant_id": str(doc.tenant_id),
                        "created_by": str(doc.created_by)
                    })
                
                logger.info(f"Retrieved {len(results)} recently viewed documents")
                return results
                
        except Exception as e:
            logger.error(f"Error getting recently viewed documents: {str(e)}")
            raise HTTPException(status_code=500, detail="Error retrieving recently viewed documents")
    
    async def _generate_document_summary(self, text: str, filename: str) -> str:
        """Generate a concise summary of the document"""
        try:
            text_for_summary = text[:5000] if len(text) > 5000 else text
            
            cag_answer = await self._call_cag_query(
                query=(
                    "Genera un resumen conciso (2-3 oraciones, máximo 200 palabras) "
                    "del siguiente documento. Incluye el propósito principal y los puntos clave.\n\n"
                    f"Archivo: {filename}\n"
                    f"Contenido:\n{text_for_summary}"
                ),
                tenant_id=self.tenant_id or settings.DEFAULT_TENANT,
                user_id=self.user_id or "system",
                context={
                    "task": "document_summary",
                    "filename": filename
                },
                timeout=30.0
            )
            
            if cag_answer:
                summary = cag_answer.strip()
                logger.info(f"Generated summary for {filename}: {len(summary)} chars")
                return summary
                    
        except Exception as e:
            logger.warning(f"Failed to generate LLM summary: {e}")
        
        return self._create_simple_summary(text, filename)
    
    def _create_simple_summary(self, text: str, filename: str) -> str:
        """Create a simple summary without LLM"""
        # Clean up text
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Use DocumentTypeDetector for accurate type detection
        try:
            from app.services.document_type_detector import get_document_type_detector
            detector = get_document_type_detector()
            doc_type, confidence = detector.detect_type(text, filename)
            
            # Capitalize first letter for display
            doc_type_display = doc_type.capitalize()
            
            # Add confidence indicator if low
            if confidence < 0.5:
                doc_type_display = f"Possible {doc_type_display}"
        except Exception as e:
            logger.warning(f"Could not use DocumentTypeDetector: {e}")
            # Fallback to basic detection
            doc_type_display = "Document"
        
        # Get first meaningful lines
        meaningful_lines = []
        for line in lines[:10]:
            if len(line) > 20:  # Skip very short lines
                meaningful_lines.append(line)
                if len(meaningful_lines) >= 3:
                    break
        
        if meaningful_lines:
            preview = " ".join(meaningful_lines[:2])[:200]
            return f"{doc_type_display}: {filename}. {preview}..."
        else:
            return f"{doc_type_display}: {filename}. Content preview: {text[:200]}..."
    
    async def _perform_routing_analysis(self, db: AsyncSession, doc_info: dict, text: str, file_ext: str):
        """
        Routing de documentos desactivado.

        Este método pertenecía al pipeline legacy de AgentRouter, pero ahora la orquestación
        corre dentro del servicio de Elysia/CAG. Lo dejamos como no-op para evitar disparar
        el stack antiguo hasta que exista una integración oficial con el nuevo motor.
        """
        logger.debug(
            "Routing legacy deshabilitado para el documento %s; "
            "Elysia/CAG se encargará de la orquestación.",
            doc_info.get("id"),
        )
    
    async def get_document_agents(self, db: AsyncSession, doc_id: str) -> Dict[str, Any]:
        """
        Get agents assigned to a specific document based on its type and tags.
        """
        # Get document details
        document = await self.get_document(db, doc_id)
        
        # Determine document type and tags
        doc_tags = [tag.name for tag in document.tags] if document.tags else []
        doc_type = document.category or "general"
        
        # Map document characteristics to agent types
        assigned_agents = []
        
        # Check if document is signable
        is_signable = any(tag in ["signable", "contract", "agreement"] for tag in doc_tags)
        if is_signable:
            assigned_agents.append({
                "id": f"sig-{doc_id}",
                "name": "Digital Signature Agent",
                "type": "digital_signature",
                "status": "ready",
                "description": "Manages digital signature workflows",
                "capabilities": ["signature_requests", "status_tracking", "signer_management"]
            })
        
        # Check if document needs legal compliance
        is_legal = any(tag in ["legal", "contract", "compliance"] for tag in doc_tags) or doc_type == "legal"
        if is_legal:
            assigned_agents.append({
                "id": f"legal-{doc_id}",
                "name": "Legal Compliance Agent",
                "type": "legal_compliance",
                "status": "ready",
                "description": "Validates legal requirements",
                "capabilities": ["compliance_check", "risk_assessment", "regulatory_analysis"]
            })
        
        # Check if document is financial
        is_financial = any(tag in ["financial", "invoice", "report"] for tag in doc_tags) or doc_type == "financial"
        if is_financial:
            assigned_agents.append({
                "id": f"fin-{doc_id}",
                "name": "Financial Analysis Agent",
                "type": "financial_analyzer",
                "status": "ready",
                "description": "Analyzes financial documents",
                "capabilities": ["financial_metrics", "trend_analysis", "report_generation"]
            })
        
        # Document analyzer is always available
        assigned_agents.append({
            "id": f"doc-{doc_id}",
            "name": "Document Analyzer",
            "type": "document_analyzer",
            "status": "ready",
            "description": "Analyzes document content and structure",
            "capabilities": ["content_analysis", "extraction", "summarization"]
        })
        
        # RAG assistant for Q&A
        assigned_agents.append({
            "id": f"rag-{doc_id}",
            "name": "RAG Assistant",
            "type": "rag_assistant",
            "status": "ready",
            "description": "Answers questions about the document",
            "capabilities": ["document_search", "context_qa", "knowledge_retrieval"]
        })
        
        return {
            "document_id": doc_id,
            "document_type": doc_type,
            "tags": doc_tags,
            "assigned_agents": assigned_agents,
            "total_agents": len(assigned_agents)
        }

    async def _extract_entities_langextract(
        self, 
        text: str, 
        doc_type: str = "general", 
        filename: str = None
    ) -> Dict[str, Any]:
        """Proxy to the shared LangExtract client."""
        try:
            return await langextract_client.extract_entities(
                text=text,
                document_type=doc_type,
                filename=filename,
            )
        except Exception as exc:
            logger.error("❌ LangExtract entity extraction failed: %s", exc)
            return {
                "success": False,
                "error": str(exc),
                "extractions": [],
                "extraction_type": doc_type or "general",
            }

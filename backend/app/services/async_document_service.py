"""
Async version of DocumentService for use with AsyncSession
"""
import logging
import os
import uuid
import datetime
import io
import asyncio
import base64
import httpx
from typing import List, Dict, Any, Optional
from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload, joinedload

from app.core.config import settings
from app.core.auth.base import UserProfile
from app.core.auth.acl import filter_visible_to_user, EVERYONE_ROLE
from app.db.models import Document, IndexedDocument, Tag, DocumentView, FolderMarker
from app.db.async_database import AsyncSessionLocal
from app.schemas.enums import IndexingStatus
from app.services.async_storage_factory import AsyncStorageServiceFactory
from app.services.weaviate_client import weaviate_client
from app.services.queue_service import queue_service
from app.services.folder_classification_service import classify_document as classify_document_folder

logger = logging.getLogger(__name__)


class AsyncDocumentService:
    """Async version of Document Service (single-tenant, role-based ACL)."""

    def __init__(self, user: Optional[UserProfile] = None):
        """
        Initialize async document service.

        Note: The async init pattern requires using a factory method (`create`).
        """
        self.user = user
        self.user_id: Optional[str] = user.sub if user else None
        self.user_roles: List[str] = list(user.roles) if user else []
        self.storage_service = None
        self.collection_name: Optional[str] = None  # Weaviate collection name
        self._initialized = False

    async def _call_cag_query(
        self,
        query: str,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: float = 45.0
    ) -> Optional[str]:
        """
        Helper to call the CAG microservice and return the LLM answer.
        Falls back quietly if the service is unavailable.
        """
        import httpx

        user = user_id or self.user_id or "system"
        payload = {
            "query": query,
            "user_id": str(user),
            "context": context or {}
        }
        headers = {
            "X-API-Key": settings.MICROSERVICES_API_KEY,
            "X-User-Roles": ",".join(self.user_roles),
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
                "CAG query failed | user=%s error=%s",
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
    async def create(cls, user: Optional[UserProfile] = None, db: AsyncSession = None):
        """
        Factory method to create and initialize AsyncDocumentService.
        """
        service = cls(user)
        await service._initialize(db)
        return service

    async def _initialize(self, db: AsyncSession = None):
        """Initialize the service with async operations."""
        # Single-tenant deployment: storage factory still takes a legacy
        # positional bucket-scope string (slated for Plan 2 storage cleanup).
        storage_scope = settings.DEFAULT_TENANT_ID

        if db:
            self.storage_service = await AsyncStorageServiceFactory.create_storage_service(
                storage_scope, self.user_id, db
            )
        else:
            async with AsyncSessionLocal() as new_db:
                self.storage_service = await AsyncStorageServiceFactory.create_storage_service(
                    storage_scope, self.user_id, new_db
                )

        # Single shared Weaviate collection for the deployment.
        self.collection_name = "Nouxcube_documents"
        self.weaviate_service_url = getattr(settings, 'WEAVIATE_SERVICE_URL', 'http://weaviate-service:8000')
        self.microservices_api_key = getattr(settings, 'MICROSERVICES_API_KEY', '')

        self._initialized = True

    async def _call_indexing_pipeline(
        self,
        document_id: str,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Call the unified IndexingPipeline via weaviate-service.

        This replaces manual text extraction + Weaviate storage with a single
        call that handles: text extraction, semantic chunking, embeddings, and storage.

        Args:
            document_id: UUID of the document
            file_bytes: Raw file content
            filename: Original filename
            mime_type: MIME type of the file
            metadata: Additional metadata to store

        Returns:
            Dict with success status, weaviate_id, chunks_count, etc.
        """
        file_base64 = base64.b64encode(file_bytes).decode('utf-8')

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.microservices_api_key,
            "X-User-Roles": ",".join(self.user_roles),
        }

        payload = {
            "document_id": str(document_id),
            "file_bytes_base64": file_base64,
            "filename": filename,
            "mime_type": mime_type,
            "owner_id": str(self.user_id) if self.user_id else "",
            "metadata": metadata or {},
            "acl": {},  # ACL will be set later
        }

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=5.0)
        ) as client:
            try:
                logger.info(f"📤 Calling IndexingPipeline for document {document_id}")
                response = await client.post(
                    f"{self.weaviate_service_url}/weaviate/index/from-connector",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                logger.info(
                    f"✅ IndexingPipeline success for {document_id}: "
                    f"weaviate_id={result.get('weaviate_id')}, "
                    f"chunks={result.get('chunks_count', 0)}"
                )
                return result

            except httpx.HTTPStatusError as e:
                error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                logger.error(f"❌ IndexingPipeline error for {document_id}: {error_msg}")
                return {"success": False, "error": error_msg}
            except Exception as e:
                logger.error(f"❌ IndexingPipeline exception for {document_id}: {e}")
                return {"success": False, "error": str(e)}

    async def _call_weaviate_search(
        self,
        query: str,
        limit: int = 20,
        user_id: Optional[str] = None,
        user_role_ids: Optional[List[str]] = None,
        is_admin: bool = False,
        filters: Optional[Dict[str, Any]] = None,
        search_type: str = "hybrid",
    ) -> Dict[str, Any]:
        """
        Call Weaviate hybrid search to replace Elasticsearch.

        Weaviate provides:
        - Vector search (semantic similarity)
        - Keyword search (BM25)
        - Hybrid search (combines both)

        Args:
            query: Search query text
            limit: Maximum results to return
            user_id: User ID for ACL filtering
            user_role_ids: User's role IDs for ACL filtering
            is_admin: Admin bypass for ACL
            filters: Additional filters (category, tags, dates)
            search_type: "vector", "keyword", or "hybrid"

        Returns:
            Dict with results, total_results, search_time_ms
        """
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.microservices_api_key,
            "X-User-Roles": ",".join(self.user_roles),
        }

        payload = {
            "query": query,
            "limit": limit,
            "user_id": user_id,
            "user_role_ids": user_role_ids or [],
            "is_admin": is_admin,
            "filters": filters or {},
            "search_type": search_type,
        }

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)
        ) as client:
            try:
                logger.info(f"🔍 Weaviate hybrid search: '{query}' (type={search_type})")
                response = await client.post(
                    f"{self.weaviate_service_url}/weaviate/collections/{self.collection_name}/search",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
                logger.info(
                    f"✅ Weaviate search returned {result.get('total_results', 0)} results "
                    f"in {result.get('search_time_ms', 0)}ms"
                )
                return result

            except httpx.HTTPStatusError as e:
                error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                logger.error(f"❌ Weaviate search error: {error_msg}")
                return {"results": [], "total_results": 0, "error": error_msg}
            except Exception as e:
                logger.error(f"❌ Weaviate search exception: {e}")
                return {"results": [], "total_results": 0, "error": str(e)}

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

            # Use Weaviate hybrid search (vector + BM25) for text queries
            if search and search.strip():
                # Build filters for Weaviate
                weaviate_filters = {}
                if category:
                    weaviate_filters["category"] = category
                if tags:
                    weaviate_filters["tags"] = tags
                if date_from:
                    weaviate_filters["date_from"] = date_from
                if date_to:
                    weaviate_filters["date_to"] = date_to
                # ACL: Add document_ids filter
                if document_ids is not None:
                    weaviate_filters["document_ids"] = [str(doc_id) for doc_id in document_ids]

                # Build user context for ACL filtering
                user_role_ids = []
                is_admin = False
                if self.user_id:
                    try:
                        from app.db.models import User
                        user_result = await db.execute(
                            select(User).options(selectinload(User.roles)).filter(User.id == uuid.UUID(self.user_id))
                        )
                        user = user_result.scalars().first()
                        if user:
                            user_role_ids = [str(role.id) for role in user.roles] if user.roles else []
                            is_admin = user.is_admin
                    except Exception as ctx_exc:
                        logger.warning(f"Could not build user context for ACL filtering: {ctx_exc}")

                # Call Weaviate hybrid search
                search_result = await self._call_weaviate_search(
                    query=search,
                    limit=per_page * 2,  # Get more results to account for filtering
                    user_id=self.user_id,
                    user_role_ids=user_role_ids,
                    is_admin=is_admin,
                    filters=weaviate_filters,
                    search_type="hybrid",
                )

                if search_result.get("error"):
                    logger.warning(f"Weaviate search failed, falling back to SQL: {search_result.get('error')}")
                    # Fall through to SQL search below
                else:
                    weaviate_results = search_result.get("results", [])
                    total_results = search_result.get("total_results", len(weaviate_results))

                    # Return Weaviate results directly (no PostgreSQL query needed)
                    # Weaviate already has all document metadata
                    offset = (page - 1) * per_page
                    paginated_results = weaviate_results[offset:offset + per_page]

                    items = []
                    for res in paginated_results:
                        # Convert Weaviate result to expected document format
                        doc_dict = {
                            "id": res.get("id"),
                            "title": res.get("title", ""),
                            "filename": res.get("title", ""),  # Weaviate uses title as filename
                            "description": res.get("metadata", {}).get("description", ""),
                            "content_preview": (res.get("content", "")[:500] + "...") if res.get("content") else "",
                            "file_type": res.get("metadata", {}).get("file_type", ""),
                            "file_size": res.get("metadata", {}).get("file_size"),
                            "mime_type": res.get("metadata", {}).get("mime_type", ""),
                            "category": res.get("document_type", ""),
                            "tags": res.get("tags", []),
                            "created_at": res.get("created_at"),
                            "updated_at": res.get("updated_at"),
                            "search_score": res.get("similarity_score", 0.0),
                            "source": "weaviate",  # Indicate source for frontend
                        }
                        items.append(doc_dict)

                    return {
                        "items": items,
                        "total": total_results,
                        "page": page,
                        "per_page": per_page,
                        "total_pages": (total_results + per_page - 1) // per_page,
                        "search_engine": "weaviate_hybrid"
                    }

            # SQL search when no search term or Weaviate fails
            logger.info("Using SQL-based document search (Document + IndexedDocument)")

            # Role-based ACL filters (applied via clauses below).
            # Document: use shared helper.
            # IndexedDocument: inline role overlap clause (helper is Document-only).
            base_filters = []
            if self.user:
                from app.core.auth.acl import build_role_filter_clause
                base_filters.append(build_role_filter_clause(self.user))

            indexed_base_filters = [IndexedDocument.roles.contains([EVERYONE_ROLE])]
            if self.user_roles:
                indexed_base_filters = [
                    or_(
                        IndexedDocument.roles.contains([EVERYONE_ROLE]),
                        IndexedDocument.roles.overlap(list(self.user_roles)),
                    )
                ]

            # ACL: Filter by accessible document IDs
            if document_ids is not None:
                base_filters.append(Document.id.in_(document_ids))
                indexed_base_filters.append(IndexedDocument.id.in_(document_ids))

            # Folder filtering (Google Drive style)
            folder_items = []  # Subfolders to include at the beginning
            current_folder = ""  # Initialize for later use
            if folder is not None:
                # Normalize folder path
                current_folder = folder.strip() if folder else ""
                if current_folder and not current_folder.startswith("/"):
                    current_folder = "/" + current_folder

                if current_folder:
                    # Filter documents in this specific folder only (not subfolders)
                    base_filters.append(Document.folder_path == current_folder)
                    indexed_base_filters.append(IndexedDocument.external_path == current_folder)
                else:
                    # Root folder: show documents with no folder or empty folder_path
                    base_filters.append(
                        or_(
                            Document.folder_path.is_(None),
                            Document.folder_path == "",
                            Document.folder_path == "/"
                        )
                    )
                    indexed_base_filters.append(
                        or_(
                            IndexedDocument.external_path.is_(None),
                            IndexedDocument.external_path == "",
                            IndexedDocument.external_path == "/"
                        )
                    )

                # Get immediate subfolders as items (Google Drive style)
                # Query to find distinct folder_path values that are direct children
                from sqlalchemy import distinct, case, literal
                from collections import defaultdict

                # Collect subfolders from BOTH tables
                folder_counts = defaultdict(int)

                # === Document table subfolders ===
                if current_folder:
                    # Find folders that start with current_folder/ but are only one level deeper
                    subfolder_query = (
                        select(
                            Document.folder_path,
                            func.count(Document.id).label("document_count")
                        )
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
                        .where(Document.folder_path.isnot(None))
                        .where(Document.folder_path != "")
                        .where(Document.folder_path != "/")
                        .group_by(Document.folder_path)
                    )
                if self.user:
                    subfolder_query = filter_visible_to_user(subfolder_query, self.user)

                # === IndexedDocument table subfolders ===
                if current_folder:
                    indexed_subfolder_query = (
                        select(
                            IndexedDocument.external_path,
                            func.count(IndexedDocument.id).label("document_count")
                        )
                        .where(IndexedDocument.external_path.isnot(None))
                        .where(IndexedDocument.external_path.startswith(current_folder + "/"))
                        .group_by(IndexedDocument.external_path)
                    )
                else:
                    indexed_subfolder_query = (
                        select(
                            IndexedDocument.external_path,
                            func.count(IndexedDocument.id).label("document_count")
                        )
                        .where(IndexedDocument.external_path.isnot(None))
                        .where(IndexedDocument.external_path != "")
                        .where(IndexedDocument.external_path != "/")
                        .group_by(IndexedDocument.external_path)
                    )
                for _f in indexed_base_filters:
                    indexed_subfolder_query = indexed_subfolder_query.where(_f)

                # ACL: Filter subfolders by accessible document IDs
                if document_ids is not None:
                    subfolder_query = subfolder_query.where(Document.id.in_(document_ids))
                    indexed_subfolder_query = indexed_subfolder_query.where(IndexedDocument.id.in_(document_ids))

                # Execute BOTH subfolder queries
                subfolder_result = await db.execute(subfolder_query)
                all_subpaths = subfolder_result.all()

                indexed_subfolder_result = await db.execute(indexed_subfolder_query)
                indexed_subpaths = indexed_subfolder_result.all()

                # Combine results from both tables
                all_subpaths = list(all_subpaths) + list(indexed_subpaths)

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

                        # Count documents in this subfolder (recursively) from BOTH tables
                        # Document table count (ACL filtered)
                        doc_count_query = (
                            select(func.count(Document.id))
                            .where(Document.folder_path.startswith(child_path))
                        )
                        if self.user:
                            doc_count_query = filter_visible_to_user(doc_count_query, self.user)
                        if document_ids is not None:
                            doc_count_query = doc_count_query.where(Document.id.in_(document_ids))
                        doc_count_result = await db.execute(doc_count_query)
                        doc_count = doc_count_result.scalar() or 0

                        # IndexedDocument table count (role-overlap)
                        indexed_count_query = (
                            select(func.count(IndexedDocument.id))
                            .where(IndexedDocument.external_path.startswith(child_path))
                        )
                        for _f in indexed_base_filters:
                            indexed_count_query = indexed_count_query.where(_f)
                        if document_ids is not None:
                            indexed_count_query = indexed_count_query.where(IndexedDocument.id.in_(document_ids))
                        indexed_count_result = await db.execute(indexed_count_query)
                        indexed_count = indexed_count_result.scalar() or 0

                        subfolder_doc_count = doc_count + indexed_count

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
                        .where(FolderMarker.folder_path.startswith(current_folder + "/"))
                    )
                else:
                    # Root: find all top-level folder markers
                    marker_query = (
                        select(FolderMarker.folder_path, FolderMarker.created_at)
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

            # === Query Document table ===
            doc_query = select(Document).filter(
                *base_filters
            ).options(
                selectinload(Document.tags),
                selectinload(Document.creator)
            )

            # === Query IndexedDocument table ===
            indexed_query = select(IndexedDocument).filter(
                *indexed_base_filters
            )

            # Apply filters to Document query
            if search:
                doc_query = doc_query.filter(
                    or_(
                        Document.title.ilike(f"%{search}%"),
                        Document.description.ilike(f"%{search}%"),
                        Document.filename.ilike(f"%{search}%")
                    )
                )
                indexed_query = indexed_query.filter(
                    or_(
                        IndexedDocument.title.ilike(f"%{search}%"),
                        IndexedDocument.description.ilike(f"%{search}%")
                    )
                )

            if category:
                doc_query = doc_query.filter(Document.category == category)
                # IndexedDocument doesn't have category field, skip

            if tags:
                # Join with tags (only for Document table)
                doc_query = doc_query.join(Document.tags).filter(
                    Tag.name.in_(tags)
                )
                # IndexedDocument doesn't have tags relation, skip

            if date_from:
                date_from_obj = datetime.datetime.fromisoformat(date_from)
                doc_query = doc_query.filter(Document.created_at >= date_from_obj)
                indexed_query = indexed_query.filter(IndexedDocument.created_at >= date_from_obj)

            if date_to:
                date_to_obj = datetime.datetime.fromisoformat(date_to)
                doc_query = doc_query.filter(Document.created_at <= date_to_obj)
                indexed_query = indexed_query.filter(IndexedDocument.created_at <= date_to_obj)

            # Count total documents from BOTH tables
            doc_count_query = select(func.count()).select_from(doc_query.subquery())
            doc_count_result = await db.execute(doc_count_query)
            doc_total = doc_count_result.scalar() or 0

            indexed_count_query = select(func.count()).select_from(indexed_query.subquery())
            indexed_count_result = await db.execute(indexed_count_query)
            indexed_total = indexed_count_result.scalar() or 0

            total_docs = doc_total + indexed_total

            # Total items = folders + documents from both tables
            total = len(folder_items) + total_docs

            # Pagination logic accounting for folders
            # Folders are always shown first on page 1
            offset = (page - 1) * per_page

            if page == 1:
                # First page: show folders first, then documents
                docs_to_fetch = per_page - len(folder_items)
                doc_query = doc_query.offset(0).limit(max(0, docs_to_fetch)).order_by(Document.created_at.desc())
                indexed_query = indexed_query.offset(0).limit(max(0, docs_to_fetch)).order_by(IndexedDocument.created_at.desc())
            else:
                # Other pages: adjust offset for folders shown on page 1
                adjusted_offset = offset - len(folder_items)
                doc_query = doc_query.offset(max(0, adjusted_offset)).limit(per_page).order_by(Document.created_at.desc())
                indexed_query = indexed_query.offset(max(0, adjusted_offset)).limit(per_page).order_by(IndexedDocument.created_at.desc())

            # Execute BOTH queries
            doc_result = await db.execute(doc_query)
            documents = doc_result.scalars().all()

            indexed_result = await db.execute(indexed_query)
            indexed_documents = indexed_result.scalars().all()

            # Convert Document objects to dict with type="document"
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
                    } if doc.creator else None,
                    "source": "upload"  # Indicate source for frontend
                }
                doc_items.append(doc_dict)

            # Convert IndexedDocument objects to dict
            for indexed_doc in indexed_documents:
                doc_items.append(self._indexed_document_to_dict(indexed_doc))

            # Sort combined results by created_at descending
            doc_items.sort(key=lambda x: x.get("created_at") or "", reverse=True)

            # Apply pagination limit to combined results
            if page == 1:
                docs_limit = per_page - len(folder_items)
            else:
                docs_limit = per_page
            doc_items = doc_items[:max(0, docs_limit)]

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
                "document_count": total_docs,
                "breakdown": {
                    "uploads": doc_total,
                    "connectors": indexed_total
                }
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

    def _indexed_document_to_dict(self, doc: IndexedDocument) -> Dict[str, Any]:
        """Convert IndexedDocument model (from connectors) to dictionary"""
        # Map indexing_status to display string
        status_map = {
            "indexed": "Indexado",
            "pending": "Pendiente",
            "processing": "Procesando",
            "failed": "Error"
        }
        indexed_status = status_map.get(doc.indexing_status, doc.indexing_status or "Pendiente")

        return {
            "id": str(doc.id),
            "type": "document",
            "title": doc.title,
            "description": doc.description,
            "filename": doc.title,  # IndexedDocument uses title as filename
            "folder_path": doc.external_path,
            "file_type": doc.file_extension,
            "file_size": doc.size_bytes or 0,
            "mime_type": doc.mime_type,
            "indexed": indexed_status,
            "category": None,  # IndexedDocument doesn't have category
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            "tags": [],  # IndexedDocument doesn't have tags relation
            "created_by": None,  # Would need to join with User table
            # Connector-specific fields
            "source": "connector",
            "connector_type": doc.connector_type,
            "connector_id": str(doc.connector_id) if doc.connector_id else None,
            "external_id": doc.external_id,
            "external_url": doc.external_url,
            "weaviate_id": str(doc.weaviate_id) if doc.weaviate_id else None,
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
        folder_path: Optional[str] = None,
        roles: Optional[List[str]] = None,
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
                roles=roles or [EVERYONE_ROLE],
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
                    stmt = select(Tag).filter(Tag.name == tag_name)
                    result = await db.execute(stmt)
                    tag = result.scalar_one_or_none()

                    if not tag:
                        tag = Tag(name=tag_name)
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
                "user_id": self.user_id,
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
        """
        Process document in background using unified IndexingPipeline.

        This method now uses the weaviate-service's IndexingPipeline for:
        - Text extraction (via Tika)
        - Semantic chunking
        - Embedding generation
        - Weaviate storage

        After indexing, it performs additional enrichment:
        - Auto-categorization via LangExtract
        - Entity extraction
        - Folder classification (Learn-First approach)
        """
        doc_id = doc_info["id"]
        try:
            logger.info(f"🚀 Starting async processing for document {doc_id}, file type: {file_ext}")

            # Get document metadata for IndexingPipeline
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
                    "filename": doc.filename,
                    "title": doc.title or doc.filename,
                    "description": doc.description,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "file_size": doc.file_size,
                    "mime_type": doc.mime_type,
                    "category": doc.category,
                    "tags": tags_list,
                }
                mime_type = doc.mime_type or "application/octet-stream"

            # Call unified IndexingPipeline (handles extraction, chunking, embedding, storage)
            pipeline_result = await self._call_indexing_pipeline(
                document_id=doc_id,
                file_bytes=contents,
                filename=doc_info.get("filename"),
                mime_type=mime_type,
                metadata=metadata,
            )

            if not pipeline_result.get("success"):
                error_msg = pipeline_result.get("error", "Unknown indexing error")
                raise Exception(f"IndexingPipeline failed: {error_msg}")

            # Get extracted text preview for downstream operations
            text_preview = pipeline_result.get("extracted_text_preview", "")
            extraction_language = pipeline_result.get("extraction_language", "unknown")
            chunk_count = pipeline_result.get("chunk_count", 0)

            if not text_preview:
                logger.warning(f"No text extracted from document {doc_id}")
                raise Exception("No text could be extracted from the document")

            logger.info(
                f"✅ IndexingPipeline completed for {doc_id}: "
                f"{chunk_count} chunks, language={extraction_language}"
            )

            # Update document status and metadata
            async with AsyncSessionLocal() as db:
                stmt = select(Document).options(selectinload(Document.tags)).filter(Document.id == doc_id)
                result = await db.execute(stmt)
                doc = result.scalar_one_or_none()

                if doc:
                    # Generate summary from text preview
                    summary = await self._generate_document_summary(text_preview, doc_info["filename"])

                    current_metadata = dict(doc.document_metadata or {})
                    current_metadata["text_extraction"] = {
                        "language": extraction_language,
                        "chunk_count": chunk_count,
                        "indexing_pipeline": "unified",
                    }
                    if summary:
                        current_metadata["summary"] = summary
                        current_metadata.setdefault("text_preview", summary[:500])
                    doc.document_metadata = current_metadata

                    # Mark as indexed (Weaviate only - ES deprecated)
                    doc.indexed = IndexingStatus.INDEXED
                    doc.indexing_error = None

                    await db.commit()
                    logger.info(f"✅ Document {doc_id} marked as INDEXED")

            # Auto-categorize via LangExtract
            category = None
            try:
                category = await self._auto_categorize_document(
                    doc_id,
                    text_content=text_preview,
                    user_id=self.user_id,
                    source="auto_ingest",
                )
                if category:
                    logger.info(f"Document {doc_id} categorized as '{category}'")
            except Exception as e:
                logger.warning(f"Auto-categorization failed for {doc_id}: {e}")

            # Entity extraction handled by indexing pipeline (intelligence-docs-service → Weaviate/FalkorDB)

            # Auto-classify folder (Learn-First approach)
            try:
                await self._auto_classify_folder(
                    doc_id=doc_id,
                    text_content=text_preview,
                    filename=doc_info.get("filename"),
                    file_type=file_ext,
                )
            except Exception as e:
                logger.warning(f"Folder classification failed for {doc_id}: {e}")

            logger.info(f"🎉 Document {doc_id} processing completed successfully")

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
        """Get single document by ID from Document table.

        Note: This method only searches the Document table (SaaS uploads).
        For connector documents, use get_indexed_document() or get_any_document().
        """
        stmt = select(Document).filter(Document.id == doc_id).options(
            selectinload(Document.tags),
            selectinload(Document.creator)
        )
        if self.user:
            stmt = filter_visible_to_user(stmt, self.user)

        result = await db.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return doc

    async def get_indexed_document(self, db: AsyncSession, doc_id: str) -> IndexedDocument:
        """Get single document by ID from IndexedDocument table (connector documents)."""
        stmt = select(IndexedDocument).filter(IndexedDocument.id == uuid.UUID(doc_id))
        if self.user_roles:
            stmt = stmt.filter(
                or_(
                    IndexedDocument.roles.contains([EVERYONE_ROLE]),
                    IndexedDocument.roles.overlap(list(self.user_roles)),
                )
            )
        else:
            stmt = stmt.filter(IndexedDocument.roles.contains([EVERYONE_ROLE]))

        result = await db.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="IndexedDocument not found")

        return doc

    async def get_any_document(self, db: AsyncSession, doc_id: str) -> Dict[str, Any]:
        """Get single document by ID from either Document or IndexedDocument table.

        This method searches both tables and returns a unified dictionary format.
        Use this for on-premise deployments where documents come from connectors.

        Returns:
            Dict with unified document format including 'source' field ('upload' or 'connector')
        """
        # First try Document table
        doc_stmt = select(Document).filter(Document.id == doc_id).options(
            selectinload(Document.tags),
            selectinload(Document.creator)
        )
        if self.user:
            doc_stmt = filter_visible_to_user(doc_stmt, self.user)

        doc_result = await db.execute(doc_stmt)
        doc = doc_result.scalar_one_or_none()

        if doc:
            result = self._document_to_dict(doc)
            result["source"] = "upload"
            return result

        # Try IndexedDocument table
        try:
            indexed_stmt = select(IndexedDocument).filter(
                IndexedDocument.id == uuid.UUID(doc_id)
            )
            if self.user_roles:
                indexed_stmt = indexed_stmt.filter(
                    or_(
                        IndexedDocument.roles.contains([EVERYONE_ROLE]),
                        IndexedDocument.roles.overlap(list(self.user_roles)),
                    )
                )
            else:
                indexed_stmt = indexed_stmt.filter(IndexedDocument.roles.contains([EVERYONE_ROLE]))

            indexed_result = await db.execute(indexed_stmt)
            indexed_doc = indexed_result.scalar_one_or_none()

            if indexed_doc:
                return self._indexed_document_to_dict(indexed_doc)
        except ValueError:
            # Invalid UUID format, skip IndexedDocument search
            pass

        raise HTTPException(status_code=404, detail="Document not found in either table")
    
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

            # Classify via intelligence-docs-service
            import httpx
            intelligence_url = os.getenv(
                "INTELLIGENCE_DOCS_SERVICE_URL", "http://intelligence-docs-service:8000"
            )
            logger.info(f"Classifying document {doc_id} via intelligence-docs-service")
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{intelligence_url}/classify",
                        json={"text": snippet[:5000], "filename": doc.filename or ""},
                    )
                    resp.raise_for_status()
                    data = resp.json()
            except Exception as classify_err:
                logger.warning(f"Classification failed for {doc_id}: {classify_err}")
                return None

            category = data.get("document_type", "general")
            confidence = data.get("confidence", 0.0)

            doc.category = category
            updated_metadata = dict(doc.document_metadata or {})
            updated_metadata["auto_categorization"] = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "method": "intelligence-docs-service",
                "source": source,
                "detected_type": category,
                "confidence": confidence,
            }
            doc.document_metadata = updated_metadata
            await session.commit()

            logger.info(f"Document {doc_id} categorized as '{category}' (confidence: {confidence:.2f})")
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
        # NOTE: In the multi-tenant era, auto_classification config lived on the
        # Tenant row. Post-refactor the Tenant model is gone; until these knobs
        # are moved into `settings`, we hardcode defaults (k=5, min_conf=0.6)
        # and always attempt classification.
        auto_classification_k = 5
        auto_classification_min_confidence = 0.6

        async with AsyncSessionLocal() as session:
            try:
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
                    documento=documento,
                    k=auto_classification_k,
                    min_confidence=auto_classification_min_confidence,
                )

                # Check confidence threshold
                if classification.confianza < auto_classification_min_confidence:
                    logger.info(
                        f"📁 Confidence ({classification.confianza:.2f}) below threshold "
                        f"({auto_classification_min_confidence}). "
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
        user_id: str,
        source: str = "manual",
    ) -> Dict[str, Any]:
        """Public helper to categorize/re-categorize a document."""
        category = await self._auto_categorize_document(
            doc_id,
            text_content=content_preview,
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
            # Get document (ACL-filtered)
            stmt = select(Document).filter(Document.id == doc_id).options(selectinload(Document.tags))
            if self.user:
                stmt = filter_visible_to_user(stmt, self.user)

            result = await db.execute(stmt)
            document = result.scalar_one_or_none()

            if not document:
                raise HTTPException(status_code=404, detail="Document not found")

            # Check if tag already exists
            tag_stmt = select(Tag).filter(Tag.name == tag_name)
            tag_result = await db.execute(tag_stmt)
            tag = tag_result.scalar_one_or_none()

            if not tag:
                # Create new tag
                tag = Tag(name=tag_name)
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
            # Get document (ACL-filtered)
            stmt = select(Document).filter(Document.id == doc_id).options(selectinload(Document.tags))
            if self.user:
                stmt = filter_visible_to_user(stmt, self.user)
            
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
        Mark document as viewed by current user.

        Searches both Document (SaaS uploads) and IndexedDocument (connector documents)
        tables to support on-premise deployments.

        Args:
            document_id: ID of the document being viewed
            view_duration_seconds: Optional duration of view in seconds
            scroll_percentage: Optional percentage of document scrolled

        Returns:
            view_id: ID of the created view record
        """
        try:
            async with AsyncSessionLocal() as db:
                # Check if document exists in Document table (ACL-filtered)
                doc_stmt = select(Document).filter(Document.id == document_id)
                if self.user:
                    doc_stmt = filter_visible_to_user(doc_stmt, self.user)
                doc_result = await db.execute(doc_stmt)
                document = doc_result.scalar_one_or_none()

                # If not found, check IndexedDocument table
                if not document:
                    try:
                        indexed_stmt = select(IndexedDocument).filter(
                            IndexedDocument.id == uuid.UUID(document_id)
                        )
                        if self.user_roles:
                            indexed_stmt = indexed_stmt.filter(
                                or_(
                                    IndexedDocument.roles.contains([EVERYONE_ROLE]),
                                    IndexedDocument.roles.overlap(list(self.user_roles)),
                                )
                            )
                        else:
                            indexed_stmt = indexed_stmt.filter(
                                IndexedDocument.roles.contains([EVERYONE_ROLE])
                            )
                        indexed_result = await db.execute(indexed_stmt)
                        indexed_doc = indexed_result.scalar_one_or_none()

                        if not indexed_doc:
                            raise HTTPException(status_code=404, detail="Document not found in either table")

                        # IndexedDocument found - use it for the view record
                        document = indexed_doc
                    except ValueError:
                        raise HTTPException(status_code=404, detail="Document not found")
                
                # Create or update document view record
                view_record = DocumentView(
                    user_id=self.user_id,
                    document_id=document_id,
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
                # Base query with Document and DocumentView joined (ACL-filtered)
                query = select(
                    Document,
                    func.max(DocumentView.viewed_at).label("last_viewed_at")
                ).join(
                    DocumentView, Document.id == DocumentView.document_id
                )
                if self.user:
                    query = filter_visible_to_user(query, self.user)

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


"""
API endpoints for entity management and search
"""
import logging

logger = logging.getLogger(__name__)
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, desc
from uuid import UUID
import hashlib

from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async
from app.db.async_database import get_async_db
from app.db.models import User, Document, DocumentView, DocumentShare, SignatureContact
from sqlalchemy.dialects.postgresql import JSONB
from app.schemas.entity import Entity, EntitySearchResponse

router = APIRouter()


@router.get("/search/entities", response_model=EntitySearchResponse)
async def search_entities(
    q: str = Query(..., min_length=1, description="Search query"),
    document_id: Optional[str] = Query(None, description="Filter by document associations"),
    limit: int = Query(10, ge=1, le=50),
    types: Optional[List[str]] = Query(None, description="Entity types to search"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Search for entities extracted from documents
    """
    logger.info(f"Entity search - Query: '{q}', Document ID: {document_id}, Tenant ID: {tenant_id}")
    
    entities = []
    search_pattern = f"%{q.lower()}%"
    
    # Build base query for documents with extracted entities
    doc_query = select(Document).where(
        and_(
            Document.tenant_id == UUID(tenant_id),
            Document.extracted_entities.isnot(None),
            Document.extracted_entities != []
        )
    )
    
    # Filter by specific document if provided (skip if document_id is "general" for global search)
    if document_id and document_id != "general":
        try:
            doc_query = doc_query.where(Document.id == UUID(document_id))
        except ValueError:
            logger.warning(f"Invalid document_id format: {document_id}. Treating as general search.")
            # Continue without document filter for invalid UUIDs
    
    # Execute query
    result = await db.execute(doc_query)
    documents = result.scalars().all()
    
    # Extract entities from documents and filter by search query and types
    seen_entities = {}  # Use dict to deduplicate by name+type
    
    for doc in documents:
        if doc.extracted_entities:
            for entity in doc.extracted_entities:
                entity_name = entity.get('name', '').lower()
                entity_type = entity.get('type', 'other')
                
                # Filter by search query
                if q.lower() in entity_name:
                    # Filter by types if specified
                    if not types or entity_type in types:
                        # Create unique key for deduplication
                        entity_key = f"{entity_name}:{entity_type}"
                        
                        if entity_key not in seen_entities:
                            # Generate a stable ID for the entity
                            entity_id = str(UUID(bytes=hashlib.md5(entity_key.encode()).digest(), version=4))
                            
                            seen_entities[entity_key] = {
                                "id": entity_id,
                                "name": entity.get('name', ''),
                                "type": entity_type,
                                "role": entity.get('role', ''),
                                "email": '',  # Entities from documents don't have emails
                                "metadata": {
                                    "context": entity.get('context', ''),
                                    "document_id": str(doc.id),
                                    "document_title": doc.title
                                }
                            }
    
    # Convert to list and sort by relevance
    entities = list(seen_entities.values())
    entities.sort(key=lambda e: e['name'])
    
    # Also search system users if 'user' type is requested
    if not types or 'user' in types:
        user_query = select(User).where(
            and_(
                User.tenant_id == UUID(tenant_id),
                or_(
                    func.lower(func.coalesce(User.full_name, '')).like(search_pattern),
                    func.lower(User.email).like(search_pattern)
                )
            )
        ).limit(5)  # Limit user results to not overwhelm entity results
        
        result = await db.execute(user_query)
        users = result.scalars().all()
        
        for user in users:
            entities.append({
                "id": str(user.id),
                "name": user.full_name or user.email,
                "email": user.email,
                "type": "user",
                "role": user.role if hasattr(user, 'role') else None,
                "metadata": {
                    "is_system_user": True
                }
            })
    
    # Search signature contacts if 'contact' or 'signer' type is requested
    if not types or 'contact' in types or 'signer' in types:
        contact_query = select(SignatureContact).where(
            and_(
                SignatureContact.tenant_id == UUID(tenant_id),
                or_(
                    func.lower(SignatureContact.name).like(search_pattern),
                    func.lower(SignatureContact.email).like(search_pattern),
                    func.lower(func.coalesce(SignatureContact.company, '')).like(search_pattern)
                )
            )
        ).order_by(
            desc(SignatureContact.is_favorite),
            desc(SignatureContact.usage_count)
        ).limit(10)
        
        result = await db.execute(contact_query)
        contacts = result.scalars().all()
        
        for contact in contacts:
            entities.append({
                "id": str(contact.id),
                "name": contact.name,
                "email": contact.email,
                "type": "contact",
                "role": contact.role or "Signer",
                "metadata": {
                    "is_signature_contact": True,
                    "is_favorite": contact.is_favorite,
                    "usage_count": contact.usage_count,
                    "company": contact.company,
                    "phone": contact.phone
                }
            })
    
    # Limit total results
    entities = entities[:limit]
    
    logger.info(f"Returning {len(entities)} total entities for query '{q}'")
    return EntitySearchResponse(
        entities=entities,
        total=len(entities)
    )


@router.get("/documents/{document_id}/entities", response_model=EntitySearchResponse)
async def get_document_entities(
    document_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get entities extracted from a specific document
    """
    # Verify document exists and user has access
    doc_query = select(Document).where(
        and_(
            Document.id == UUID(document_id),
            Document.tenant_id == UUID(tenant_id)
        )
    )
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    entities = []
    
    # Get entities extracted from the document
    if document.extracted_entities:
        for entity in document.extracted_entities:
            # Generate a stable ID for the entity
            entity_key = f"{entity.get('name', '')}:{entity.get('type', 'other')}"
            entity_id = str(UUID(bytes=hashlib.md5(entity_key.encode()).digest(), version=4))
            
            entities.append({
                "id": entity_id,
                "name": entity.get('name', ''),
                "type": entity.get('type', 'other'),
                "role": entity.get('role', ''),
                "email": '',  # Entities from documents don't have emails
                "metadata": {
                    "context": entity.get('context', ''),
                    "document_id": str(document.id),
                    "document_title": document.title,
                    "extraction_method": entity.get('metadata', {}).get('extraction_method', 'llm')
                }
            })
    
    # Also include document creator as a system entity
    creator_query = select(User).where(User.id == document.created_by)
    result = await db.execute(creator_query)
    creator = result.scalar_one_or_none()
    
    if creator:
        entities.append({
            "id": str(creator.id),
            "name": creator.full_name or creator.email,
            "email": creator.email,
            "type": "user",
            "role": "Document Creator",
            "metadata": {
                "is_system_user": True
            }
        })
    
    return EntitySearchResponse(
        entities=entities,
        total=len(entities)
    )


@router.get("/search/entities/recent", response_model=EntitySearchResponse)
async def get_recent_entities(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get recently interacted entities for quick selection.
    Returns users from the same tenant who have recent document views.
    """
    entities = []
    tenant_uuid = UUID(tenant_id)

    try:
        # Get users from recent document views with explicit join condition
        recent_users_query = (
            select(User)
            .join(DocumentView, DocumentView.user_id == User.id)
            .where(User.tenant_id == tenant_uuid)
            .order_by(desc(DocumentView.viewed_at))
            .distinct()
            .limit(limit)
        )

        result = await db.execute(recent_users_query)
        recent_users = result.scalars().all()

        for user in recent_users:
            entities.append({
                "id": str(user.id),
                "name": user.full_name or user.email,
                "email": user.email,
                "type": "user",
                "role": user.role if hasattr(user, 'role') else None
            })

        # If no recent users found, return users from the tenant
        if not entities:
            fallback_query = (
                select(User)
                .where(User.tenant_id == tenant_uuid)
                .order_by(desc(User.created_at))
                .limit(limit)
            )
            result = await db.execute(fallback_query)
            fallback_users = result.scalars().all()

            for user in fallback_users:
                entities.append({
                    "id": str(user.id),
                    "name": user.full_name or user.email,
                    "email": user.email,
                    "type": "user",
                    "role": user.role if hasattr(user, 'role') else None
                })

    except Exception as e:
        logging.error(f"Error fetching recent entities: {e}")
        # Return empty list on error instead of raising
        pass

    return EntitySearchResponse(
        entities=entities,
        total=len(entities)
    )
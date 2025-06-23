"""
API endpoints for entity management and search
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func
from uuid import UUID

from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async
from app.db.async_database import get_async_db
from app.db.models import User, Document, Agent, DocumentView, DocumentShare
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
    Search for entities (users, contacts, organizations, agents) with optional document context
    """
    entities = []
    search_pattern = f"%{q.lower()}%"
    
    # Search users in the same tenant
    if not types or 'user' in types:
        user_query = select(User).where(
            and_(
                User.tenant_id == UUID(tenant_id),
                or_(
                    func.lower(User.full_name).like(search_pattern),
                    func.lower(User.email).like(search_pattern)
                )
            )
        ).limit(limit)
        
        result = await db.execute(user_query)
        users = result.scalars().all()
        
        for user in users:
            entities.append({
                "id": str(user.id),
                "name": user.full_name or user.email,
                "email": user.email,
                "type": "user",
                "role": user.role if hasattr(user, 'role') else None
            })
    
    # Search agents
    if not types or 'agent' in types:
        agent_query = select(Agent).where(
            and_(
                Agent.tenant_id == UUID(tenant_id),
                or_(
                    func.lower(Agent.name).like(search_pattern),
                    func.lower(Agent.description).like(search_pattern)
                )
            )
        ).limit(limit)
        
        result = await db.execute(agent_query)
        agents = result.scalars().all()
        
        for agent in agents:
            entities.append({
                "id": str(agent.id),
                "name": agent.name,
                "email": f"{agent.name.lower().replace(' ', '.')}@agent.ai",
                "type": "agent",
                "role": agent.agent_type
            })
    
    # If document_id is provided, prioritize entities associated with the document
    if document_id:
        # Get users who have viewed or shared the document
        view_query = select(User).join(DocumentView).where(
            and_(
                DocumentView.document_id == UUID(document_id),
                User.tenant_id == UUID(tenant_id)
            )
        ).distinct()
        
        result = await db.execute(view_query)
        document_users = result.scalars().all()
        
        # Prioritize document-associated entities
        document_entity_ids = {str(u.id) for u in document_users}
        entities.sort(key=lambda e: (e['id'] not in document_entity_ids, e['name']))
    
    # Limit results
    entities = entities[:limit]
    
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
    Get entities associated with a specific document
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
    
    # Get document creator
    creator_query = select(User).where(User.id == document.created_by)
    result = await db.execute(creator_query)
    creator = result.scalar_one_or_none()
    
    if creator:
        entities.append({
            "id": str(creator.id),
            "name": creator.full_name or creator.email,
            "email": creator.email,
            "type": "user",
            "role": "Document Creator"
        })
    
    # Get users who have viewed the document
    view_query = select(User).join(DocumentView).where(
        DocumentView.document_id == UUID(document_id)
    ).distinct().limit(10)
    
    result = await db.execute(view_query)
    viewers = result.scalars().all()
    
    for viewer in viewers:
        if str(viewer.id) != str(creator.id) if creator else True:
            entities.append({
                "id": str(viewer.id),
                "name": viewer.full_name or viewer.email,
                "email": viewer.email,
                "type": "user",
                "role": "Viewer"
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
    Get recently interacted entities for quick selection
    """
    entities = []
    
    # Get users from recent document views
    recent_users_query = select(User).join(DocumentView).where(
        User.tenant_id == UUID(tenant_id)
    ).order_by(DocumentView.viewed_at.desc()).distinct().limit(limit)
    
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
    
    return EntitySearchResponse(
        entities=entities,
        total=len(entities)
    )
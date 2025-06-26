"""
API endpoints for Signature Contacts management
"""
import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import selectinload

from app.api.async_dependencies import get_async_db, get_current_active_user_async
from app.db.models import User, SignatureContact
from app.schemas.signature_contact import (
    SignatureContactCreate, SignatureContactUpdate, SignatureContact as SignatureContactSchema,
    SignatureContactList
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=SignatureContactSchema)
async def create_signature_contact(
    contact_data: SignatureContactCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Create a new signature contact"""
    
    try:
        # Check if contact already exists
        stmt = select(SignatureContact).filter(
            and_(
                SignatureContact.tenant_id == current_user.tenant_id,
                SignatureContact.email == contact_data.email
            )
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contact with this email already exists"
            )
        
        # Create new contact
        contact = SignatureContact(
            tenant_id=current_user.tenant_id,
            created_by=current_user.id,
            name=contact_data.name,
            email=contact_data.email,
            phone=contact_data.phone,
            role=contact_data.role,
            company=contact_data.company,
            notes=contact_data.notes,
            is_favorite=contact_data.is_favorite,
            contact_metadata=contact_data.contact_metadata
        )
        
        db.add(contact)
        await db.commit()
        await db.refresh(contact)
        
        logger.info(f"Created signature contact {contact.id} for tenant {current_user.tenant_id}")
        return contact
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating signature contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating signature contact"
        )


@router.get("/", response_model=SignatureContactList)
async def get_signature_contacts(
    search: Optional[str] = Query(None, description="Search by name or email"),
    is_favorite: Optional[bool] = Query(None, description="Filter by favorite status"),
    sort_by: str = Query("usage_count", description="Sort by: name, email, usage_count, last_used_at"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Get signature contacts for the current tenant"""
    
    try:
        # Base query
        stmt = select(SignatureContact).filter(
            SignatureContact.tenant_id == current_user.tenant_id
        )
        
        # Apply filters
        if search:
            search_pattern = f"%{search.lower()}%"
            stmt = stmt.filter(
                or_(
                    func.lower(SignatureContact.name).like(search_pattern),
                    func.lower(SignatureContact.email).like(search_pattern),
                    func.lower(SignatureContact.company).like(search_pattern)
                )
            )
        
        if is_favorite is not None:
            stmt = stmt.filter(SignatureContact.is_favorite == is_favorite)
        
        # Apply sorting
        if sort_by == "name":
            order_col = SignatureContact.name
        elif sort_by == "email":
            order_col = SignatureContact.email
        elif sort_by == "last_used_at":
            order_col = SignatureContact.last_used_at
        else:  # default to usage_count
            order_col = SignatureContact.usage_count
        
        if sort_order == "asc":
            stmt = stmt.order_by(order_col.asc())
        else:
            stmt = stmt.order_by(order_col.desc())
        
        # Get total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await db.execute(count_stmt)
        total = count_result.scalar()
        
        # Get favorites count
        favorites_stmt = select(func.count()).select_from(SignatureContact).filter(
            and_(
                SignatureContact.tenant_id == current_user.tenant_id,
                SignatureContact.is_favorite == True
            )
        )
        favorites_result = await db.execute(favorites_stmt)
        favorites_count = favorites_result.scalar()
        
        # Apply pagination
        stmt = stmt.offset(offset).limit(limit)
        
        # Execute query
        result = await db.execute(stmt)
        contacts = result.scalars().all()
        
        return SignatureContactList(
            contacts=contacts,
            total=total,
            favorites_count=favorites_count
        )
        
    except Exception as e:
        logger.error(f"Error getting signature contacts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving signature contacts"
        )


@router.get("/frequently-used", response_model=List[SignatureContactSchema])
async def get_frequently_used_contacts(
    limit: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Get frequently used signature contacts"""
    
    try:
        stmt = select(SignatureContact).filter(
            and_(
                SignatureContact.tenant_id == current_user.tenant_id,
                SignatureContact.usage_count > 0
            )
        ).order_by(
            desc(SignatureContact.usage_count),
            desc(SignatureContact.last_used_at)
        ).limit(limit)
        
        result = await db.execute(stmt)
        contacts = result.scalars().all()
        
        return contacts
        
    except Exception as e:
        logger.error(f"Error getting frequently used contacts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving frequently used contacts"
        )


@router.get("/favorites", response_model=List[SignatureContactSchema])
async def get_favorite_contacts(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Get favorite signature contacts"""
    
    try:
        stmt = select(SignatureContact).filter(
            and_(
                SignatureContact.tenant_id == current_user.tenant_id,
                SignatureContact.is_favorite == True
            )
        ).order_by(SignatureContact.name)
        
        result = await db.execute(stmt)
        contacts = result.scalars().all()
        
        return contacts
        
    except Exception as e:
        logger.error(f"Error getting favorite contacts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving favorite contacts"
        )


@router.get("/{contact_id}", response_model=SignatureContactSchema)
async def get_signature_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Get a specific signature contact"""
    
    try:
        stmt = select(SignatureContact).filter(
            and_(
                SignatureContact.id == contact_id,
                SignatureContact.tenant_id == current_user.tenant_id
            )
        )
        result = await db.execute(stmt)
        contact = result.scalar_one_or_none()
        
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found"
            )
        
        return contact
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting signature contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving signature contact"
        )


@router.put("/{contact_id}", response_model=SignatureContactSchema)
async def update_signature_contact(
    contact_id: UUID,
    contact_data: SignatureContactUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Update a signature contact"""
    
    try:
        stmt = select(SignatureContact).filter(
            and_(
                SignatureContact.id == contact_id,
                SignatureContact.tenant_id == current_user.tenant_id
            )
        )
        result = await db.execute(stmt)
        contact = result.scalar_one_or_none()
        
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found"
            )
        
        # Update fields
        update_data = contact_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(contact, field, value)
        
        await db.commit()
        await db.refresh(contact)
        
        logger.info(f"Updated signature contact {contact.id}")
        return contact
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating signature contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating signature contact"
        )


@router.post("/{contact_id}/toggle-favorite", response_model=SignatureContactSchema)
async def toggle_favorite_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Toggle favorite status of a signature contact"""
    
    try:
        stmt = select(SignatureContact).filter(
            and_(
                SignatureContact.id == contact_id,
                SignatureContact.tenant_id == current_user.tenant_id
            )
        )
        result = await db.execute(stmt)
        contact = result.scalar_one_or_none()
        
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found"
            )
        
        # Toggle favorite status
        contact.is_favorite = not contact.is_favorite
        
        await db.commit()
        await db.refresh(contact)
        
        logger.info(f"Toggled favorite status for contact {contact.id}")
        return contact
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error toggling favorite status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error toggling favorite status"
        )


@router.delete("/{contact_id}")
async def delete_signature_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Delete a signature contact"""
    
    try:
        stmt = select(SignatureContact).filter(
            and_(
                SignatureContact.id == contact_id,
                SignatureContact.tenant_id == current_user.tenant_id
            )
        )
        result = await db.execute(stmt)
        contact = result.scalar_one_or_none()
        
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found"
            )
        
        await db.delete(contact)
        await db.commit()
        
        logger.info(f"Deleted signature contact {contact_id}")
        return {"message": "Contact deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting signature contact: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting signature contact"
        )


@router.post("/import", response_model=List[SignatureContactSchema])
async def import_signature_contacts(
    contacts: List[SignatureContactCreate],
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Import multiple signature contacts"""
    
    try:
        created_contacts = []
        
        for contact_data in contacts:
            # Check if contact already exists
            stmt = select(SignatureContact).filter(
                and_(
                    SignatureContact.tenant_id == current_user.tenant_id,
                    SignatureContact.email == contact_data.email
                )
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if not existing:
                # Create new contact
                contact = SignatureContact(
                    tenant_id=current_user.tenant_id,
                    created_by=current_user.id,
                    name=contact_data.name,
                    email=contact_data.email,
                    phone=contact_data.phone,
                    role=contact_data.role,
                    company=contact_data.company,
                    notes=contact_data.notes,
                    is_favorite=contact_data.is_favorite,
                    contact_metadata=contact_data.contact_metadata
                )
                db.add(contact)
                created_contacts.append(contact)
        
        await db.commit()
        
        # Refresh all created contacts
        for contact in created_contacts:
            await db.refresh(contact)
        
        logger.info(f"Imported {len(created_contacts)} signature contacts for tenant {current_user.tenant_id}")
        return created_contacts
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error importing signature contacts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error importing signature contacts"
        )


@router.get("/recent-signers", response_model=List[dict])
async def get_recent_signers(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Get recent signers from signature requests that are not yet contacts"""
    
    try:
        from app.db.models import SignatureRequest, SignatureRequestSigner
        
        # Get recent signers from signature requests
        stmt = select(
            SignatureRequestSigner.name,
            SignatureRequestSigner.email,
            SignatureRequestSigner.phone,
            func.max(SignatureRequest.created_at).label('last_used')
        ).join(
            SignatureRequest,
            SignatureRequestSigner.request_id == SignatureRequest.id
        ).filter(
            SignatureRequest.tenant_id == current_user.tenant_id
        ).group_by(
            SignatureRequestSigner.email,
            SignatureRequestSigner.name,
            SignatureRequestSigner.phone
        ).order_by(
            desc('last_used')
        ).limit(limit * 2)  # Get more to filter out existing contacts
        
        result = await db.execute(stmt)
        recent_signers = result.all()
        
        # Get existing contact emails
        contact_stmt = select(SignatureContact.email).filter(
            SignatureContact.tenant_id == current_user.tenant_id
        )
        contact_result = await db.execute(contact_stmt)
        existing_emails = {row[0] for row in contact_result.all()}
        
        # Filter out existing contacts and format response
        new_signers = []
        for signer in recent_signers:
            if signer.email not in existing_emails:
                new_signers.append({
                    "name": signer.name,
                    "email": signer.email,
                    "phone": signer.phone,
                    "last_used": signer.last_used.isoformat() if signer.last_used else None,
                    "is_existing_contact": False
                })
                
                if len(new_signers) >= limit:
                    break
        
        return new_signers
        
    except Exception as e:
        logger.error(f"Error getting recent signers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving recent signers"
        )


@router.post("/import-from-recent", response_model=List[SignatureContactSchema])
async def import_contacts_from_recent_signers(
    emails: List[str],
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async)
):
    """Import specific recent signers as contacts"""
    
    try:
        from app.db.models import SignatureRequest, SignatureRequestSigner
        
        created_contacts = []
        
        # Get signer details for the specified emails
        stmt = select(
            SignatureRequestSigner.name,
            SignatureRequestSigner.email,
            SignatureRequestSigner.phone
        ).join(
            SignatureRequest,
            SignatureRequestSigner.request_id == SignatureRequest.id
        ).filter(
            and_(
                SignatureRequest.tenant_id == current_user.tenant_id,
                SignatureRequestSigner.email.in_(emails)
            )
        ).distinct()
        
        result = await db.execute(stmt)
        signers = result.all()
        
        # Create contacts for each signer
        for signer in signers:
            # Check if contact already exists
            existing_stmt = select(SignatureContact).filter(
                and_(
                    SignatureContact.tenant_id == current_user.tenant_id,
                    SignatureContact.email == signer.email
                )
            )
            existing_result = await db.execute(existing_stmt)
            existing = existing_result.scalar_one_or_none()
            
            if not existing:
                contact = SignatureContact(
                    tenant_id=current_user.tenant_id,
                    created_by=current_user.id,
                    name=signer.name,
                    email=signer.email,
                    phone=signer.phone,
                    usage_count=1,
                    last_used_at=datetime.now(timezone.utc)
                )
                db.add(contact)
                created_contacts.append(contact)
        
        await db.commit()
        
        # Refresh all created contacts
        for contact in created_contacts:
            await db.refresh(contact)
        
        logger.info(f"Imported {len(created_contacts)} contacts from recent signers for tenant {current_user.tenant_id}")
        return created_contacts
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error importing contacts from recent signers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error importing contacts from recent signers"
        )
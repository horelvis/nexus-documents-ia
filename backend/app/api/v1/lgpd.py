"""
LGPD (Lei Geral de Proteção de Dados) API Endpoints
Complete user data deletion for LGPD compliance
"""
from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, Optional
import logging

from app.api.async_dependencies import get_current_user_async, get_async_db
from app.core.auth.base import UserProfile
from app.core.auth.superuser import require_superuser
from app.services.lgpd_deletion_service import lgpd_deletion_service
from app.db.models import LGPDDeletionAudit
from app.schemas.user import UserResponse
from pydantic import BaseModel, Field, EmailStr

logger = logging.getLogger(__name__)

router = APIRouter(tags=["LGPD Compliance"])


class LGPDDeletionRequest(BaseModel):
    """Request model for LGPD user deletion"""
    confirmation_email: EmailStr = Field(..., description="User email for confirmation")
    confirmation_text: str = Field(..., min_length=5, description="User must type confirmation text")
    reason: Optional[str] = Field(None, max_length=500, description="Optional reason for deletion")

    class Config:
        json_schema_extra = {
            "example": {
                "confirmation_email": "user@example.com",
                "confirmation_text": "DELETE",
                "reason": "No longer using the service",
            }
        }


class LGPDDataSummaryResponse(BaseModel):
    """Response model for user data summary"""
    user_id: str
    email: str
    full_name: Optional[str]
    created_at: str
    data_summary: Dict[str, Any]
    lgpd_rights: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "12345678-1234-1234-1234-123456789012",
                "email": "user@example.com",
                "full_name": "João Silva",
                "tenant": "Empresa ABC",
                "created_at": "2024-01-01T00:00:00",
                "data_summary": {
                    "profile_data": {
                        "user_record": 1,
                        "user_image": 1,
                        "external_accounts": {
                            "clerk": True,
                            "stripe": True
                        }
                    },
                    "document_data": {
                        "documents_created": 15,
                        "document_views": 45
                    }
                },
                "lgpd_rights": {
                    "article_18": "Right to data deletion",
                    "deletion_scope": "Complete personal data removal"
                }
            }
        }


class LGPDDeletionResponse(BaseModel):
    """Response model for LGPD deletion result"""
    user_id: str
    deletion_id: str
    status: str
    deleted_at: str
    summary: Dict[str, Any]
    lgpd_compliance: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "12345678-1234-1234-1234-123456789012",
                "deletion_id": "87654321-4321-4321-4321-210987654321",
                "status": "completed",
                "deleted_at": "2024-01-01T12:00:00",
                "summary": {
                    "deleted_records": {
                        "documents": 15,
                        "profile_data": 3,
                        "user": 1
                    },
                    "anonymized_records": 8
                },
                "lgpd_compliance": {
                    "article": "LGPD Article 18 - Right to Data Deletion",
                    "method": "complete_data_destruction"
                }
            }
        }


@router.get("/data-summary", response_model=LGPDDataSummaryResponse)
async def get_user_data_summary(
    current_user: UserProfile = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get comprehensive summary of user data for LGPD transparency

    Shows what personal data will be deleted when user requests deletion.
    Required by LGPD Article 9 (Right to Information).
    """
    try:
        logger.info(f"📊 LGPD Data Summary requested by user {current_user.sub}")

        summary = await lgpd_deletion_service.get_user_data_summary(
            db=db,
            user_id=current_user.sub
        )

        return LGPDDataSummaryResponse(**summary)

    except Exception as e:
        logger.error(f"❌ Failed to get LGPD data summary for user {current_user.sub}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve data summary"
        )


@router.post("/request-deletion", response_model=LGPDDeletionResponse)
async def request_user_deletion(
    deletion_request: LGPDDeletionRequest,
    current_user: UserProfile = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Request complete user data deletion for LGPD compliance

    Implements LGPD Article 18 (Right to Data Deletion).
    This action is IRREVERSIBLE and will delete ALL user data.

    Security Requirements:
    - User must confirm their email address
    - User must type explicit confirmation text
    - Process is logged for compliance audit
    """
    current_user_id = current_user.sub
    current_user_email = current_user.email
    try:
        logger.warning(f"🔥 LGPD DELETION REQUEST by user {current_user_id}")

        # Security validations
        if deletion_request.confirmation_email != current_user_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Confirmation email does not match your account email"
            )

        expected_confirmation = "DELETE"
        if deletion_request.confirmation_text != expected_confirmation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Confirmation text must be exactly: '{expected_confirmation}'"
            )

        # Execute LGPD deletion
        result = await lgpd_deletion_service.request_user_deletion(
            db=db,
            user_id=current_user_id,
            requested_by_user_id=current_user_id,
            confirmation_token=deletion_request.confirmation_text,
            reason=deletion_request.reason,
        )

        logger.warning(f"🔥 LGPD DELETION COMPLETED for user {current_user_id}")

        return LGPDDeletionResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ LGPD deletion failed for user {current_user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process deletion request"
        )


@router.post("/admin/delete-user", response_model=LGPDDeletionResponse)
async def admin_delete_user(
    user_id: str = Body(..., embed=True),
    reason: Optional[str] = Body(None, embed=True),
    current_user: UserProfile = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Admin endpoint to delete user for LGPD compliance

    Only available to admins.
    Used for cases where user cannot self-delete (e.g., deceased, incapacitated).
    """
    try:
        logger.warning(f"🔥 ADMIN LGPD DELETION - Admin {current_user.sub} deleting user {user_id}")

        result = await lgpd_deletion_service.request_user_deletion(
            db=db,
            user_id=user_id,
            requested_by_user_id=current_user.sub,
            confirmation_token="ADMIN_DELETION",
            reason=reason or "Admin deletion for LGPD compliance"
        )

        logger.warning(f"🔥 ADMIN LGPD DELETION COMPLETED - User {user_id} deleted by admin {current_user.sub}")

        return LGPDDeletionResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Admin LGPD deletion failed for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process admin deletion request"
        )


@router.get("/deletion-history")
async def get_deletion_history(
    current_user: UserProfile = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get LGPD deletion audit history

    Only available to admins. Shows deletion history for compliance reporting.
    """
    try:
        from sqlalchemy.future import select
        from sqlalchemy.orm import selectinload

        stmt = select(LGPDDeletionAudit).options(
            selectinload(LGPDDeletionAudit.requested_by_user),
        ).order_by(LGPDDeletionAudit.created_at.desc())

        result = await db.execute(stmt)
        deletions = result.scalars().all()

        return {
            "total_deletions": len(deletions),
            "deletions": [
                {
                    "deletion_id": str(deletion.id),
                    "user_id": str(deletion.user_id),
                    "user_email": deletion.user_email,
                    "requested_by": {
                        "id": str(deletion.requested_by_user.id),
                        "email": deletion.requested_by_user.email,
                        "full_name": deletion.requested_by_user.full_name
                    } if deletion.requested_by_user else None,
                    "status": deletion.status,
                    "started_at": deletion.started_at.isoformat(),
                    "completed_at": deletion.completed_at.isoformat() if deletion.completed_at else None,
                    "total_records_deleted": deletion.total_records_deleted,
                    "anonymized_records": deletion.anonymized_records,
                    "lgpd_article": deletion.lgpd_article,
                    "deletion_method": deletion.deletion_method,
                    "reason": deletion.reason
                }
                for deletion in deletions
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get deletion history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve deletion history"
        )


@router.get("/compliance-info")
async def get_lgpd_compliance_info():
    """
    Get information about LGPD compliance and user rights
    
    Public endpoint that explains user rights under LGPD.
    """
    return {
        "lgpd_compliance": {
            "law": "Lei Geral de Proteção de Dados (LGPD) - Lei nº 13.709/2018",
            "user_rights": {
                "article_18": {
                    "title": "Right to Data Deletion",
                    "description": "Users have the right to request complete deletion of their personal data",
                    "scope": "All personal data stored in the system will be permanently deleted",
                    "exceptions": "Audit records are anonymized rather than deleted for legal compliance"
                },
                "article_9": {
                    "title": "Right to Information", 
                    "description": "Users can request information about what personal data is stored",
                    "endpoint": "/api/v1/lgpd/data-summary"
                }
            },
            "deletion_process": {
                "step_1": "Request data summary to see what will be deleted",
                "step_2": "Submit deletion request with email and text confirmation",
                "step_3": "System performs complete data removal within 30 days",
                "step_4": "Audit record is created for compliance (anonymized)",
                "irreversible": True,
                "external_services": "Clerk and Stripe accounts are deleted automatically when API keys are configured; otherwise manual action is required"
            },
            "data_retention": {
                "audit_records": "Anonymized and retained for 5 years for legal compliance",
                "deleted_data": "Permanently destroyed and unrecoverable",
                "backups": "Removed from all backups within 90 days"
            }
        }
    }

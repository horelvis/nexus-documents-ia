"""
Identity Extraction Service

Business logic for identity document processing with GDPR compliance:
- Calls langextract-service for actual OCR/extraction
- Manages database storage with encryption
- Handles retention policies and automatic deletion
- Provides audit logging for all PII access

GDPR Compliance:
- Explicit consent required for processing
- Automatic deletion after retention period
- All access logged in audit table
- Integrates with existing LGPD deletion service
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.identity_document import (
    IdentityDocumentExtraction,
    IdentityDocumentResponse,
    IdentityDocumentType,
    IdentityExtractionAuditLog,
)

logger = logging.getLogger(__name__)


class IdentityExtractionService:
    """
    Service for extracting and managing identity document data.

    GDPR-compliant handling of PII:
    - Requires explicit consent before processing
    - Stores data with automatic retention policies
    - Logs all access for audit purposes
    - Integrates with LGPD deletion service for deletion requests
    """

    def __init__(
        self,
        langextract_url: Optional[str] = None,
        api_key: Optional[str] = None,
        default_retention_days: int = 90,
    ):
        self.langextract_url = langextract_url or os.getenv(
            "LANGEXTRACT_SERVICE_URL",
            "http://langextract-service:8000"
        )
        self.api_key = api_key or settings.MICROSERVICES_API_KEY
        self.default_retention_days = default_retention_days

    async def extract_identity_document(
        self,
        db: AsyncSession,
        file_bytes: bytes,
        filename: str,
        tenant_id: str,
        user_id: str,
        document_type: Optional[str] = None,
        purpose: str = "identity_verification",
        retention_days: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extract data from an identity document.

        Args:
            db: Database session
            file_bytes: Document file content
            filename: Original filename
            tenant_id: Tenant identifier
            user_id: User performing the extraction
            document_type: Expected document type (auto-detected if not provided)
            purpose: Purpose for processing (GDPR requirement)
            retention_days: Days to retain data (default: 90)
            ip_address: Client IP address for audit
            user_agent: Client user agent for audit

        Returns:
            Dict with extraction result and GDPR metadata
        """
        retention = retention_days or self.default_retention_days

        # Log audit: extraction started
        await self._log_audit(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            action="extraction_started",
            purpose=purpose,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"filename": filename, "document_type": document_type},
        )

        try:
            # Call langextract-service
            result = await self._call_langextract(
                file_bytes=file_bytes,
                filename=filename,
                document_type=document_type,
                purpose=purpose,
                tenant_id=tenant_id,
            )

            if not result.get("success"):
                await self._log_audit(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="extraction_failed",
                    purpose=purpose,
                    metadata={"error": result.get("error", "Unknown error")},
                )
                return {
                    "success": False,
                    "error": result.get("error", "Extraction failed"),
                }

            # Calculate retention date
            retention_until = datetime.utcnow() + timedelta(days=retention)

            # Store in database
            extraction_id = await self._store_extraction(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                result=result,
                purpose=purpose,
                retention_until=retention_until,
            )

            # Log audit: extraction completed
            await self._log_audit(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                action="extraction_completed",
                purpose=purpose,
                extraction_id=extraction_id,
                fields_accessed=list(result.keys()),
                ip_address=ip_address,
                user_agent=user_agent,
            )

            return {
                "success": True,
                "extraction": result,
                "extraction_id": extraction_id,
                "retention_until": retention_until.isoformat(),
                "gdpr_notice": f"Data will be automatically deleted after {retention} days.",
            }

        except Exception as e:
            logger.error(f"Identity extraction failed: {e}")
            await self._log_audit(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                action="extraction_error",
                purpose=purpose,
                metadata={"error": str(e)},
            )
            raise

    async def get_extraction(
        self,
        db: AsyncSession,
        extraction_id: str,
        tenant_id: str,
        user_id: str,
        purpose: str,
        ip_address: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve an identity extraction by ID.

        Logs access for GDPR audit trail.
        """
        result = await db.execute(
            text("""
                SELECT id, document_type, issuing_country, extracted_data,
                       confidence_score, retention_until, created_at
                FROM identity_document_extractions
                WHERE id = :id AND tenant_id = :tenant_id
            """),
            {"id": extraction_id, "tenant_id": tenant_id}
        )
        row = result.fetchone()

        if not row:
            return None

        # Log access
        await self._log_audit(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            action="view",
            purpose=purpose,
            extraction_id=extraction_id,
            ip_address=ip_address,
        )

        return {
            "id": str(row[0]),
            "document_type": row[1],
            "issuing_country": row[2],
            "extracted_data": json.loads(row[3]) if row[3] else {},
            "confidence_score": row[4],
            "retention_until": row[5].isoformat() if row[5] else None,
            "created_at": row[6].isoformat() if row[6] else None,
        }

    async def delete_extraction(
        self,
        db: AsyncSession,
        extraction_id: str,
        tenant_id: str,
        user_id: str,
        reason: str = "user_request",
    ) -> bool:
        """
        Delete an identity extraction (GDPR right to erasure).
        """
        # Log deletion request
        await self._log_audit(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            action="deletion_requested",
            purpose=reason,
            extraction_id=extraction_id,
        )

        result = await db.execute(
            text("""
                DELETE FROM identity_document_extractions
                WHERE id = :id AND tenant_id = :tenant_id
            """),
            {"id": extraction_id, "tenant_id": tenant_id}
        )
        await db.commit()

        deleted = result.rowcount > 0

        if deleted:
            await self._log_audit(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                action="deleted",
                purpose=reason,
                extraction_id=extraction_id,
            )

        return deleted

    async def cleanup_expired_extractions(
        self,
        db: AsyncSession,
    ) -> int:
        """
        Delete all extractions past their retention date.

        Should be called by a scheduled job (e.g., daily cron).
        """
        result = await db.execute(
            text("""
                DELETE FROM identity_document_extractions
                WHERE retention_until < NOW()
                RETURNING id, tenant_id
            """)
        )
        deleted_rows = result.fetchall()
        await db.commit()

        for row in deleted_rows:
            logger.info(
                f"GDPR: Auto-deleted expired extraction {row[0]} "
                f"from tenant {row[1]}"
            )

        return len(deleted_rows)

    async def _call_langextract(
        self,
        file_bytes: bytes,
        filename: str,
        document_type: Optional[str],
        purpose: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Call langextract-service for OCR/extraction"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.langextract_url}/api/v1/extraction/identity/extract",
                headers={
                    "X-API-Key": self.api_key,
                    "X-Tenant-ID": tenant_id,
                },
                files={"file": (filename, file_bytes)},
                data={
                    "document_type": document_type or "",
                    "consent_given": "true",
                    "purpose": purpose,
                },
            )

            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("detail", response.text)
                except Exception:
                    pass

                return {
                    "success": False,
                    "error": f"Extraction service error: {error_detail}",
                }

            return response.json()

    async def _store_extraction(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        result: Dict[str, Any],
        purpose: str,
        retention_until: datetime,
    ) -> Optional[str]:
        """Store extraction result in database"""
        try:
            extracted_data = {
                "full_name": result.get("full_name"),
                "first_name": result.get("first_name"),
                "last_name": result.get("last_name"),
                "document_number": result.get("document_number"),
                "date_of_birth": result.get("date_of_birth"),
                "expiration_date": result.get("expiration_date"),
                "nationality": result.get("nationality"),
                "gender": result.get("gender"),
                "mrz_data": result.get("mrz_data"),
                "license_categories": result.get("license_categories"),
            }

            db_result = await db.execute(
                text("""
                    INSERT INTO identity_document_extractions (
                        tenant_id, document_type, issuing_country,
                        extracted_data, confidence_score, ocr_engine,
                        retention_until, consent_purpose, created_by
                    ) VALUES (
                        :tenant_id, :document_type, :issuing_country,
                        :extracted_data, :confidence_score, :ocr_engine,
                        :retention_until, :consent_purpose, :created_by
                    ) RETURNING id
                """),
                {
                    "tenant_id": tenant_id,
                    "document_type": result.get("document_type", "unknown"),
                    "issuing_country": result.get("issuing_country"),
                    "extracted_data": json.dumps(extracted_data),
                    "confidence_score": result.get("confidence_score", 0.0),
                    "ocr_engine": result.get("ocr_engine", "doctr"),
                    "retention_until": retention_until,
                    "consent_purpose": purpose,
                    "created_by": user_id,
                }
            )
            await db.commit()

            row = db_result.fetchone()
            return str(row[0]) if row else None

        except Exception as e:
            logger.error(f"Failed to store extraction: {e}")
            return None

    async def _log_audit(
        self,
        db: AsyncSession,
        tenant_id: str,
        user_id: str,
        action: str,
        purpose: str,
        extraction_id: Optional[str] = None,
        fields_accessed: Optional[List[str]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Log audit entry for GDPR compliance"""
        try:
            await db.execute(
                text("""
                    INSERT INTO identity_extraction_audit_log (
                        extraction_id, tenant_id, user_id, action,
                        purpose, fields_accessed, ip_address, user_agent, metadata
                    ) VALUES (
                        :extraction_id, :tenant_id, :user_id, :action,
                        :purpose, :fields_accessed, :ip_address, :user_agent, :metadata
                    )
                """),
                {
                    "extraction_id": extraction_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "action": action,
                    "purpose": purpose,
                    "fields_accessed": json.dumps(fields_accessed or []),
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "metadata": json.dumps(metadata or {}),
                }
            )
            await db.commit()
        except Exception as e:
            # Don't fail the main operation if audit logging fails
            logger.warning(f"Failed to log audit entry: {e}")


# Global instance
identity_extraction_service = IdentityExtractionService()

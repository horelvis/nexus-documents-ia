"""
Edit Session Service - Manages temporary Google Docs editing sessions
"""
import asyncio
import base64
import binascii
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete

from app.models.edit_session import EditSession
from app.services.google_docs_service import google_docs_service, ODT_MIME_TYPE
from app.core.config import settings

logger = logging.getLogger(__name__)
DEFAULT_TEMPLATE_MIME = ODT_MIME_TYPE


class EditSessionService:
    """
    Service for managing edit sessions following Alfresco ECM pattern
    """
    
    def __init__(self):
        self._cleanup_task = None
    
    async def create_edit_session(
        self,
        db: AsyncSession,
        template_id: str,
        template_name: str,
        template_file_base64: Optional[str],
        template_content: Optional[str],
        template_file_name: Optional[str],
        template_file_mime: Optional[str],
        user_id: str,
        user_email: str,
        tenant_id: str
    ) -> EditSession:
        """
        Create new editing session with temporary Google Doc
        """
        try:
            logger.info(f"🔄 Creating edit session for template {template_id} by user {user_id}")
            
            # 1. Check if user already has active session for this template
            existing_session = await self._get_active_session_for_user(
                db, template_id, user_id
            )
            
            if existing_session:
                logger.warning(f"⚠️ User {user_id} already has active session for template {template_id}")
                
                # Check if the Google Doc still exists
                doc_exists = await google_docs_service.check_document_exists(existing_session.google_doc_id)
                
                if doc_exists:
                    # Document exists, extend existing session
                    existing_session.extend_session(hours=1)
                    await db.commit()
                    logger.info(f"✅ Extended existing session for valid document: {existing_session.google_doc_id}")
                    return existing_session
                else:
                    # Document doesn't exist, clean up old session and create new one
                    logger.warning(f"🗑️ Document {existing_session.google_doc_id} no longer exists, cleaning up old session")
                    await db.delete(existing_session)
                    await db.commit()
            
            # Determine whether we are using an ODT payload or HTML content
            template_file_bytes: Optional[bytes] = None
            html_content: Optional[str] = None
            if template_file_base64:
                template_file_bytes = self._decode_template_payload(template_file_base64)
            else:
                html_content = template_content or "<p></p>"
            
            file_name = template_file_name
            file_mime = template_file_mime
            if template_file_bytes:
                file_name = file_name or f"{template_name}.odt"
                file_mime = file_mime or DEFAULT_TEMPLATE_MIME
            else:
                file_name = file_name or f"{template_name}.html"
                file_mime = file_mime or "text/html"
            
            # 2. Create temporary Google Doc from provided payload
            doc_info = await google_docs_service.create_temporary_document(
                title=template_name,
                content=html_content,
                user_email=user_email,
                template_id=template_id,
                file_bytes=template_file_bytes,
                file_mime_type=file_mime,
                original_filename=file_name
            )
            doc_original_name = doc_info.get('original_file_name') or file_name
            doc_mime = doc_info.get('file_mime_type') or file_mime
            payload_size = template_file_bytes or (html_content.encode('utf-8') if html_content else b"")
            doc_size = doc_info.get('file_size') or len(payload_size)
            
            # 3. Create edit session record
            edit_session = EditSession(
                template_id=template_id,
                template_name=template_name,
                template_file_name=doc_original_name,
                template_file_mime=doc_mime,
                user_id=user_id,
                user_email=user_email,
                tenant_id=tenant_id,
                google_doc_id=doc_info['document_id'],
                google_doc_url=doc_info['view_url'],
                google_doc_edit_url=doc_info['edit_url'],
                original_content_hash=doc_info['content_hash'],
                content_size_bytes=doc_size,
                status="active"
            )
            
            db.add(edit_session)
            await db.commit()
            await db.refresh(edit_session)
            
            logger.info(f"✅ Edit session created: {edit_session.id}")
            
            return edit_session
            
        except Exception as e:
            logger.error(f"❌ Failed to create edit session: {e}")
            await db.rollback()
            raise
    
    async def _get_active_session_for_user(
        self,
        db: AsyncSession,
        template_id: str,
        user_id: str
    ) -> Optional[EditSession]:
        """Get active session for user and template"""
        try:
            stmt = select(EditSession).where(
                EditSession.template_id == template_id,
                EditSession.user_id == user_id,
                EditSession.status == "active"
            )
            result = await db.execute(stmt)
            session = result.scalar_one_or_none()
            
            if session and session.is_expired:
                # Session exists but expired, mark it as expired
                await self._mark_session_expired(db, session)
                return None
            
            return session
            
        except Exception as e:
            logger.error(f"❌ Failed to get active session: {e}")
            return None
    
    async def get_edit_session(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str = None
    ) -> Optional[EditSession]:
        """Get edit session by ID"""
        try:
            stmt = select(EditSession).where(EditSession.id == session_id)
            
            if user_id:
                stmt = stmt.where(EditSession.user_id == user_id)
            
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"❌ Failed to get edit session {session_id}: {e}")
            return None
    
    async def finish_edit_session(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str,
        force_sync: bool = False
    ) -> Dict[str, Any]:
        """
        Finish editing session - sync changes and cleanup
        Following Alfresco pattern: sync back, delete temp doc
        """
        try:
            logger.info(f"🔄 Finishing edit session {session_id}")
            
            # 1. Get session
            session = await self.get_edit_session(db, session_id, user_id)
            if not session:
                raise ValueError("Edit session not found")
            
            if session.status != "active":
                raise ValueError(f"Session is not active (status: {session.status})")
            
            # 2. Get updated ODT payload from Google Doc
            updated_file_bytes, new_content_hash = await google_docs_service.export_document(
                session.google_doc_id
            )
            
            # 3. Check if changes were made
            changes_detected = new_content_hash != session.original_content_hash
            should_sync = changes_detected or force_sync
            
            # 4. Update template in main system (if changes detected)
            sync_result = None
            if should_sync:
                sync_result = await self._sync_changes_to_template(
                    session.template_id,
                    updated_file_bytes,
                    session.tenant_id,
                    user_id
                )
            
            # 5. Delete temporary Google Doc
            deletion_success = await google_docs_service.delete_document(session.google_doc_id)
            
            # 6. Mark session as completed
            session.mark_completed(
                content_hash=new_content_hash,
                changes_detected=changes_detected
            )
            session.cleanup_completed = deletion_success
            
            await db.commit()

            updated_file_payload = None
            if should_sync and updated_file_bytes:
                file_name = session.template_file_name or f"{session.template_name}.odt"
                mime_type = session.template_file_mime or DEFAULT_TEMPLATE_MIME
                updated_file_payload = {
                    "base64": base64.b64encode(updated_file_bytes).decode("utf-8"),
                    "mime_type": mime_type,
                    "file_name": file_name,
                    "content_hash": new_content_hash,
                    "size": len(updated_file_bytes)
                }
            
            result = {
                "session_id": str(session.id),
                "status": "completed",
                "changes_detected": changes_detected,
                "sync_result": sync_result,
                "cleanup_success": deletion_success,
                "completed_at": session.completed_at.isoformat(),
                "updated_file": updated_file_payload
            }
            
            logger.info(f"✅ Edit session completed: {session_id}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to finish edit session {session_id}: {e}")
            await db.rollback()
            raise
    
    async def _sync_changes_to_template(
        self,
        template_id: str,
        updated_file_bytes: bytes,
        tenant_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Sync changes back to main template system"""
        try:
            logger.info(f"🔄 Syncing changes to template {template_id}")
            
            # Here you would call the main API to update the template
            # For now, return mock result
            sync_result = {
                "template_id": template_id,
                "updated_at": datetime.utcnow().isoformat(),
                "updated_by": user_id,
                "content_size": len(updated_file_bytes),
                "success": True
            }
            
            logger.info(f"✅ Template synchronized: {template_id}")
            return sync_result
            
        except Exception as e:
            logger.error(f"❌ Failed to sync template {template_id}: {e}")
            return {
                "template_id": template_id,
                "success": False,
                "error": str(e)
            }
    
    async def extend_session(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str,
        hours: int = 1
    ) -> EditSession:
        """Extend session expiration time"""
        try:
            session = await self.get_edit_session(db, session_id, user_id)
            if not session:
                raise ValueError("Edit session not found")
            
            if session.status != "active":
                raise ValueError("Cannot extend inactive session")
            
            session.extend_session(hours=hours)
            await db.commit()
            
            logger.info(f"⏰ Extended session {session_id} by {hours} hours")
            return session
            
        except Exception as e:
            logger.error(f"❌ Failed to extend session {session_id}: {e}")
            await db.rollback()
            raise
    
    async def cancel_edit_session(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Cancel editing session and cleanup"""
        try:
            logger.info(f"❌ Cancelling edit session {session_id}")
            
            session = await self.get_edit_session(db, session_id, user_id)
            if not session:
                raise ValueError("Edit session not found")
            
            # Delete Google Doc
            deletion_success = await google_docs_service.delete_document(session.google_doc_id)
            
            # Update session status
            session.status = "cancelled"
            session.completed_at = datetime.utcnow()
            session.cleanup_completed = deletion_success
            
            await db.commit()
            
            logger.info(f"✅ Edit session cancelled: {session_id}")
            
            return {
                "session_id": str(session.id),
                "status": "cancelled",
                "cleanup_success": deletion_success
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to cancel session {session_id}: {e}")
            await db.rollback()
            raise
    
    async def cleanup_expired_sessions(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Cleanup expired sessions and their Google Docs
        Runs periodically as background task
        """
        try:
            logger.info("🧹 Starting cleanup of expired edit sessions")
            
            # Find expired sessions
            current_time = datetime.utcnow()
            stmt = select(EditSession).where(
                EditSession.status == "active",
                EditSession.expires_at <= current_time
            )
            result = await db.execute(stmt)
            expired_sessions = result.scalars().all()
            
            cleanup_stats = {
                "expired_sessions_found": len(expired_sessions),
                "successfully_cleaned": 0,
                "cleanup_errors": 0,
                "google_docs_deleted": 0
            }
            
            for session in expired_sessions:
                try:
                    logger.info(f"🧹 Cleaning up expired session: {session.id}")
                    
                    # Delete Google Doc
                    deletion_success = await google_docs_service.delete_document(
                        session.google_doc_id
                    )
                    
                    if deletion_success:
                        cleanup_stats["google_docs_deleted"] += 1
                    
                    # Mark session as expired
                    await self._mark_session_expired(db, session)
                    session.cleanup_completed = deletion_success
                    
                    cleanup_stats["successfully_cleaned"] += 1
                    
                except Exception as e:
                    logger.error(f"❌ Failed to cleanup session {session.id}: {e}")
                    cleanup_stats["cleanup_errors"] += 1
                    
                    # Mark cleanup error
                    session.cleanup_error = str(e)
                    session.status = "cleanup_error"
            
            await db.commit()
            
            logger.info(f"✅ Cleanup completed: {cleanup_stats}")
            return cleanup_stats
            
        except Exception as e:
            logger.error(f"❌ Failed to cleanup expired sessions: {e}")
            await db.rollback()
            raise
    
    async def _mark_session_expired(self, db: AsyncSession, session: EditSession):
        """Mark session as expired"""
        session.mark_expired()
        # Note: db.commit() should be called by the caller
    
    def _decode_template_payload(self, payload: str) -> bytes:
        """Decode Base64 ODT payload coming from core API."""
        try:
            data = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid template file payload") from exc
        
        if not data:
            raise ValueError("Template file payload is empty")
        return data
    
    async def get_user_sessions(
        self,
        db: AsyncSession,
        user_id: str,
        tenant_id: str,
        include_completed: bool = False
    ) -> List[EditSession]:
        """Get all sessions for a user"""
        try:
            stmt = select(EditSession).where(
                EditSession.user_id == user_id,
                EditSession.tenant_id == tenant_id
            )
            
            if not include_completed:
                stmt = stmt.where(EditSession.status == "active")
            
            stmt = stmt.order_by(EditSession.created_at.desc())
            
            result = await db.execute(stmt)
            return result.scalars().all()
            
        except Exception as e:
            logger.error(f"❌ Failed to get user sessions for {user_id}: {e}")
            return []
    
    def start_cleanup_task(self):
        """Start background cleanup task"""
        if self._cleanup_task is None:
            logger.info("🚀 Starting cleanup background task")
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    def stop_cleanup_task(self):
        """Stop background cleanup task"""
        if self._cleanup_task:
            logger.info("🛑 Stopping cleanup background task")
            self._cleanup_task.cancel()
            self._cleanup_task = None
    
    async def _cleanup_loop(self):
        """Background cleanup loop"""
        try:
            while True:
                await asyncio.sleep(settings.cleanup_interval_minutes * 60)  # Convert to seconds
                
                try:
                    # This would need proper database session management in real implementation
                    # For now, it's just a placeholder
                    logger.info("⏰ Running scheduled cleanup...")
                    
                except Exception as e:
                    logger.error(f"❌ Cleanup loop error: {e}")
                    
        except asyncio.CancelledError:
            logger.info("🛑 Cleanup loop cancelled")
        except Exception as e:
            logger.error(f"❌ Cleanup loop failed: {e}")


# Global service instance
edit_session_service = EditSessionService()

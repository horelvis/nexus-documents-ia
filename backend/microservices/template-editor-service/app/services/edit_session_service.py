"""
Edit Session Service - Manages temporary Google Docs editing sessions via the core API.
"""
import asyncio
import base64
import binascii
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from app.services.google_docs_service import google_docs_service, ODT_MIME_TYPE
from app.services.core_google_token_client import google_token_client, GoogleTokenNotConnectedError
from app.services.core_session_client import core_session_client, SessionNotFoundError

logger = logging.getLogger(__name__)
DEFAULT_TEMPLATE_MIME = ODT_MIME_TYPE


class EditSessionService:
    """
    Service for managing edit sessions following Alfresco ECM pattern.
    Persists state using the core API instead of a local database.
    """

    def __init__(self):
        self._cleanup_task = None

    async def create_edit_session(
        self,
        template_id: str,
        template_name: str,
        template_file_base64: Optional[str],
        template_content: Optional[str],
        template_file_name: Optional[str],
        template_file_mime: Optional[str],
        user_id: str,
        user_email: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        logger.info("🔄 Creating edit session for template %s", template_id)

        try:
            user_token = await google_token_client.get_access_token(user_id)
        except GoogleTokenNotConnectedError as exc:
            raise ValueError("User must connect Google Drive before editing templates") from exc

        existing_session = await core_session_client.get_active_session(
            template_id, user_id
        )
        if existing_session:
            logger.info("⚠️ Existing session found for template %s", template_id)
            doc_exists = await google_docs_service.check_document_exists(
                existing_session["google_doc_id"], user_token=user_token
            )
            if doc_exists:
                await core_session_client.extend_session(existing_session["id"], user_id)
                return existing_session
            await core_session_client.cancel_session(
                existing_session["id"], user_id, reason="Google Doc no longer exists"
            )

        template_file_bytes: Optional[bytes] = None
        html_content: Optional[str] = None
        if template_file_base64:
            template_file_bytes = self._decode_template_payload(template_file_base64)
        elif template_content:
            html_content = template_content

        file_name = template_file_name
        file_mime = template_file_mime
        if template_file_bytes:
            file_name = file_name or f"{template_name}.odt"
            file_mime = file_mime or DEFAULT_TEMPLATE_MIME
        elif html_content:
            file_name = file_name or f"{template_name}.html"
            file_mime = file_mime or "text/html"
        else:
            file_name = file_name or f"{template_name}.odt"
            file_mime = file_mime or DEFAULT_TEMPLATE_MIME

        try:
            user_token = await google_token_client.get_access_token(user_id)
        except GoogleTokenNotConnectedError as exc:
            raise ValueError("User needs to connect Google Drive before editing templates") from exc

        doc_info = await google_docs_service.create_temporary_document(
            title=template_name,
            content=html_content,
            user_email=user_email,
            template_id=template_id,
            file_bytes=template_file_bytes,
            file_mime_type=file_mime,
            original_filename=file_name,
            user_token=user_token,
        )

        payload_size = template_file_bytes or (html_content.encode("utf-8") if html_content else b"")
        create_payload = {
            "template_id": template_id,
            "template_name": template_name,
            "template_file_name": doc_info.get("original_file_name") or file_name,
            "template_file_mime": doc_info.get("file_mime_type") or file_mime,
            "user_id": user_id,
            "user_email": user_email,
            "tenant_id": tenant_id,
            "google_doc_id": doc_info["document_id"],
            "google_doc_url": doc_info["view_url"],
            "google_doc_edit_url": doc_info["edit_url"],
            "original_content_hash": doc_info["content_hash"],
            "content_size_bytes": doc_info.get("file_size") or len(payload_size),
        }
        session = await core_session_client.create_session(create_payload)
        logger.info("✅ Edit session created %s", session["id"])
        return session

    async def get_edit_session(self, session_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            return await core_session_client.get_session(session_id, user_id=user_id)
        except SessionNotFoundError as exc:
            raise ValueError("Edit session not found") from exc

    async def finish_edit_session(
        self,
        session_id: str,
        user_id: str,
        force_sync: bool = False,
    ) -> Dict[str, Any]:
        session = await self.get_edit_session(session_id, user_id=user_id)
        doc_id = session["google_doc_id"]
        logger.info("🔚 Finishing edit session %s", session_id)

        try:
            user_token = await google_token_client.get_access_token(user_id)
        except GoogleTokenNotConnectedError as exc:
            raise ValueError("Cannot finish edit session without Google Drive connection") from exc

        updated_file_bytes, new_hash = await google_docs_service.export_document(
            doc_id, user_token=user_token
        )
        changes_detected = new_hash != session.get("original_content_hash") or force_sync
        cleanup_success = await google_docs_service.delete_document(doc_id, user_token=user_token)

        await core_session_client.complete_session(
            session_id,
            user_id,
            changes_detected=changes_detected,
            final_content_hash=new_hash,
            content_size_bytes=len(updated_file_bytes),
            cleanup_completed=cleanup_success,
        )

        updated_file_payload = None
        if updated_file_bytes:
            mime_type = session.get("template_file_mime") or DEFAULT_TEMPLATE_MIME
            file_name = session.get("template_file_name") or f"{session['template_name']}.odt"
            updated_file_payload = {
                "base64": base64.b64encode(updated_file_bytes).decode("utf-8"),
                "mime_type": mime_type,
                "file_name": file_name,
                "content_hash": new_hash,
                "size": len(updated_file_bytes),
            }

        return {
            "session_id": session_id,
            "status": "completed" if cleanup_success else "cleanup_pending",
            "changes_detected": changes_detected,
            "cleanup_success": cleanup_success,
            "completed_at": datetime.utcnow().isoformat(),
            "updated_file": updated_file_payload,
        }

    async def extend_session(self, session_id: str, user_id: str, hours: int = 1) -> Dict[str, Any]:
        try:
            return await core_session_client.extend_session(session_id, user_id, hours)
        except SessionNotFoundError as exc:
            raise ValueError("Edit session not found") from exc

    async def cancel_edit_session(self, session_id: str, user_id: str) -> Dict[str, Any]:
        try:
            session = await core_session_client.get_session(session_id, user_id=user_id)
            if not session:
                raise ValueError("Edit session not found")

            try:
                user_token = await google_token_client.get_access_token(user_id)
            except GoogleTokenNotConnectedError:
                user_token = None

            if session.get("google_doc_id"):
                await google_docs_service.delete_document(session["google_doc_id"], user_token=user_token)

            return await core_session_client.cancel_session(
                session_id, user_id, reason="Cancelled by user"
            )
        except SessionNotFoundError as exc:
            raise ValueError("Edit session not found") from exc

    async def get_user_sessions(
        self,
        user_id: str,
        tenant_id: str,
        include_completed: bool = False,
    ) -> Dict[str, Any]:
        return await core_session_client.list_sessions(
            user_id=user_id,
            tenant_id=tenant_id,
            include_completed=include_completed,
        )

    def start_cleanup_task(self):
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    def stop_cleanup_task(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    async def _cleanup_loop(self):
        while True:
            try:
                await asyncio.sleep(60 * 30)
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("❌ Cleanup loop error: %s", exc)

    async def _cleanup_expired_sessions(self):
        sessions = await core_session_client.list_sessions(
            include_completed=False,
            include_expired=True,
        )
        now = datetime.utcnow()
        total = 0
        cleaned = 0
        errors = 0
        for session in sessions.get("sessions", []):
            expires_at = datetime.fromisoformat(session["expires_at"])
            if expires_at <= now and session["status"] == "active":
                total += 1
                logger.info("🧹 Cleaning expired session %s", session["id"])
                try:
                    user_token = None
                    try:
                        user_token = await google_token_client.get_access_token(session["user_id"])
                    except GoogleTokenNotConnectedError:
                        pass

                    await google_docs_service.delete_document(
                        session["google_doc_id"],
                        user_token=user_token
                    )
                    await core_session_client.cancel_session(
                        session["id"],
                        session["user_id"],
                        reason="Expired cleanup",
                    )
                    cleaned += 1
                except Exception as exc:  # pylint: disable=broad-except
                    errors += 1
                    logger.error("❌ Failed to cleanup session %s: %s", session["id"], exc)
        return {"total": total, "success": cleaned, "errors": errors, "expired": total}

    @staticmethod
    def _decode_template_payload(payload: str) -> bytes:
        try:
            data = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid template file payload") from exc
        if not data:
            raise ValueError("Template file payload is empty")
        return data


edit_session_service = EditSessionService()

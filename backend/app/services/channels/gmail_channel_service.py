"""
Gmail Channel Service for syncing emails to RAG.

Handles:
- Listing emails from specified labels
- Extracting email body and metadata
- Processing email attachments
- Coordinating with Weaviate for indexing
"""
from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InformationChannel, ChannelDocument
from app.services.channels.channel_service import ChannelService
from app.services.channels.channel_credential_service import ChannelCredentialService
from app.core.config import settings

logger = logging.getLogger(__name__)

# Supported attachment types for extraction
SUPPORTED_ATTACHMENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "text/plain": "txt",
}


class GmailChannelService:
    """
    Service for syncing Gmail emails to the RAG pipeline.

    Uses Gmail API to:
    - List emails from specified labels (INBOX, etc.)
    - Extract email body (prefer plain text, fallback to HTML)
    - Process supported attachments (PDF, DOCX, etc.)
    - Index combined content in Weaviate
    """

    def __init__(
        self,
        db: AsyncSession,
        channel_service: ChannelService,
        credential_service: ChannelCredentialService,
    ):
        self.db = db
        self.channel_service = channel_service
        self.credential_service = credential_service

    async def sync_channel(
        self,
        channel: InformationChannel,
        full_sync: bool = False,
    ) -> Dict[str, Any]:
        """
        Sync a Gmail channel.

        Args:
            channel: The channel to sync
            full_sync: If True, re-sync all emails regardless of changes

        Returns:
            Dict with sync statistics
        """
        stats = {
            "items_found": 0,
            "items_new": 0,
            "items_updated": 0,
            "items_deleted": 0,
            "items_failed": 0,
            "errors": [],
        }

        try:
            # Get credentials
            credentials = await self.credential_service.get_oauth_credentials(channel.id)
            if not credentials:
                raise ValueError("No valid credentials for channel")

            # Build Gmail service
            service = build("gmail", "v1", credentials=credentials)

            # Get configuration
            config = channel.configuration or {}
            # Handle empty labels array - default to INBOX if not specified or empty
            labels = config.get("labels") or ["INBOX"]
            if not labels:
                labels = ["INBOX"]
                logger.warning(f"Channel {channel.id} has empty labels, defaulting to INBOX")
            max_age_days = config.get("max_age_days", 90)
            include_attachments = config.get("include_attachments", True)
            attachment_types = config.get("attachment_types", list(SUPPORTED_ATTACHMENT_TYPES.values()))
            max_emails = config.get("max_emails_per_sync", 100)

            # Calculate date filter
            after_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)
            after_query = after_date.strftime("%Y/%m/%d")

            # List emails
            messages = await self._list_messages(
                service=service,
                labels=labels,
                after_date=after_query,
                max_results=max_emails,
            )
            stats["items_found"] = len(messages)

            # Process each email
            for msg_stub in messages:
                try:
                    result = await self._process_message(
                        service=service,
                        channel=channel,
                        message_id=msg_stub["id"],
                        include_attachments=include_attachments,
                        attachment_types=attachment_types,
                        full_sync=full_sync,
                    )
                    if result == "new":
                        stats["items_new"] += 1
                    elif result == "updated":
                        stats["items_updated"] += 1
                except Exception as e:
                    stats["items_failed"] += 1
                    stats["errors"].append({
                        "message_id": msg_stub["id"],
                        "error": str(e),
                    })
                    logger.exception(f"Error processing message {msg_stub['id']}: {e}")

        except Exception as e:
            logger.exception(f"Error syncing Gmail channel {channel.id}: {e}")
            raise

        return stats

    async def _list_messages(
        self,
        service: Any,
        labels: List[str],
        after_date: str,
        max_results: int,
    ) -> List[Dict[str, str]]:
        """
        List messages from Gmail with specified filters.

        Args:
            service: Gmail API service
            labels: Label IDs to filter (e.g., ["INBOX"])
            after_date: Only messages after this date (YYYY/MM/DD)
            max_results: Maximum messages to return

        Returns:
            List of message stubs with 'id' and 'threadId'
        """
        messages = []
        query = f"after:{after_date}"

        page_token = None
        while len(messages) < max_results:
            remaining = max_results - len(messages)
            page_size = min(remaining, 100)

            response = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    labelIds=labels,
                    q=query,
                    maxResults=page_size,
                    pageToken=page_token,
                )
                .execute()
            )

            batch = response.get("messages", [])
            messages.extend(batch)

            page_token = response.get("nextPageToken")
            if not page_token or not batch:
                break

        return messages[:max_results]

    async def _process_message(
        self,
        service: Any,
        channel: InformationChannel,
        message_id: str,
        include_attachments: bool,
        attachment_types: List[str],
        full_sync: bool,
    ) -> Optional[str]:
        """
        Process a single Gmail message.

        Args:
            service: Gmail API service
            channel: The channel being synced
            message_id: Gmail message ID
            include_attachments: Whether to process attachments
            attachment_types: Allowed attachment types
            full_sync: Force reprocessing

        Returns:
            "new", "updated", or None if skipped
        """
        # Get full message
        message = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        # Extract headers
        headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "(No Subject)")
        # Try multiple headers for sender (from, reply-to, sender)
        from_addr = headers.get("from") or headers.get("reply-to") or headers.get("sender") or ""
        to_addr = headers.get("to", "")
        date_str = headers.get("date", "")

        # Parse date
        email_date = None
        if date_str:
            try:
                email_date = parsedate_to_datetime(date_str)
            except Exception:
                pass

        # Calculate content hash based on internal date (unique per message)
        internal_date = message.get("internalDate", "")
        hash_input = f"{message_id}:{internal_date}"
        content_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        # Check if document exists
        doc, is_new = await self.channel_service.upsert_document(
            channel_id=channel.id,
            external_id=message_id,
            content_hash=content_hash,
            title=subject,
            external_url=f"https://mail.google.com/mail/u/0/#inbox/{message_id}",
            source_metadata={
                "from": from_addr,
                "to": to_addr,
                "thread_id": message.get("threadId"),
                "labels": message.get("labelIds", []),
            },
            source_created_at=email_date,
        )

        # Skip if unchanged
        if not is_new and doc.status == "indexed" and not full_sync:
            logger.debug(f"Skipping unchanged email: {subject}")
            return None

        try:
            # Extract email body
            body_text = self._extract_body(message.get("payload", {}))

            # Extract attachments if enabled
            attachment_texts = []
            if include_attachments:
                attachment_texts = await self._process_attachments(
                    service=service,
                    message_id=message_id,
                    payload=message.get("payload", {}),
                    attachment_types=attachment_types,
                )

            # Combine content
            full_content = self._build_email_content(
                subject=subject,
                from_addr=from_addr,
                to_addr=to_addr,
                date=email_date,
                body=body_text,
                attachments=attachment_texts,
            )

            if not full_content.strip():
                logger.warning(f"📧 No content extracted from email: {subject}")
                await self.channel_service.mark_document_failed(doc.id, "Empty content")
                return None

            # Log content size for debugging
            logger.info(
                f"📧 Email content ready for indexing: subject='{subject[:50]}...', "
                f"body={len(body_text)} chars, attachments={len(attachment_texts)}, "
                f"total={len(full_content)} chars"
            )

            # Index in Weaviate
            weaviate_id = await self._index_in_weaviate(
                channel=channel,
                document=doc,
                content=full_content,
                subject=subject,
                from_addr=from_addr,
            )

            if weaviate_id:
                await self.channel_service.mark_document_indexed(doc.id, weaviate_id)
                return "new" if is_new else "updated"
            else:
                await self.channel_service.mark_document_failed(doc.id, "Weaviate indexing failed")
                return None

        except Exception as e:
            await self.channel_service.mark_document_failed(doc.id, str(e))
            raise

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """
        Extract email body from payload.

        Strategy:
        1. Collect ALL text/plain and text/html parts from the message
        2. For multipart/alternative, prefer HTML (usually more complete)
        3. For multipart/mixed, concatenate all text parts
        4. Convert HTML to readable text preserving structure

        Args:
            payload: Message payload from Gmail API

        Returns:
            Email body text
        """
        import re
        from html import unescape

        plain_parts: List[str] = []
        html_parts: List[str] = []

        def process_part(part: Dict[str, Any], parent_type: str = "") -> None:
            """Recursively process MIME parts."""
            mime_type = part.get("mimeType", "")
            body = part.get("body", {})

            # Extract data from this part
            if body.get("data"):
                try:
                    decoded = base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="ignore")
                    if mime_type == "text/plain":
                        plain_parts.append(decoded)
                        logger.debug(f"📧 Extracted text/plain part: {len(decoded)} chars")
                    elif mime_type == "text/html":
                        html_parts.append(decoded)
                        logger.debug(f"📧 Extracted text/html part: {len(decoded)} chars")
                except Exception as e:
                    logger.warning(f"Error decoding email part: {e}")

            # Process nested parts (multipart messages)
            for subpart in part.get("parts", []):
                process_part(subpart, parent_type=mime_type)

        process_part(payload)

        logger.info(f"📧 Email extraction: {len(plain_parts)} plain parts, {len(html_parts)} HTML parts")

        def html_to_text(html: str) -> str:
            """Convert HTML to readable text preserving structure."""
            # Decode HTML entities
            text = unescape(html)

            # Remove style and script blocks
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)

            # Convert block elements to newlines for structure
            text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
            text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
            text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
            text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
            text = re.sub(r"</tr>", "\n", text, flags=re.IGNORECASE)
            text = re.sub(r"</h[1-6]>", "\n\n", text, flags=re.IGNORECASE)

            # Remove remaining HTML tags
            text = re.sub(r"<[^>]+>", " ", text)

            # Clean up whitespace while preserving paragraph breaks
            text = re.sub(r"[ \t]+", " ", text)  # Collapse horizontal whitespace
            text = re.sub(r"\n[ \t]+", "\n", text)  # Remove leading whitespace on lines
            text = re.sub(r"[ \t]+\n", "\n", text)  # Remove trailing whitespace on lines
            text = re.sub(r"\n{3,}", "\n\n", text)  # Max 2 consecutive newlines

            return text.strip()

        # Strategy: HTML usually contains more complete content
        # Gmail's text/plain is often auto-generated and truncated
        if html_parts:
            # Combine all HTML parts and convert
            combined_html = "\n".join(html_parts)
            result = html_to_text(combined_html)
            logger.info(f"📧 Using HTML content: {len(result)} chars final")
            return result

        # Fallback to plain text if no HTML
        if plain_parts:
            result = "\n".join(plain_parts)
            logger.info(f"📧 Using plain text content: {len(result)} chars final")
            return result

        logger.warning("📧 No email body content found")
        return ""

    async def _process_attachments(
        self,
        service: Any,
        message_id: str,
        payload: Dict[str, Any],
        attachment_types: List[str],
    ) -> List[Dict[str, str]]:
        """
        Process supported attachments from an email.

        Args:
            service: Gmail API service
            message_id: Gmail message ID
            payload: Message payload
            attachment_types: Allowed attachment types

        Returns:
            List of dicts with 'filename' and 'text'
        """
        results = []

        def find_attachments(part: Dict[str, Any]) -> List[Dict[str, Any]]:
            """Find all attachments in payload parts."""
            attachments = []
            body = part.get("body", {})

            if body.get("attachmentId"):
                attachments.append({
                    "part_id": part.get("partId"),
                    "attachment_id": body["attachmentId"],
                    "filename": part.get("filename", ""),
                    "mime_type": part.get("mimeType", ""),
                    "size": body.get("size", 0),
                })

            for subpart in part.get("parts", []):
                attachments.extend(find_attachments(subpart))

            return attachments

        attachments = find_attachments(payload)

        for att in attachments:
            mime_type = att["mime_type"]
            filename = att["filename"]

            # Check if supported type
            file_ext = SUPPORTED_ATTACHMENT_TYPES.get(mime_type)
            if not file_ext or file_ext not in attachment_types:
                continue

            try:
                # Download attachment
                attachment = (
                    service.users()
                    .messages()
                    .attachments()
                    .get(userId="me", messageId=message_id, id=att["attachment_id"])
                    .execute()
                )

                data = attachment.get("data", "")
                if not data:
                    continue

                file_content = base64.urlsafe_b64decode(data)

                # Extract text
                text = await self._extract_attachment_text(
                    file_content=file_content,
                    filename=filename,
                    mime_type=mime_type,
                )

                if text:
                    results.append({
                        "filename": filename,
                        "text": text,
                    })

            except Exception as e:
                logger.warning(f"Error processing attachment {filename}: {e}")

        return results

    async def _extract_attachment_text(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str,
    ) -> Optional[str]:
        """
        Extract text from attachment using intelligence-docs-service.

        Args:
            file_content: Attachment bytes
            filename: Attachment filename
            mime_type: Attachment MIME type

        Returns:
            Extracted text, or None if failed
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://intelligence-docs-service:8000/extract",
                    files={"file": (filename, file_content, mime_type)},
                    timeout=60.0,
                )
                response.raise_for_status()
                result = response.json()
                return result.get("text", "")

        except Exception as e:
            logger.exception(f"Error extracting text from attachment {filename}: {e}")
            return None

    def _build_email_content(
        self,
        subject: str,
        from_addr: str,
        to_addr: str,
        date: Optional[datetime],
        body: str,
        attachments: List[Dict[str, str]],
    ) -> str:
        """
        Build combined content from email parts.

        Args:
            subject: Email subject
            from_addr: From address
            to_addr: To address
            date: Email date
            body: Email body text
            attachments: List of attachment texts

        Returns:
            Combined content string
        """
        parts = []

        # Email header
        parts.append(f"Subject: {subject}")
        parts.append(f"From: {from_addr}")
        parts.append(f"To: {to_addr}")
        if date:
            parts.append(f"Date: {date.isoformat()}")
        parts.append("")

        # Body
        if body:
            parts.append("--- Email Body ---")
            parts.append(body)
            parts.append("")

        # Attachments
        for att in attachments:
            parts.append(f"--- Attachment: {att['filename']} ---")
            parts.append(att["text"])
            parts.append("")

        return "\n".join(parts)

    async def _index_in_weaviate(
        self,
        channel: InformationChannel,
        document: ChannelDocument,
        content: str,
        subject: str,
        from_addr: str,
    ) -> Optional[str]:
        """
        Index email in Weaviate with channel access control properties.

        Args:
            channel: The channel
            document: ChannelDocument record
            content: Combined email content
            subject: Email subject
            from_addr: Sender address

        Returns:
            Weaviate object UUID, or None if failed
        """
        try:
            # Build collection name using channel-specific format: nexus_{tenant_id}_channel_{channel_id}
            # This allows separate collections per information channel (Gmail, Drive, etc.)
            # Must match get_channel_collection_name() in weaviate-service/app/core/security.py
            tenant_normalized = str(channel.tenant_id).lower().replace("-", "_")
            channel_normalized = str(channel.id).lower().replace("-", "_")
            collection_name = f"nexus_{tenant_normalized}_channel_{channel_normalized}"
            weaviate_url = f"{settings.WEAVIATE_SERVICE_URL}/weaviate/collections/{collection_name}/documents"

            # Service-to-service auth uses X-API-Key
            headers = {}
            if hasattr(settings, "MICROSERVICES_API_KEY") and settings.MICROSERVICES_API_KEY:
                headers["X-API-Key"] = settings.MICROSERVICES_API_KEY

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    weaviate_url,
                    headers=headers,
                    json={
                        "title": subject,
                        "content": content,
                        "tenant_id": str(channel.tenant_id),
                        "document_type": "email",
                        "metadata": {
                            "external_id": document.external_id,
                            "external_url": document.external_url,
                            "channel_name": channel.name,
                            "from": from_addr,
                            **(document.source_metadata or {}),
                        },
                        "tags": ["gmail", "email", f"channel:{channel.id}"],
                        # Channel access control properties
                        "channel_id": str(channel.id),
                        "channel_visibility": channel.visibility,
                        "owner_user_id": str(channel.created_by),
                        "source_type": "gmail",
                        "external_id": document.external_id,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()
                return result.get("id")

        except Exception as e:
            logger.exception(f"Error indexing email in Weaviate: {e}")
            return None

    async def get_available_labels(self, channel_id: UUID) -> List[Dict[str, str]]:
        """
        Get available Gmail labels for configuration.

        Args:
            channel_id: Channel UUID

        Returns:
            List of labels with 'id' and 'name'
        """
        try:
            credentials = await self.credential_service.get_oauth_credentials(channel_id)
            if not credentials:
                return []

            service = build("gmail", "v1", credentials=credentials)
            response = service.users().labels().list(userId="me").execute()

            return [
                {"id": label["id"], "name": label["name"]}
                for label in response.get("labels", [])
                if label.get("type") in ["user", "system"]
            ]

        except Exception as e:
            logger.exception(f"Error getting Gmail labels: {e}")
            return []

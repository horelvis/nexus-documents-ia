"""
Google Docs Service - Temporary document creation and management
Following Alfresco ECM pattern: create temp, edit, sync, delete
"""
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import logging

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings

logger = logging.getLogger(__name__)


class GoogleDocsService:
    """
    Google Docs integration service for temporary document editing
    """
    
    def __init__(self):
        self._docs_service = None
        self._drive_service = None
        self._credentials = None
        self._initialize_services()
    
    def _initialize_services(self):
        """Initialize Google API services"""
        try:
            # Load service account credentials (always try now that we have real ones)
            if True:  # Always try to load credentials now
                # Load service account credentials with domain-wide delegation
                self._credentials = service_account.Credentials.from_service_account_file(
                    settings.google_credentials_path,
                    scopes=[
                        'https://www.googleapis.com/auth/documents',
                        'https://www.googleapis.com/auth/drive',
                        'https://www.googleapis.com/auth/drive.file',
                    ]
                )
                
                # Build API services (will be recreated per-user)
                self._docs_service = build('docs', 'v1', credentials=self._credentials)
                self._drive_service = build('drive', 'v3', credentials=self._credentials)
                
                logger.info("✅ Google API services initialized successfully")
            else:
                # Mock services for development
                self._credentials = None
                self._docs_service = None
                self._drive_service = None
                logger.info("⚠️ Running in DEBUG mode - Google API services mocked")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google API services: {e}")
            # In debug mode, continue without Google services
            if settings.debug:
                logger.warning("🔄 Continuing without Google API services in DEBUG mode")
                self._credentials = None
                self._docs_service = None
                self._drive_service = None
            else:
                raise
    
    async def _share_document_with_user(self, doc_id: str, user_email: str):
        """Share document with user as editor"""
        try:
            # Give editor access to the user
            permission = {
                'type': 'user',
                'role': 'writer',  # Editor access
                'emailAddress': user_email
            }
            
            self._drive_service.permissions().create(
                fileId=doc_id,
                body=permission,
                sendNotificationEmail=False  # Don't spam user with notification
            ).execute()
            
            logger.info(f"🔐 Shared document {doc_id} with user: {user_email}")
            
        except Exception as e:
            logger.error(f"❌ Failed to share document with user {user_email}: {e}")
            # Continue - not critical, user might still be able to access via other means
    
    async def _transfer_document_ownership(self, doc_id: str, user_email: str):
        """Transfer document ownership to the editing user if enabled."""
        if not settings.google_transfer_ownership or not self._drive_service:
            return
        
        try:
            permission = {
                'type': 'user',
                'role': 'owner',
                'emailAddress': user_email
            }
            self._drive_service.permissions().create(
                fileId=doc_id,
                body=permission,
                transferOwnership=True,
                sendNotificationEmail=False
            ).execute()
            logger.info(f"👑 Ownership of document {doc_id} transferred to {user_email}")
        except HttpError as e:
            logger.warning(f"⚠️ Unable to transfer ownership of {doc_id} to {user_email}: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Unexpected error transferring ownership of {doc_id}: {e}")
    
    async def create_temporary_document(
        self,
        title: str,
        content: str,
        user_email: str,
        template_id: str
    ) -> Dict[str, Any]:
        """
        Create temporary Google Doc for editing
        
        Args:
            title: Document title
            content: Initial HTML content
            user_email: User who will edit the document
            template_id: Original template ID for tracking
            
        Returns:
            Dictionary with document info and URLs
        """
        try:
            logger.info(f"🔄 Creating temporary Google Doc for template {template_id}")
            
            # Mock response in debug mode or when APIs not available
            if settings.debug or not self._docs_service:
                logger.info("🔧 Creating MOCK Google Doc for development")
                mock_doc_id = f"mock_doc_{template_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                result = {
                    'document_id': mock_doc_id,
                    'title': f"MOCK_EDIT_{title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    'view_url': f"https://docs.google.com/document/d/{mock_doc_id}/view",
                    'edit_url': f"https://docs.google.com/document/d/{mock_doc_id}/edit",
                    'content_hash': self._calculate_content_hash(content),
                    'created_at': datetime.utcnow().isoformat(),
                    'user_email': user_email,
                    'mock': True
                }
                logger.info(f"✅ Mock document created successfully: {mock_doc_id}")
                return result
            
            # 1. Create empty Google Doc with service account
            doc_title = f"TEMP_EDIT_{title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"📄 Creating Google Doc with service account: {doc_title}")
            
            # Create via Drive API with service account
            file_metadata = {
                'name': doc_title,
                'mimeType': 'application/vnd.google-apps.document'
            }
            
            doc = self._drive_service.files().create(body=file_metadata).execute()
            doc_id = doc.get('id')
            
            logger.info(f"📄 Created Google Doc: {doc_id}")
            
            # 2. Insert initial content if provided
            if content:
                await self._insert_html_content(doc_id, content)
            
            # 3. Share document with user as editor
            await self._share_document_with_user(doc_id, user_email)
            
            # 3b. Attempt to transfer ownership so the doc lives in the user's Drive
            await self._transfer_document_ownership(doc_id, user_email)
            
            # 4. Get document URLs
            doc_urls = self._get_document_urls(doc_id)
            
            # 5. Calculate content hash for change detection
            content_hash = self._calculate_content_hash(content)
            
            result = {
                'document_id': doc_id,
                'title': doc_title,
                'view_url': doc_urls['view_url'],
                'edit_url': doc_urls['edit_url'],
                'content_hash': content_hash,
                'created_at': datetime.utcnow().isoformat(),
                'user_email': user_email
            }
            
            logger.info(f"✅ Temporary document created successfully: {doc_id}")
            return result
            
        except HttpError as e:
            # Handle different types of errors
            if e.resp.status == 403:
                if "storage quota" in str(e).lower() or "storageQuotaExceeded" in str(e):
                    logger.warning(f"⚠️ Google Drive storage quota exceeded. Falling back to mock document.")
                    logger.warning("💡 The Compute Engine service account has limited Drive storage.")
                    logger.warning("💡 Consider creating a dedicated service account for Google Docs.")
                    fallback_reason = 'Service account storage quota exceeded'
                else:
                    logger.warning(f"⚠️ Google API permission denied (403). Falling back to mock document.")
                    logger.warning("💡 To use real Google Docs, enable these APIs in Google Cloud Console:")
                    logger.warning("   1. Google Docs API (docs.googleapis.com)")
                    logger.warning("   2. Google Drive API (drive.googleapis.com)")
                    fallback_reason = 'Google APIs permission denied'
                
                # Create mock document as fallback
                mock_doc_id = f"fallback_doc_{template_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                result = {
                    'document_id': mock_doc_id,
                    'title': f"FALLBACK_EDIT_{title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    'view_url': f"https://docs.google.com/document/d/{mock_doc_id}/view",
                    'edit_url': f"https://docs.google.com/document/d/{mock_doc_id}/edit",
                    'content_hash': self._calculate_content_hash(content),
                    'created_at': datetime.utcnow().isoformat(),
                    'user_email': user_email,
                    'mock': True,
                    'fallback_reason': fallback_reason
                }
                logger.info(f"✅ Fallback document created: {mock_doc_id}")
                return result
            else:
                error_msg = f"Google API error: {e}"
                logger.error(f"❌ {error_msg}")
                raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Failed to create temporary document: {e}"
            logger.error(f"❌ {error_msg}")
            raise
    
    async def _insert_html_content(self, doc_id: str, html_content: str, docs_service=None):
        """Insert HTML content into Google Doc"""
        try:
            # Use provided docs_service or default
            service = docs_service or self._docs_service
            
            # Convert HTML to Google Docs format (simplified)
            # In production, you'd want more sophisticated HTML parsing
            plain_text = self._html_to_plain_text(html_content)
            
            requests = [{
                'insertText': {
                    'location': {
                        'index': 1,  # Insert after title
                    },
                    'text': plain_text
                }
            }]
            
            service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()
            
            logger.info(f"📝 Inserted content into document {doc_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to insert content: {e}")
            # Don't raise - document creation can continue without initial content
    
    def _html_to_plain_text(self, html_content: str) -> str:
        """Convert HTML to plain text (simplified)"""
        import re
        
        # Remove HTML tags (basic implementation)
        text = re.sub('<[^<]+?>', '', html_content)
        
        # Decode HTML entities
        import html
        text = html.unescape(text)
        
        return text.strip()
    
    
    
    def _get_document_urls(self, doc_id: str) -> Dict[str, str]:
        """Get view and edit URLs for the document"""
        base_url = f"https://docs.google.com/document/d/{doc_id}"
        return {
            'view_url': f"{base_url}/view",
            'edit_url': f"{base_url}/edit"
        }
    
    def _calculate_content_hash(self, content: str) -> str:
        """Calculate MD5 hash of content for change detection"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    async def get_document_content(self, doc_id: str) -> Tuple[str, str]:
        """
        Get document content and calculate hash
        
        Returns:
            Tuple of (content, content_hash)
        """
        try:
            # Get document
            document = self._docs_service.documents().get(documentId=doc_id).execute()
            
            # Extract text content
            content = self._extract_text_from_doc(document)
            content_hash = self._calculate_content_hash(content)
            
            return content, content_hash
            
        except HttpError as e:
            logger.error(f"❌ Failed to get document content: {e}")
            raise Exception(f"Google API error: {e}")
        except Exception as e:
            logger.error(f"❌ Failed to get document content: {e}")
            raise
    
    def _extract_text_from_doc(self, document: Dict[str, Any]) -> str:
        """Extract plain text from Google Docs document structure"""
        try:
            content = document.get('body', {}).get('content', [])
            text_parts = []
            
            for element in content:
                if 'paragraph' in element:
                    paragraph = element['paragraph']
                    elements = paragraph.get('elements', [])
                    
                    for elem in elements:
                        if 'textRun' in elem:
                            text_content = elem['textRun'].get('content', '')
                            text_parts.append(text_content)
            
            return ''.join(text_parts)
            
        except Exception as e:
            logger.error(f"❌ Failed to extract text from document: {e}")
            return ""
    
    async def delete_document(self, doc_id: str) -> bool:
        """
        Delete temporary Google Doc
        
        Returns:
            True if successfully deleted, False otherwise
        """
        try:
            logger.info(f"🗑️ Deleting temporary document: {doc_id}")
            
            self._drive_service.files().delete(fileId=doc_id).execute()
            
            logger.info(f"✅ Successfully deleted document: {doc_id}")
            return True
            
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(f"⚠️ Document {doc_id} already deleted or not found")
                return True  # Consider it successfully "deleted"
            else:
                logger.error(f"❌ Failed to delete document {doc_id}: {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to delete document {doc_id}: {e}")
            return False
    
    async def check_document_exists(self, doc_id: str) -> bool:
        """Check if document still exists"""
        try:
            # For mock/fallback documents, always return False to force recreation
            if doc_id.startswith(('mock_doc_', 'fallback_doc_')):
                logger.info(f"📄 Mock/fallback document {doc_id} detected - forcing recreation")
                return False
            
            # For real documents, check via Google API
            if not self._drive_service:
                logger.warning("⚠️ No Google Drive service available - assuming document doesn't exist")
                return False
                
            self._drive_service.files().get(fileId=doc_id).execute()
            return True
        except HttpError as e:
            if e.resp.status == 404:
                return False
            elif e.resp.status == 403:
                # Permission denied - treat as non-existent to force fallback
                logger.warning(f"⚠️ Permission denied checking document {doc_id} - treating as non-existent")
                return False
            raise
        except Exception:
            return False


# Global service instance
google_docs_service = GoogleDocsService()

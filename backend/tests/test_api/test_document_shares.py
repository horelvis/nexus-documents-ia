"""
Tests for document sharing functionality
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy.orm import Session

from app.db.models import User, Document, DocumentShare, Tenant
from app.services.document_share_service import DocumentShareService
from app.core.security import get_password_hash, verify_password


class TestDocumentShareService:
    """Test document share service functionality"""
    
    @pytest.fixture
    def share_service(self, test_tenant: Tenant, test_user: User):
        """Create a document share service instance"""
        return DocumentShareService(
            tenant_id=str(test_tenant.id),
            user_id=str(test_user.id)
        )
    
    @pytest.fixture
    def test_document(self, db: Session, test_tenant: Tenant, test_user: User):
        """Create a test document"""
        document = Document(
            id=uuid4(),
            title="Test Document for Sharing",
            description="A test document",
            filename="test.pdf",
            file_path="documents/test.pdf",
            file_type="pdf",
            file_size=1024,
            mime_type="application/pdf",
            tenant_id=test_tenant.id,
            created_by=test_user.id
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document
    
    async def test_create_basic_share(
        self,
        db: Session,
        share_service: DocumentShareService,
        test_document: Document
    ):
        """Test creating a basic document share"""
        # Create share
        share = await share_service.create_share(
            db=db,
            document_id=test_document.id,
            share_type="view"
        )
        
        # Verify share was created
        assert share is not None
        assert share.document_id == test_document.id
        assert share.share_type == "view"
        assert share.is_active is True
        assert share.share_token is not None
        assert len(share.share_token) > 20  # Ensure token is sufficiently long
        assert share.share_url.endswith(share.share_token)
    
    async def test_create_share_with_expiration(
        self,
        db: Session,
        share_service: DocumentShareService,
        test_document: Document
    ):
        """Test creating a share with expiration date"""
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        share = await share_service.create_share(
            db=db,
            document_id=test_document.id,
            share_type="download",
            expires_at=expires_at
        )
        
        assert share.expires_at is not None
        assert share.expires_at == expires_at
        assert share.is_valid() is True
    
    async def test_create_password_protected_share(
        self,
        db: Session,
        share_service: DocumentShareService,
        test_document: Document
    ):
        """Test creating a password-protected share"""
        password = "SecurePassword123!"
        
        share = await share_service.create_share(
            db=db,
            document_id=test_document.id,
            share_type="view",
            password=password
        )
        
        # Verify password was hashed
        assert share.password_hash is not None
        assert share.password_hash != password
        
        # Verify password verification works
        db_share = db.query(DocumentShare).filter_by(id=share.id).first()
        assert verify_password(password, db_share.password_hash) is True
        assert verify_password("WrongPassword", db_share.password_hash) is False
    
    async def test_create_share_with_access_limit(
        self,
        db: Session,
        share_service: DocumentShareService,
        test_document: Document
    ):
        """Test creating a share with access count limit"""
        max_access = 5
        
        share = await share_service.create_share(
            db=db,
            document_id=test_document.id,
            share_type="view",
            max_access_count=max_access
        )
        
        assert share.max_access_count == max_access
        assert share.current_access_count == 0
        assert share.is_valid() is True
        
        # Simulate accessing the share
        db_share = db.query(DocumentShare).filter_by(id=share.id).first()
        for i in range(max_access):
            assert db_share.is_valid() is True
            db_share.increment_access_count()
            db.commit()
        
        # After max accesses, share should be invalid
        assert db_share.current_access_count == max_access
        assert db_share.is_valid() is False
    
    async def test_share_expiration_validation(
        self,
        db: Session,
        share_service: DocumentShareService,
        test_document: Document
    ):
        """Test share expiration validation"""
        # Create expired share
        expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        
        share = await share_service.create_share(
            db=db,
            document_id=test_document.id,
            expires_at=expires_at
        )
        
        db_share = db.query(DocumentShare).filter_by(id=share.id).first()
        assert db_share.is_valid() is False
    
    async def test_revoke_share(
        self,
        db: Session,
        share_service: DocumentShareService,
        test_document: Document,
        test_user: User
    ):
        """Test revoking a share"""
        # Create share
        share = await share_service.create_share(
            db=db,
            document_id=test_document.id
        )
        
        assert share.is_active is True
        
        # Revoke share
        success = await share_service.revoke_share(
            db=db,
            share_id=share.id,
            revoked_by=test_user.id
        )
        
        assert success is True
        
        # Verify share is revoked
        db_share = db.query(DocumentShare).filter_by(id=share.id).first()
        assert db_share.is_active is False
        assert db_share.revoked_at is not None
        assert db_share.revoked_by == test_user.id
        assert db_share.is_valid() is False
    
    async def test_list_shares_pagination(
        self,
        db: Session,
        share_service: DocumentShareService,
        test_document: Document
    ):
        """Test listing shares with pagination"""
        # Create multiple shares
        for i in range(15):
            await share_service.create_share(
                db=db,
                document_id=test_document.id,
                share_type="view" if i % 2 == 0 else "download"
            )
        
        # Test pagination
        shares_page1, total = await share_service.list_shares(
            db=db,
            page=1,
            per_page=10
        )
        
        assert len(shares_page1) == 10
        assert total == 15
        
        shares_page2, _ = await share_service.list_shares(
            db=db,
            page=2,
            per_page=10
        )
        
        assert len(shares_page2) == 5
    
    async def test_share_statistics(
        self,
        db: Session,
        share_service: DocumentShareService,
        test_document: Document
    ):
        """Test share statistics generation"""
        # Create various shares
        active_share = await share_service.create_share(
            db=db,
            document_id=test_document.id
        )
        
        expired_share = await share_service.create_share(
            db=db,
            document_id=test_document.id,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1)
        )
        
        revoked_share = await share_service.create_share(
            db=db,
            document_id=test_document.id
        )
        await share_service.revoke_share(
            db=db,
            share_id=revoked_share.id,
            revoked_by=test_document.created_by
        )
        
        # Get statistics
        stats = await share_service.get_statistics(db=db)
        
        assert stats.total_shares >= 3
        assert stats.active_shares >= 1
        assert stats.expired_shares >= 1
        assert stats.revoked_shares >= 1


class TestDocumentShareAPI:
    """Test document share API endpoints"""
    
    def test_create_share_endpoint(self, client, auth_headers, test_document_id):
        """Test creating a share via API"""
        response = client.post(
            "/api/v1/shares",
            json={
                "document_id": test_document_id,
                "share_type": "view",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "share_token" in data
        assert "share_url" in data
        assert data["share_type"] == "view"
    
    def test_access_shared_document_no_auth(self, client, test_share_token):
        """Test accessing a shared document without authentication"""
        response = client.get(f"/api/v1/shares/access/{test_share_token}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "document_info" in data
    
    def test_access_password_protected_share(self, client, test_password_share):
        """Test accessing a password-protected share"""
        # Try without password
        response = client.get(f"/api/v1/shares/access/{test_password_share['token']}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["requires_password"] is True
        
        # Try with correct password
        response = client.get(
            f"/api/v1/shares/access/{test_password_share['token']}",
            params={"password": test_password_share['password']}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
    
    def test_bulk_share_creation(self, client, auth_headers, test_document_id):
        """Test creating multiple shares for different recipients"""
        recipients = ["user1@example.com", "user2@example.com", "user3@example.com"]
        
        response = client.post(
            "/api/v1/shares/bulk",
            json={
                "document_id": test_document_id,
                "share_type": "view",
                "recipients": recipients
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_requested"] == 3
        assert data["total_successful"] == 3
        assert len(data["successful"]) == 3
# app/services/document_tracking_service.py

from app.db.models import Document, DocumentView
from sqlalchemy.orm import Session
import uuid

class DocumentTrackingService:
    def __init__(self, tenant_id, user_id=None):
        self.tenant_id = tenant_id
        self.user_id = user_id
    
    def record_document_view(self, db: Session, document_id, view_duration=None, is_complete=False):
        """Registra una vista de documento por un usuario"""
        if not self.user_id:
            return False
        
        try:
            # Registrar la vista en DocumentView
            document_view = DocumentView(
                user_id=uuid.UUID(self.user_id) if isinstance(self.user_id, str) else self.user_id,
                document_id=uuid.UUID(document_id) if isinstance(document_id, str) else document_id,
                tenant_id=uuid.UUID(self.tenant_id) if isinstance(self.tenant_id, str) else self.tenant_id,
                view_duration_seconds=view_duration,
                is_complete_view=is_complete
            )
            db.add(document_view)
            
            # Actualizar métricas del documento
            document = db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if document:
                document.increment_metric("view_count", db)
                db.commit()
                return True
            
            return False
        except Exception as e:
            db.rollback()
            print(f"Error al registrar vista de documento: {str(e)}")
            return False
    
    def record_document_download(self, db: Session, document_id):
        """Registra una descarga de documento"""
        try:
            document = db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if document:
                document.increment_metric("download_count", db)
                db.commit()
                return True
            
            return False
        except Exception as e:
            db.rollback()
            print(f"Error al registrar descarga de documento: {str(e)}")
            return False
    
    def record_document_share(self, db: Session, document_id):
        """Registra cuando un documento es compartido"""
        try:
            document = db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if document:
                document.increment_metric("share_count", db)
                db.commit()
                return True
            
            return False
        except Exception as e:
            db.rollback()
            print(f"Error al registrar compartición de documento: {str(e)}")
            return False
    
    def record_document_query(self, db: Session, document_id):
        """Registra cuando se hace una consulta sobre un documento"""
        try:
            document = db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if document:
                document.increment_metric("query_count", db)
                db.commit()
                return True
            
            return False
        except Exception as e:
            db.rollback()
            print(f"Error al registrar consulta de documento: {str(e)}")
            return False
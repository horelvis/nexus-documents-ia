# app/services/document_tracking_service.py

from app.db.database import SessionLocal
from sqlalchemy.sql import func
from app.db.models import Document, document_views, DocumentMetrics
from datetime import datetime
import uuid

class DocumentTrackingService:
    def __init__(self, tenant_id, user_id=None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.db = SessionLocal()
    
    def __del__(self):
        self.db.close()
    
    def record_document_view(self, document_id, view_duration=None, is_complete=False):
        """Registra una vista de documento por un usuario"""
        if not self.user_id:
            return False
        
        try:
            # Registrar la vista en document_views
            view_id = str(uuid.uuid4())
            self.db.execute(
                document_views.insert().values(
                    id=view_id,
                    user_id=self.user_id,
                    document_id=document_id,
                    tenant_id=self.tenant_id,
                    viewed_at=datetime.now(),
                    view_duration_seconds=view_duration,
                    is_complete_view=is_complete
                )
            )
            
            # Actualizar métricas del documento
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if document:
                document.increment_metric("view_count", self.db)
                self.db.commit()
                return True
            
            return False
        except Exception as e:
            self.db.rollback()
            print(f"Error al registrar vista de documento: {str(e)}")
            return False
    
    def record_document_download(self, document_id):
        """Registra una descarga de documento"""
        try:
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if document:
                document.increment_metric("download_count", self.db)
                self.db.commit()
                return True
            
            return False
        except Exception as e:
            self.db.rollback()
            print(f"Error al registrar descarga de documento: {str(e)}")
            return False
    
    def record_document_share(self, document_id):
        """Registra cuando un documento es compartido"""
        try:
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if document:
                document.increment_metric("share_count", self.db)
                self.db.commit()
                return True
            
            return False
        except Exception as e:
            self.db.rollback()
            print(f"Error al registrar compartición de documento: {str(e)}")
            return False
    
    def record_document_query(self, document_id):
        """Registra cuando se hace una consulta sobre un documento"""
        try:
            document = self.db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == self.tenant_id
            ).first()
            
            if document:
                document.increment_metric("query_count", self.db)
                self.db.commit()
                return True
            
            return False
        except Exception as e:
            self.db.rollback()
            print(f"Error al registrar consulta de documento: {str(e)}")
            return False
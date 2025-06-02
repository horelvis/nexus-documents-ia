# app/services/document_tracking_service.py

from app.db.database import SessionLocal
from app.db.models import Document, DocumentView, DocumentMetrics
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
            # Registrar la vista en DocumentView
            # CORRECCIÓN: Usar uuid.uuid4() directamente en lugar de str(uuid.uuid4())
            view_id = uuid.uuid4()  # Cambio: UUID en lugar de String
            self.db.execute(
                DocumentView.insert().values(
                    id=view_id,
                    user_id=uuid.UUID(self.user_id) if isinstance(self.user_id, str) else self.user_id,  # Asegurar UUID
                    document_id=uuid.UUID(document_id) if isinstance(document_id, str) else document_id,  # Asegurar UUID
                    tenant_id=uuid.UUID(self.tenant_id) if isinstance(self.tenant_id, str) else self.tenant_id,  # Asegurar UUID
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
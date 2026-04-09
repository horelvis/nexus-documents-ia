# app/services/document_insights_service.py

from sqlalchemy.sql import func, desc
from sqlalchemy import or_
from app.db.database import SessionLocal
from app.db.models import Document, IndexedDocument, DocumentView, DocumentMetrics
from app.core.config import settings
from datetime import datetime, timedelta
from typing import List, Dict, Any
import uuid
import logging
import httpx

logger = logging.getLogger(__name__)


def _indexed_doc_to_dict(doc: IndexedDocument) -> Dict[str, Any]:
    """Convert IndexedDocument to dictionary format compatible with Document."""
    return {
        "id": doc.id,
        "title": doc.title,
        "description": doc.description,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
        "format": doc.file_extension,
        "size": doc.size_bytes or 0,
        "source": "connector",
        "connector_type": doc.connector_type,
    }

class DocumentInsightsService:
    def __init__(self, user_id=None):
        self.user_id = user_id
        self.db = SessionLocal()
    
    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()
    
    def get_trending_documents(self, limit: int = 10, time_period_days: int = 30) -> List[Dict[str, Any]]:
        """Obtiene los documentos con mayor interés en un periodo de tiempo"""
        cutoff_date = datetime.now() - timedelta(days=time_period_days)
        
        # Consulta para obtener documentos ordenados por relevance_score
        documents = self.db.query(Document, DocumentMetrics)\
            .join(DocumentMetrics, Document.id == DocumentMetrics.document_id)\
            .filter(DocumentMetrics.last_viewed_at >= cutoff_date)\
            .order_by(desc(DocumentMetrics.relevance_score))\
            .limit(limit)\
            .all()
        
        # Formatear resultados
        results = []
        for doc, metrics in documents:
            results.append({
                "id": doc.id,
                "title": doc.title,
                "description": doc.description,
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
                "format": doc.file_type,
                "size": doc.file_size,
                "metrics": {
                    "view_count": metrics.view_count,
                    "download_count": metrics.download_count,
                    "share_count": metrics.share_count,
                    "query_count": metrics.query_count,
                    "relevance_score": metrics.relevance_score,
                    "last_viewed_at": metrics.last_viewed_at
                }
            })
        
        return results
    
    def get_recently_viewed_documents(self, limit: int = 10, user_specific: bool = True) -> List[Dict[str, Any]]:
        """Obtiene los documentos vistos recientemente por el usuario o en general"""
        query = self.db.query(
                Document,
                func.max(DocumentView.viewed_at).label("last_viewed_at")
            )\
            .join(DocumentView, Document.id == DocumentView.document_id)

        # Filtrar por usuario si es necesario
        if user_specific and self.user_id:
            query = query.filter(DocumentView.user_id == self.user_id)
        
        # Agrupar, ordenar y limitar resultados
        documents = query\
            .group_by(Document.id)\
            .order_by(desc("last_viewed_at"))\
            .limit(limit)\
            .all()
        
        # Formatear resultados
        results = []
        for doc, last_viewed_at in documents:
            results.append({
                "id": doc.id,
                "title": doc.title,
                "description": doc.description,
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
                "format": doc.file_type,
                "size": doc.file_size,
                "last_viewed_at": last_viewed_at
            })
        
        return results
    
    async def get_document_recommendations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Recomienda documentos basados en el historial de visualización del usuario usando microservicio"""
        if not self.user_id:
            return []
        
        logger.info("LangChain recommendation microservice deprecated. Using local fallback strategy.")
        return self._fallback_recommendations(limit)
    
    def _fallback_recommendations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Método de respaldo para recomendaciones cuando ML no está disponible.
        Devuelve documentos populares que el usuario no ha visto.
        """
        try:
            # Obtener documentos que el usuario ha visto
            user_viewed_docs = self.db.query(DocumentView.document_id)\
                .filter(DocumentView.user_id == self.user_id)\
                .subquery()
            
            # Obtener documentos populares no vistos por el usuario
            documents = self.db.query(Document, DocumentMetrics)\
                .join(DocumentMetrics, Document.id == DocumentMetrics.document_id)\
                .filter(Document.id.notin_(user_viewed_docs))\
                .order_by(desc(DocumentMetrics.relevance_score))\
                .limit(limit)\
                .all()
            
            # Formatear resultados
            results = []
            for doc, metrics in documents:
                results.append({
                    "id": doc.id,
                    "title": doc.title,
                    "description": doc.description,
                    "created_at": doc.created_at,
                    "updated_at": doc.updated_at,
                    "format": doc.file_type,
                    "size": doc.file_size,
                    "reason": f"Documento popular (puntuación: {metrics.relevance_score:.1f})"
                })
            
            return results

        except Exception as e:
            logger.error(f"Error en recomendaciones de respaldo: {str(e)}")
            return []

    def get_document_counts(self) -> Dict[str, int]:
        """
        Get document counts from both Document (uploads) and IndexedDocument (connectors).

        Returns:
            Dict with counts: {uploads, connectors, total}
        """
        try:
            # Count from Document table
            upload_count = self.db.query(func.count(Document.id)).scalar() or 0

            # Count from IndexedDocument table
            connector_count = self.db.query(func.count(IndexedDocument.id)).scalar() or 0

            return {
                "uploads": upload_count,
                "connectors": connector_count,
                "total": upload_count + connector_count
            }
        except Exception as e:
            logger.error(f"Error getting document counts: {str(e)}")
            return {"uploads": 0, "connectors": 0, "total": 0}

    def get_recent_connector_documents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recently indexed documents from connectors (IndexedDocument table).

        This complements get_recently_viewed_documents which only works for
        Document table entries.
        """
        try:
            documents = self.db.query(IndexedDocument)\
                .order_by(desc(IndexedDocument.created_at))\
                .limit(limit)\
                .all()

            return [_indexed_doc_to_dict(doc) for doc in documents]
        except Exception as e:
            logger.error(f"Error getting recent connector documents: {str(e)}")
            return []

# app/services/document_insights_service.py

from app.ml.document_recommender import DocumentRecommender
from sqlalchemy.sql import func, desc
from app.db.database import SessionLocal
from app.db.models import Document, DocumentView, DocumentMetrics
from datetime import datetime, timedelta
from typing import List, Dict, Any
import uuid
import logging

logger = logging.getLogger(__name__)

class DocumentInsightsService:
    def __init__(self, tenant_id, user_id=None):
        self.tenant_id = tenant_id
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
            .filter(
                Document.tenant_id == self.tenant_id,
                DocumentMetrics.last_viewed_at >= cutoff_date
            )\
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
            .join(DocumentView, Document.id == DocumentView.document_id)\
            .filter(Document.tenant_id == self.tenant_id)
        
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
    
    # Modificar el método get_document_recommendations
    def get_document_recommendations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Recomienda documentos basados en el historial de visualización del usuario"""
        if not self.user_id:
            return []
        
        try:
            # Usar recomendador basado en ML
            recommender = DocumentRecommender(tenant_id=self.tenant_id)
            ml_recommendations = recommender.recommend_documents(user_id=self.user_id, n=limit)
            
            # Si hay suficientes recomendaciones de ML, usarlas
            if len(ml_recommendations) >= limit:
                results = []
                for rec in ml_recommendations[:limit]:
                    doc = rec["document"]
                    results.append({
                        "id": doc.id,
                        "title": doc.title,
                        "description": doc.description,
                        "created_at": doc.created_at,
                        "updated_at": doc.updated_at,
                        "format": doc.file_type,
                        "size": doc.file_size,
                        "reason": rec["reason"]
                    })
                return results
            
            # Si no hay suficientes, combinar con el método original
            # (código original del método)
            # ...
            
            return results
        except Exception as e:
            logger.error(f"Error al obtener recomendaciones: {str(e)}")
            # Fallback al método original si hay error
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
                .filter(
                    Document.tenant_id == self.tenant_id,
                    Document.id.notin_(user_viewed_docs)
                )\
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
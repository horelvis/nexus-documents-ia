# app/ml/document_recommender.py

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from app.db.database import get_db
from app.db.models import Document, DocumentView , User
from sqlalchemy.sql import func, desc

import logging

logger = logging.getLogger(__name__)

class DocumentRecommender:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id
        self.db = get_db()
    
    def __del__(self):
        self.db.close()
    
    def build_user_item_matrix(self):
        """Construye una matriz usuario-documento para análisis colaborativo"""
        try:
            # Obtener todas las vistas de documentos para este tenant
            views = self.db.query(
                DocumentView.user_id,
                DocumentView.document_id,
                func.count(DocumentView.id).label("view_count")
            ).filter(
                DocumentView.tenant_id == self.tenant_id
            ).group_by(
                DocumentView.user_id,
                DocumentView.document_id
            ).all()
            
            # Convertir a dataframe
            df = pd.DataFrame(views, columns=["user_id", "document_id", "view_count"])
            
            # Crear matriz usuario-documento
            user_item_matrix = df.pivot(
                index="user_id", 
                columns="document_id", 
                values="view_count"
            ).fillna(0)
            
            return user_item_matrix
        except Exception as e:
            logger.error(f"Error al construir matriz usuario-documento: {str(e)}")
            return None
    
    def get_similar_users(self, user_id, n=5):
        """Encuentra usuarios similares basado en patrones de vista"""
        matrix = self.build_user_item_matrix()
        if matrix is None or user_id not in matrix.index:
            return []
        
        # Calcular similitud de coseno entre usuarios
        user_similarity = cosine_similarity(matrix)
        
        # Crear DataFrame de similitud
        user_similarity_df = pd.DataFrame(
            user_similarity,
            index=matrix.index,
            columns=matrix.index
        )
        
        # Obtener usuarios más similares (excluyendo el propio usuario)
        similar_users = user_similarity_df[user_id].sort_values(ascending=False).drop(user_id).head(n)
        
        return [(user, score) for user, score in similar_users.items()]
    
    def recommend_documents(self, user_id, n=5):
        """Recomienda documentos basado en usuarios similares"""
        # Obtener usuarios similares
        similar_users = self.get_similar_users(user_id)
        if not similar_users:
            return []
        
        # Documentos ya vistos por el usuario
        user_docs = self.db.query(DocumentView.document_id).filter(
            DocumentView.user_id == user_id,
            DocumentView.tenant_id == self.tenant_id
        ).distinct().all()
        
        user_doc_ids = [doc[0] for doc in user_docs]
        
        # Obtener documentos populares entre usuarios similares
        recommended_docs = []
        
        for similar_user_id, similarity_score in similar_users:
            # Documentos vistos por el usuario similar
            similar_user_docs = self.db.query(
                Document, 
                func.count(DocumentView.id).label("view_count")
            ).join(
                DocumentView, Document.id == DocumentView.document_id
            ).filter(
                DocumentView.user_id == similar_user_id,
                DocumentView.tenant_id == self.tenant_id,
                ~Document.id.in_(user_doc_ids)  # Excluir docs ya vistos
            ).group_by(
                Document.id
            ).order_by(
                desc("view_count")
            ).limit(n).all()
            
            # Añadir a la lista de recomendaciones
            for doc, count in similar_user_docs:
                # Calcular puntuación ponderada por similitud del usuario
                weighted_score = count * similarity_score
                
                recommended_docs.append({
                    "document": doc,
                    "score": weighted_score,
                    "reason": f"Popular entre usuarios con intereses similares"
                })
        
        # Ordenar por puntuación y tomar los top N
        recommended_docs.sort(key=lambda x: x["score"], reverse=True)
        return recommended_docs[:n]
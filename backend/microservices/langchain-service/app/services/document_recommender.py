# microservices/langchain-service/app/services/document_recommender.py

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import create_engine, func, desc
from sqlalchemy.orm import sessionmaker
import logging
import os

logger = logging.getLogger(__name__)

class DocumentRecommender:
    def __init__(self, tenant_id, db_url=None):
        self.tenant_id = tenant_id
        # Usar URL de base de datos del environment o parámetro
        database_url = db_url or os.getenv("DATABASE_URL", "postgresql://user:password@localhost/db")
        self.engine = create_engine(database_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = SessionLocal()
    
    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()
    
    def build_user_item_matrix(self):
        """Construye una matriz usuario-documento para análisis colaborativo"""
        try:
            # Query SQL directo para evitar dependencias de modelos
            query = """
                SELECT user_id, document_id, COUNT(*) as view_count
                FROM document_views 
                WHERE tenant_id = :tenant_id
                GROUP BY user_id, document_id
            """
            
            result = self.db.execute(query, {"tenant_id": self.tenant_id})
            views = result.fetchall()
            
            # Convertir a dataframe
            df = pd.DataFrame(views, columns=["user_id", "document_id", "view_count"])
            
            if df.empty:
                return None
            
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
        user_docs_query = """
            SELECT DISTINCT document_id 
            FROM document_views 
            WHERE user_id = :user_id AND tenant_id = :tenant_id
        """
        result = self.db.execute(user_docs_query, {"user_id": user_id, "tenant_id": self.tenant_id})
        user_doc_ids = [row[0] for row in result.fetchall()]
        
        # Obtener documentos populares entre usuarios similares
        recommended_docs = []
        
        for similar_user_id, similarity_score in similar_users:
            # Documentos vistos por el usuario similar
            similar_docs_query = """
                SELECT d.id, d.title, d.filename, COUNT(dv.id) as view_count
                FROM documents d
                JOIN document_views dv ON d.id = dv.document_id
                WHERE dv.user_id = :similar_user_id 
                AND dv.tenant_id = :tenant_id
                AND d.id NOT IN :user_doc_ids
                GROUP BY d.id, d.title, d.filename
                ORDER BY view_count DESC
                LIMIT :limit
            """
            
            user_doc_ids_str = "(" + ",".join(map(str, user_doc_ids)) + ")" if user_doc_ids else "(NULL)"
            
            result = self.db.execute(
                similar_docs_query.replace("NOT IN :user_doc_ids", f"NOT IN {user_doc_ids_str}"),
                {
                    "similar_user_id": similar_user_id,
                    "tenant_id": self.tenant_id,
                    "limit": n
                }
            )
            
            docs = result.fetchall()
            
            # Añadir a la lista de recomendaciones
            for doc in docs:
                doc_id, title, filename, count = doc
                # Calcular puntuación ponderada por similitud del usuario
                weighted_score = count * similarity_score
                
                recommended_docs.append({
                    "document_id": doc_id,
                    "title": title,
                    "filename": filename,
                    "score": weighted_score,
                    "reason": f"Popular entre usuarios con intereses similares"
                })
        
        # Ordenar por puntuación y tomar los top N
        recommended_docs.sort(key=lambda x: x["score"], reverse=True)
        return recommended_docs[:n]
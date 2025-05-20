import logging
import os
import numpy as np
from typing import List, Dict, Any, Optional, Union
import uuid

import qdrant_client
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorService:
    """Servicio para la gestión de vectores en la base de datos Qdrant"""
    
    def __init__(self, tenant_id: str = None):
        """
        Inicializa el servicio de vectores.
        
        Args:
            tenant_id: ID del tenant para separar colecciones
        """
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        self.embedding_dim = 1536  # Dimensión típica para embeddings de modelos Ollama
        
        # Inicializar cliente Qdrant
        self.client = qdrant_client.QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT
        )
        
        # Nombre de la colección específica para el tenant
        self.collection_name = f"{settings.QDRANT_COLLECTION}_{self.tenant_id}"
        
        # Inicializar la colección si no existe
        self._init_collection()
    
    def _init_collection(self):
        """Inicializa la colección en Qdrant si no existe"""
        try:
            # Comprobar si la colección existe
            collections = self.client.get_collections().collections
            collection_names = [collection.name for collection in collections]
            
            if self.collection_name not in collection_names:
                # Crear nueva colección
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.embedding_dim,
                        distance=models.Distance.COSINE
                    )
                )
                logger.info(f"Colección Qdrant '{self.collection_name}' creada exitosamente")
            else:
                logger.info(f"Usando colección Qdrant existente '{self.collection_name}'")
                
        except Exception as e:
            logger.exception(f"Error inicializando colección Qdrant: {str(e)}")
            raise
    
    def add_document_vectors(
        self, 
        doc_id: str, 
        vectors: List[np.ndarray], 
        metadatas: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Añade vectores de un documento a la base de datos.
        
        Args:
            doc_id: ID del documento
            vectors: Lista de vectores de embedding
            metadatas: Lista de metadatos correspondientes a cada vector
            
        Returns:
            Lista de IDs de puntos creados
        """
        try:
            if len(vectors) != len(metadatas):
                raise ValueError("El número de vectores y metadatos debe ser igual")
            
            # Generar IDs para cada vector
            point_ids = [str(uuid.uuid4()) for _ in range(len(vectors))]
            
            # Crear puntos para upsert
            points = []
            for i, (vector, metadata) in enumerate(zip(vectors, metadatas)):
                # Asegurarse de que doc_id esté en los metadatos
                metadata["doc_id"] = doc_id
                
                # Crear punto
                points.append(models.PointStruct(
                    id=point_ids[i],
                    vector=vector.tolist(),
                    payload=metadata
                ))
            
            # Insertar puntos en la colección
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            
            logger.info(f"Añadidos {len(points)} vectores para documento {doc_id}")
            return point_ids
            
        except Exception as e:
            logger.exception(f"Error añadiendo vectores a Qdrant: {str(e)}")
            raise
    
    def search_similar(
        self, 
        query_vector: np.ndarray, 
        limit: int = 10, 
        filter_by: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca vectores similares en la base de datos.
        
        Args:
            query_vector: Vector de consulta
            limit: Número máximo de resultados
            filter_by: Filtros para la búsqueda
            
        Returns:
            Lista de resultados con metadatos y puntuaciones
        """
        try:
            # Crear objeto de filtro si es necesario
            filter_obj = None
            if filter_by:
                conditions = []
                
                # Filtrar por ID de documento
                if "doc_ids" in filter_by and filter_by["doc_ids"]:
                    conditions.append(
                        models.FieldCondition(
                            key="doc_id",
                            match=models.MatchAny(any=filter_by["doc_ids"])
                        )
                    )
                
                # Filtrar por metadatos adicionales
                for key, value in filter_by.items():
                    if key != "doc_ids" and value is not None:
                        conditions.append(
                            models.FieldCondition(
                                key=key,
                                match=models.MatchValue(value=value)
                            )
                        )
                
                if conditions:
                    filter_obj = models.Filter(
                        must=conditions
                    )
            
            # Realizar búsqueda
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector.tolist(),
                limit=limit,
                query_filter=filter_obj
            )
            
            # Formatear resultados
            results = []
            for res in search_results:
                results.append({
                    "score": res.score,
                    "metadata": res.payload
                })
            
            return results
            
        except Exception as e:
            logger.exception(f"Error al buscar en Qdrant: {str(e)}")
            return []
    
    def delete_document_vectors(self, doc_id: str) -> bool:
        """
        Elimina todos los vectores asociados a un documento.
        
        Args:
            doc_id: ID del documento
            
        Returns:
            True si se eliminaron con éxito, False en caso contrario
        """
        try:
            # Eliminar vectores con el filtro de doc_id
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="doc_id",
                                match=models.MatchValue(value=doc_id)
                            )
                        ]
                    )
                )
            )
            
            logger.info(f"Vectores eliminados para documento {doc_id}")
            return True
            
        except Exception as e:
            logger.exception(f"Error eliminando vectores de Qdrant: {str(e)}")
            return False
    
    def get_document_vectors(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene todos los vectores asociados a un documento.
        
        Args:
            doc_id: ID del documento
            
        Returns:
            Lista de vectores con sus metadatos
        """
        try:
            # Buscar vectores con el filtro de doc_id
            results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="doc_id",
                            match=models.MatchValue(value=doc_id)
                        )
                    ]
                ),
                limit=1000  # Límite máximo para un documento
            )
            
            vectors = []
            for point in results[0]:
                vectors.append({
                    "id": point.id,
                    "vector": np.array(point.vector),
                    "metadata": point.payload
                })
            
            return vectors
            
        except Exception as e:
            logger.exception(f"Error obteniendo vectores de Qdrant: {str(e)}")
            return []
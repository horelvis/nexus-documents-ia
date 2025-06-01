"""
LLM Service using LangChain microservice HTTP client
"""
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.services.langchain_client import LangChainClient

logger = logging.getLogger(__name__)


class LLMService:
    """Servicio para generación de texto y RAG usando el microservicio LangChain"""
    
    def __init__(self):
        logger.info("LLMService initialized with LangChain microservice client")
    
    async def generate_response(
        self, 
        query: str, 
        doc_ids: List[str] = None, 
        tenant_id: str = None,
        max_tokens: int = 500
    ) -> Dict[str, Any]:
        """
        Genera una respuesta usando RAG o LLM directo.
        
        Args:
            query: Pregunta o consulta del usuario
            doc_ids: Lista opcional de IDs de documentos para RAG
            tenant_id: ID del tenant para búsqueda vectorial
            max_tokens: Máximo número de tokens en la respuesta
            
        Returns:
            Diccionario con la respuesta y fuentes (si aplica)
        """
        try:
            logger.debug(f"Generating response for query: {query[:100]}...")
            
            # Usar cliente HTTP para generar respuesta
            async with LangChainClient() as client:
                response = await client.generate_response(
                    query=query,
                    tenant_id=tenant_id,
                    doc_ids=doc_ids,
                    max_tokens=max_tokens
                )
            
            return response
                
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return {
                "answer": "Lo siento, ocurrió un error al procesar tu consulta. Por favor, intenta nuevamente.",
                "sources": [],
                "error": str(e)
            }
    
    async def suggest_tags(self, text: str, num_tags: int = 5) -> List[str]:
        """
        Sugiere tags relevantes para un texto.
        
        Args:
            text: Texto para analizar
            num_tags: Número de tags a sugerir
            
        Returns:
            Lista de tags sugeridos
        """
        try:
            logger.debug(f"Generating {num_tags} tags for text of length: {len(text)}")
            
            # Usar cliente HTTP para sugerir tags
            async with LangChainClient() as client:
                tags = await client.suggest_tags(text, num_tags)
            
            logger.debug(f"Generated tags: {tags}")
            return tags
            
        except Exception as e:
            logger.error(f"Error generating tags: {str(e)}")
            return ["documento", "texto", "contenido"]  # Tags por defecto
    
    async def extract_metadata(self, text: str) -> Dict[str, str]:
        """
        Extrae metadatos relevantes de un texto.
        
        Args:
            text: Texto para analizar
            
        Returns:
            Diccionario con metadatos extraídos
        """
        try:
            logger.debug(f"Extracting metadata from text of length: {len(text)}")
            
            # Usar cliente HTTP para extraer metadatos
            async with LangChainClient() as client:
                metadata = await client.extract_metadata(text)
            
            logger.debug(f"Extracted metadata: {metadata}")
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            return {
                "título": "Documento",
                "tipo": "texto",
                "estado": "procesado"
            }
    
    async def summarize_text(self, text: str, max_length: int = 200) -> str:
        """
        Genera un resumen del texto.
        
        Args:
            text: Texto a resumir
            max_length: Longitud máxima del resumen
            
        Returns:
            Resumen del texto
        """
        try:
            logger.debug(f"Summarizing text of length: {len(text)}")
            
            # Usar cliente HTTP para resumir texto
            async with LangChainClient() as client:
                summary = await client.summarize_text(text, max_length)
            
            logger.debug(f"Generated summary of length: {len(summary)}")
            return summary
            
        except Exception as e:
            logger.error(f"Error summarizing text: {str(e)}")
            return "Resumen no disponible."
    
    def create_custom_prompt(self, template: str, variables: Dict[str, str]) -> str:
        """
        Crea un prompt personalizado con variables.
        
        Args:
            template: Template del prompt con placeholders
            variables: Variables para rellenar el template
            
        Returns:
            Prompt formateado
        """
        try:
            # Implementación simple de formateo de template
            prompt = template
            for key, value in variables.items():
                prompt = prompt.replace(f"{{{key}}}", value)
            return prompt
            
        except Exception as e:
            logger.error(f"Error creating custom prompt: {str(e)}")
            return template
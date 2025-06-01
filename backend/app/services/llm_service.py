"""
LangChain-based LLM Service with RAG capabilities
"""
import logging
from typing import List, Dict, Any, Optional

from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.schema import Document

from app.core.config import settings
from app.core.langchain_config import LangChainManager
from app.services.vector_service import VectorService

logger = logging.getLogger(__name__)


class LLMService:
    """Servicio para generación de texto y RAG usando LangChain"""
    
    def __init__(self):
        self.llm = LangChainManager.get_llm()
        logger.info("LLMService initialized with LangChain")
    
    def create_rag_chain(self, vectorstore):
        """Crea una cadena RAG con el vectorstore proporcionado"""
        return LangChainManager.create_rag_chain(vectorstore)
    
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
            if doc_ids and tenant_id:
                # Usar RAG con documentos específicos
                logger.debug(f"Generating RAG response for query: {query[:100]}...")
                
                vector_service = VectorService(tenant_id)
                vectorstore = vector_service.get_vectorstore()
                
                # Crear chain RAG
                chain = self.create_rag_chain(vectorstore)
                
                # Filtrar por documentos específicos si se proporcionan
                if doc_ids:
                    # Buscar contexto relevante en documentos específicos
                    context_results = vector_service.search_by_document_ids(
                        doc_ids=doc_ids,
                        query=query,
                        limit=5
                    )
                    
                    if context_results:
                        # Ejecutar chain con contexto filtrado
                        result = chain({"query": query})
                        
                        return {
                            "answer": result["result"],
                            "sources": [
                                {
                                    "content": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                                    "metadata": doc.metadata
                                }
                                for doc in result.get("source_documents", [])
                            ],
                            "context_used": len(context_results)
                        }
                    else:
                        # No se encontró contexto relevante
                        return {
                            "answer": "Lo siento, no encontré información relevante en los documentos especificados para responder tu pregunta.",
                            "sources": [],
                            "context_used": 0
                        }
                else:
                    # RAG sin filtro de documentos
                    result = chain({"query": query})
                    
                    return {
                        "answer": result["result"],
                        "sources": [
                            {
                                "content": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                                "metadata": doc.metadata
                            }
                            for doc in result.get("source_documents", [])
                        ]
                    }
            else:
                # LLM directo sin RAG
                logger.debug(f"Generating direct LLM response for query: {query[:100]}...")
                
                response = self.llm.invoke(query)
                
                return {
                    "answer": response,
                    "sources": [],
                    "type": "direct_llm"
                }
                
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
            
            prompt = f"""Analiza el siguiente texto y sugiere {num_tags} tags o etiquetas relevantes.
            Las etiquetas deben ser palabras clave que describan el contenido, tema o categoría del texto.
            Responde solo con las etiquetas separadas por comas, sin explicaciones adicionales.

            Texto: {text[:2000]}

            Etiquetas:"""
            
            response = self.llm.invoke(prompt)
            
            # Procesar respuesta para extraer tags
            tags = [tag.strip() for tag in response.split(',')]
            tags = [tag for tag in tags if tag and len(tag) > 1]  # Filtrar tags vacíos o muy cortos
            
            logger.debug(f"Generated tags: {tags}")
            return tags[:num_tags]  # Limitar al número solicitado
            
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
            
            prompt = f"""Analiza el siguiente texto y extrae metadatos relevantes.
            Identifica información como título, autor, fecha, categoría, tema principal, etc.
            Responde en formato JSON con las claves en español.

            Texto: {text[:2000]}

            Metadatos JSON:"""
            
            response = self.llm.invoke(prompt)
            
            # Intentar parsear como JSON, si falla usar valores por defecto
            try:
                import json
                metadata = json.loads(response)
            except:
                # Si no se puede parsear, crear metadatos básicos
                metadata = {
                    "título": "Documento sin título",
                    "tipo": "documento",
                    "idioma": "español"
                }
            
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
            
            prompt = f"""Resume el siguiente texto en aproximadamente {max_length} caracteres.
            El resumen debe capturar las ideas principales y ser coherente.

            Texto: {text}

            Resumen:"""
            
            response = self.llm.invoke(prompt)
            
            # Truncar si es necesario
            if len(response) > max_length:
                response = response[:max_length-3] + "..."
            
            logger.debug(f"Generated summary of length: {len(response)}")
            return response
            
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
            prompt_template = PromptTemplate(
                template=template,
                input_variables=list(variables.keys())
            )
            return prompt_template.format(**variables)
            
        except Exception as e:
            logger.error(f"Error creating custom prompt: {str(e)}")
            return template
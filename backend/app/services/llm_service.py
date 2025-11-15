"""
LLM Service migrado para usar directamente Ollama y Weaviate/Elysia
Reemplaza el anterior LangChain microservice con integración directa
"""
import logging
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Servicio para generación de texto y RAG usando Ollama directo + Weaviate/Elysia"""
    
    def __init__(self):
        self.ollama_base_url = settings.OLLAMA_BASE_URL
        self.weaviate_service_url = settings.WEAVIATE_SERVICE_URL
        self.api_key = settings.MICROSERVICES_API_KEY
        self.default_model = settings.OLLAMA_MODEL or "llama3.1:8b"
        logger.info(
            "LLMService initialized | ollama_base_url=%s weaviate_service_url=%s default_model=%s",
            self.ollama_base_url,
            self.weaviate_service_url,
            self.default_model,
        )
    
    async def generate_response(
        self,
        query: str,
        doc_ids: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
        max_tokens: int = 500,
        use_rag: bool = True
    ) -> Dict[str, Any]:
        """Generate LLM response with optional RAG using Weaviate/Elysia"""
        try:
            if use_rag and tenant_id:
                # Use Elysia for RAG-enabled responses
                return await self._generate_with_elysia_rag(
                    query, tenant_id, max_tokens, doc_ids
                )
            else:
                # Direct Ollama generation
                return await self._generate_direct_ollama(query, max_tokens)
                
        except Exception as e:
            logger.exception(
                "❌ LLM generation failed | use_rag=%s tenant_id=%s doc_ids=%s error=%s",
                use_rag,
                tenant_id,
                doc_ids if doc_ids else "[]",
                e,
            )
            raise
    
    async def _generate_with_elysia_rag(
        self, 
        query: str, 
        tenant_id: str, 
        max_tokens: int,
        doc_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Generate response using Elysia RAG system"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                url = f"{self.weaviate_service_url}/elysia/query"
                
                payload = {
                    "query": query,
                    "tenant_id": tenant_id,
                    "query_type": "search",
                    "max_iterations": 3,
                    "enable_learning": True
                }
                
                if doc_ids:
                    payload["context"] = {"doc_ids": doc_ids}
                
                logger.debug(
                    "Invocando Elysia RAG | url=%s tenant_id=%s doc_ids=%s max_tokens=%d",
                    url,
                    tenant_id,
                    doc_ids if doc_ids else "[]",
                    max_tokens,
                )
                
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                }
                
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                
                elysia_result = response.json()
                
                return {
                    "answer": elysia_result.get("answer", "No response generated"),
                    "sources": elysia_result.get("data", {}).get("documents", []),
                    "context_used": len(elysia_result.get("data", {}).get("documents", [])),
                    "confidence_score": elysia_result.get("confidence_score", 0.8),
                    "execution_time_ms": elysia_result.get("execution_time_ms", 0),
                    "tools_used": elysia_result.get("tools_used", []),
                    "decision_path": elysia_result.get("decision_path", [])
                }
                
        except Exception as e:
            logger.exception(
                "❌ Elysia RAG generation failed | url=%s tenant_id=%s doc_ids=%s error=%s",
                f"{self.weaviate_service_url}/elysia/query",
                tenant_id,
                doc_ids if doc_ids else "[]",
                e,
            )
            # Fallback to direct Ollama
            return await self._generate_direct_ollama(query, max_tokens)
    
    async def _generate_direct_ollama(self, query: str, max_tokens: int) -> Dict[str, Any]:
        """Generate response using direct Ollama"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.ollama_base_url}/api/generate"
                
                payload = {
                    "model": self.default_model,
                    "prompt": query,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": 0.7
                    }
                }
                
                logger.debug(
                    "Invocando Ollama generate | url=%s model=%s prompt_chars=%d max_tokens=%d",
                    url,
                    self.default_model,
                    len(query),
                    max_tokens,
                )
                
                response = await client.post(url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                
                return {
                    "answer": result.get("response", "No response generated"),
                    "sources": [],
                    "context_used": 0,
                    "model": self.default_model,
                    "tokens_generated": result.get("eval_count", 0)
                }
                
        except Exception as e:
            logger.exception(
                "❌ Direct Ollama generation failed | url=%s model=%s error=%s",
                f"{self.ollama_base_url}/api/generate",
                self.default_model,
                e,
            )
            raise
    
    async def suggest_tags(self, text: str, num_tags: int = 5) -> List[str]:
        """Suggest tags for text using Ollama"""
        try:
            prompt = f"""Analyze the following text and suggest {num_tags} relevant tags (keywords). 
Return only the tags separated by commas, no explanations.

Text: {text[:1000]}

Tags:"""

            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.ollama_base_url}/api/generate"
                
                payload = {
                    "model": self.default_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 50,
                        "temperature": 0.3
                    }
                }
                
                response = await client.post(url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                tags_text = result.get("response", "").strip()
                
                # Parse tags from response
                tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()]
                return tags[:num_tags]
                
        except Exception as e:
            logger.exception(
                "❌ Tag suggestion failed | url=%s model=%s prompt_chars=%d error=%s",
                f"{self.ollama_base_url}/api/generate",
                self.default_model,
                len(text),
                e,
            )
            return []
    
    async def extract_metadata(self, text: str) -> Dict[str, Any]:
        """Extract metadata from text using Ollama"""
        try:
            prompt = f"""Extract key metadata from this text. Return a JSON object with relevant fields like title, author, date, category, language, etc.

Text: {text[:1500]}

JSON:"""

            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.ollama_base_url}/api/generate"
                
                payload = {
                    "model": self.default_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 200,
                        "temperature": 0.1
                    }
                }
                
                response = await client.post(url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                metadata_text = result.get("response", "").strip()
                
                # Try to parse JSON response
                try:
                    import json
                    metadata = json.loads(metadata_text)
                    return metadata
                except Exception:
                    # If JSON parsing fails, return basic metadata
                    return {
                        "extracted_text": metadata_text,
                        "length": len(text),
                        "word_count": len(text.split())
                    }
                    
        except Exception as e:
            logger.exception(
                "❌ Metadata extraction failed | url=%s model=%s prompt_chars=%d error=%s",
                f"{self.ollama_base_url}/api/generate",
                self.default_model,
                len(text),
                e,
            )
            return {"error": str(e)}
    
    async def summarize_text(self, text: str, max_length: int = 200) -> str:
        """Summarize text using Ollama"""
        try:
            prompt = f"""Provide a concise summary of the following text in about {max_length} characters:

Text: {text}

Summary:"""

            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.ollama_base_url}/api/generate"
                
                payload = {
                    "model": self.default_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_length // 4,  # Rough estimate
                        "temperature": 0.3
                    }
                }
                
                response = await client.post(url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                summary = result.get("response", "").strip()
                
                return summary[:max_length] if len(summary) > max_length else summary
                
        except Exception as e:
            logger.error(f"❌ Text summarization failed: {e}")
            return f"Error generating summary: {str(e)}"
    
    async def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract named entities from text using Ollama"""
        try:
            prompt = f"""Extract named entities from this text. Return a JSON list of entities with their type (PERSON, ORGANIZATION, LOCATION, etc.) and position.

Text: {text[:1000]}

JSON:"""

            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.ollama_base_url}/api/generate"
                
                payload = {
                    "model": self.default_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 300,
                        "temperature": 0.1
                    }
                }
                
                response = await client.post(url, json=payload)
                response.raise_for_status()
                
                result = response.json()
                entities_text = result.get("response", "").strip()
                
                # Try to parse JSON response
                try:
                    import json
                    entities = json.loads(entities_text)
                    return entities if isinstance(entities, list) else []
                except:
                    # If JSON parsing fails, return empty list
                    return []
                    
        except Exception as e:
            logger.error(f"❌ Entity extraction failed: {e}")
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of LLM service components"""
        health = {
            "ollama": False,
            "weaviate_service": False,
            "status": "unhealthy"
        }
        
        try:
            # Check Ollama
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.ollama_base_url}/api/tags")
                if response.status_code == 200:
                    health["ollama"] = True
        except:
            pass
        
        try:
            # Check Weaviate Service
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.weaviate_service_url}/health")
                if response.status_code == 200:
                    health["weaviate_service"] = True
        except:
            pass
        
        health["status"] = "healthy" if health["ollama"] else "partial"
        return health

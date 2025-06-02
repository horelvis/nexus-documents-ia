"""
Service for Ollama LLM operations
"""
import asyncio
import httpx
from typing import List, Dict, Any, Optional
from loguru import logger
import ollama

from app.core.config import settings

class OllamaService:
    """Service to interact with Ollama LLM"""
    
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.client = ollama.AsyncClient(host=self.base_url)
        self.timeout = settings.REQUEST_TIMEOUT
        
    async def list_models(self) -> List[Dict[str, Any]]:
        """List available models"""
        try:
            response = await self.client.list()
            return response.get('models', [])
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            raise
    
    async def pull_model(self, model_name: str) -> bool:
        """Pull a model from registry"""
        try:
            logger.info(f"Pulling model: {model_name}")
            await self.client.pull(model_name)
            logger.info(f"Successfully pulled model: {model_name}")
            return True
        except Exception as e:
            logger.error(f"Error pulling model {model_name}: {e}")
            raise
    
    async def delete_model(self, model_name: str) -> bool:
        """Delete a model"""
        try:
            await self.client.delete(model_name)
            logger.info(f"Successfully deleted model: {model_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting model {model_name}: {e}")
            return False
    
    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = None,
        max_tokens: int = None,
        top_p: float = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Chat with a model"""
        try:
            options = {}
            if temperature is not None:
                options['temperature'] = temperature
            if max_tokens is not None:
                options['num_predict'] = max_tokens
            if top_p is not None:
                options['top_p'] = top_p
            
            response = await self.client.chat(
                model=model,
                messages=messages,
                options=options,
                stream=stream
            )
            
            if stream:
                return response
            else:
                return {
                    'model': model,
                    'response': response['message']['content'],
                    'total_duration': response.get('total_duration'),
                    'load_duration': response.get('load_duration'),
                    'prompt_eval_count': response.get('prompt_eval_count'),
                    'eval_count': response.get('eval_count')
                }
        except Exception as e:
            logger.error(f"Error in chat with model {model}: {e}")
            raise
    
    async def generate(
        self,
        model: str,
        prompt: str,
        temperature: float = None,
        max_tokens: int = None,
        top_p: float = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Generate text with a model"""
        try:
            options = {}
            if temperature is not None:
                options['temperature'] = temperature
            if max_tokens is not None:
                options['num_predict'] = max_tokens
            if top_p is not None:
                options['top_p'] = top_p
            
            response = await self.client.generate(
                model=model,
                prompt=prompt,
                options=options,
                stream=stream
            )
            
            if stream:
                return response
            else:
                return {
                    'model': model,
                    'response': response['response'],
                    'total_duration': response.get('total_duration'),
                    'load_duration': response.get('load_duration'),
                    'prompt_eval_count': response.get('prompt_eval_count'),
                    'eval_count': response.get('eval_count')
                }
        except Exception as e:
            logger.error(f"Error generating with model {model}: {e}")
            raise
    
    async def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific model"""
        try:
            response = await self.client.show(model_name)
            return response
        except Exception as e:
            logger.error(f"Error getting model info for {model_name}: {e}")
            return None
    
    async def get_status(self) -> Dict[str, Any]:
        """Get Ollama service status"""
        try:
            # Check if Ollama is running by listing models
            models = await self.list_models()
            return {
                'status': 'healthy',
                'models_count': len(models),
                'base_url': self.base_url,
                'available_models': [model.get('name', 'unknown') for model in models]
            }
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'base_url': self.base_url
            }
    
    async def ensure_model_loaded(self, model_name: str) -> bool:
        """Ensure a model is loaded and ready"""
        try:
            # Try to get model info to check if it exists
            info = await self.get_model_info(model_name)
            if info:
                logger.info(f"Model {model_name} is available")
                return True
            else:
                logger.warning(f"Model {model_name} not found, attempting to pull...")
                await self.pull_model(model_name)
                return True
        except Exception as e:
            logger.error(f"Error ensuring model {model_name} is loaded: {e}")
            return False
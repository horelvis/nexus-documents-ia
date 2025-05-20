import logging
import json
import requests
from typing import List, Dict, Any, Optional
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Servicio para interactuar con modelos LLM a través de Ollama"""
    
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
    
    def _call_ollama_api(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        temperature: float = 0.5,
        max_tokens: int = 1000,
        stream: bool = False
    ) -> str:
        """
        Realiza una llamada a la API de Ollama.
        
        Args:
            prompt: Texto de entrada
            system_prompt: Instrucciones del sistema (opcional)
            temperature: Temperatura de generación (0.0-1.0)
            max_tokens: Número máximo de tokens a generar
            stream: Si se debe usar modo streaming
            
        Returns:
            Texto generado por el modelo
        """
        headers = {
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "temperature": temperature,
            "num_predict": max_tokens,
        }
        
        if system_prompt:
            data["system"] = system_prompt
        
        try:
            start_time = time.time()
            response = requests.post(
                f"{self.base_url}/api/generate",
                headers=headers,
                json=data
            )
            elapsed_time = time.time() - start_time
            
            if response.status_code != 200:
                logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                return f"Error: Unable to get response from Ollama API (Status: {response.status_code})"
            
            if stream:
                # Para streaming, recolectar todos los fragmentos de respuesta
                result = ""
                for line in response.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        result += chunk.get("response", "")
                        if chunk.get("done", False):
                            break
            else:
                # Para respuestas no streaming
                result = response.json().get("response", "")
            
            logger.info(f"Ollama request completed in {elapsed_time:.2f}s")
            return result
            
        except Exception as e:
            logger.exception(f"Error calling Ollama API: {str(e)}")
            return f"Error: {str(e)}"
    
    def summarize_text(self, text: str, max_length: int = 500) -> str:
        """
        Genera un resumen conciso del texto proporcionado.
        
        Args:
            text: Texto a resumir
            max_length: Longitud máxima aproximada del resumen en caracteres
            
        Returns:
            Resumen generado
        """
        if len(text) < max_length:
            return text
        
        # Truncar el texto si es demasiado largo para la API
        max_input_length = 100000  # Ajustar según los límites del modelo
        if len(text) > max_input_length:
            text = text[:max_input_length-1000] + "..."
        
        system_prompt = """
        Eres un asistente experto en resumir documentos. Crea resúmenes concisos 
        que capturen los puntos principales y la información más relevante.
        """
        
        prompt = f"""
        Resume el siguiente texto en aproximadamente {max_length} caracteres, 
        manteniendo los puntos clave y la información más importante:
        
        {text}
        """
        
        return self._call_ollama_api(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=max_length // 2  # Estimación aproximada de tokens
        )
    
    def suggest_tags(self, text: str, num_tags: int = 5) -> List[str]:
        """
        Sugiere etiquetas relevantes basadas en el contenido del texto.
        
        Args:
            text: Texto del documento
            num_tags: Número de etiquetas a sugerir
            
        Returns:
            Lista de etiquetas sugeridas
        """
        # Truncar el texto si es demasiado largo
        max_input_length = 50000  # Ajustar según los límites del modelo
        if len(text) > max_input_length:
            text = text[:max_input_length-1000] + "..."
        
        system_prompt = """
        Eres un experto en análisis de documentos y categorización. Debes identificar 
        las etiquetas más relevantes para el contenido.
        """
        
        prompt = f"""
        Basándote en el siguiente texto, sugiere exactamente {num_tags} etiquetas relevantes. 
        Proporciónalas como una lista separada por comas, usando solo palabras clave concisas 
        (1-2 palabras por etiqueta) sin explicaciones adicionales:
        
        {text}
        """
        
        response = self._call_ollama_api(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=100
        )
        
        # Procesar la respuesta para extraer etiquetas
        try:
            # Eliminar cualquier explicación y quedarse solo con la lista
            if ":" in response:
                response = response.split(":", 1)[1]
            
            # Eliminar puntos, comillas y otros caracteres extraños
            response = response.replace('"', '').replace("'", "").strip()
            
            # Dividir por comas y limpiar espacios
            tags = [tag.strip() for tag in response.split(",") if tag.strip()]
            
            # Limitar al número solicitado
            return tags[:num_tags]
            
        except Exception as e:
            logger.exception(f"Error parsing tags from LLM response: {str(e)}")
            return []
    
    def extract_metadata(self, text: str) -> Dict[str, Any]:
        """
        Extrae metadatos estructurados del texto del documento.
        
        Args:
            text: Texto del documento
            
        Returns:
            Diccionario con metadatos extraídos
        """
        # Truncar el texto si es demasiado largo
        max_input_length = 50000
        if len(text) > max_input_length:
            text = text[:max_input_length-1000] + "..."
        
        system_prompt = """
        Eres un experto en extracción de información y metadata de documentos. 
        Tu tarea es identificar metadatos clave y proporcionarlos en formato JSON.
        """
        
        prompt = f"""
        Extrae los siguientes metadatos del texto proporcionado en formato JSON. 
        Si no puedes determinar un valor, déjalo como null:
        
        1. título: el título principal del documento si está presente
        2. autor: nombre(s) del autor o autores
        3. fecha: cualquier fecha relevante en formato ISO (YYYY-MM-DD)
        4. categoría: la categoría principal del documento
        5. entidades: las 5 entidades principales mencionadas (personas, organizaciones, lugares)
        
        Texto del documento:
        {text}
        
        Responde únicamente con el JSON sin explicaciones adicionales.
        """
        
        response = self._call_ollama_api(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=1000
        )
        
        try:
            # Intentar extraer solo el JSON de la respuesta
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].strip()
            else:
                json_str = response.strip()
            
            # Analizar la respuesta JSON
            metadata = json.loads(json_str)
            return metadata
            
        except Exception as e:
            logger.exception(f"Error parsing metadata from LLM response: {str(e)}")
            return {
                "título": None,
                "autor": None,
                "fecha": None,
                "categoría": None,
                "entidades": []
            }
    
    def answer_question(self, question: str, context: str) -> str:
        """
        Responde una pregunta basándose en el contexto proporcionado.
        
        Args:
            question: Pregunta del usuario
            context: Contexto extraído de los documentos
            
        Returns:
            Respuesta a la pregunta
        """
        # Truncar el contexto si es demasiado largo
        max_context_length = 80000  # Ajustar según los límites del modelo
        if len(context) > max_context_length:
            context = context[:max_context_length-1000] + "..."
        
        system_prompt = """
        Eres un asistente experto en responder preguntas basadas en la información proporcionada. 
        Utiliza solo la información del contexto para responder. Si la información no está en el contexto, 
        indica que no puedes responder basándote en los documentos disponibles. No inventes información. 
        Cita las partes relevantes del contexto para respaldar tu respuesta.
        """
        
        prompt = f"""
        Contexto:
        {context}
        
        Pregunta: {question}
        
        Respuesta:
        """
        
        return self._call_ollama_api(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=1500
        )
    
    def classify_document(self, text: str, categories: List[str]) -> str:
        """
        Clasifica un documento en una de las categorías proporcionadas.
        
        Args:
            text: Texto del documento
            categories: Lista de categorías posibles
            
        Returns:
            La categoría asignada
        """
        # Truncar el texto si es demasiado largo
        max_input_length = 50000
        if len(text) > max_input_length:
            text = text[:max_input_length-1000] + "..."
        
        categories_str = ", ".join(categories)
        
        system_prompt = """
        Eres un experto en clasificación de documentos. Debes asignar cada documento 
        a la categoría más apropiada entre las opciones disponibles.
        """
        
        prompt = f"""
        Clasifica el siguiente texto en una de estas categorías: {categories_str}
        
        Responde solamente con el nombre de la categoría, sin explicaciones adicionales.
        
        Texto:
        {text}
        """
        
        response = self._call_ollama_api(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=50
        )
        
        # Limpiar la respuesta
        response = response.strip()
        
        # Verificar si la respuesta coincide con alguna categoría
        for category in categories:
            if category.lower() in response.lower():
                return category
        
        # Si no hay coincidencia exacta, devolver la respuesta completa
        return response
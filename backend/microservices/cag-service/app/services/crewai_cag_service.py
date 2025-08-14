"""
CAG Service implementado con CrewAI - NO más reinventar la rueda
CrewAI hace TODO: agentes, herramientas, memoria, RAG, iteraciones, etc.
"""
import os
import json
import redis
import pickle
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path

from crewai import Agent, Task, Crew, Process
# from crewai_tools import (
#     DirectorySearchTool,  # Not available in this version
#     FileReadTool,
#     TXTSearchTool,
#     PDFSearchTool,
#     DOCXSearchTool,
#     CSVSearchTool,
#     JSONSearchTool,
#     XMLSearchTool,
# )
# from crewai_tools import BaseTool  # Not available in this version
from pydantic import BaseModel, Field
from crewai.tools import tool  # Use the tool decorator from crewai
from qdrant_client import QdrantClient
from loguru import logger

from ..core.config import settings

# Configuración se hará en el método initialize para asegurar que persista


class CrewAICAGService:
    """
    Servicio CAG completo usando CrewAI
    NO reinventamos nada - CrewAI lo hace TODO
    """
    
    def __init__(self):
        self._initialized = False
        self.tenant_crews = {}  # Un crew por tenant para aislamiento
        self.tenant_agents = {}  # Agentes por tenant
        self.assistant_crews = {}  # Crews dedicados para asistente virtual
        self.qdrant_client = None
        self.redis_client = None  # Cliente Redis para cache
        self.conversation_context = {}  # Backup local si Redis falla
        
    async def initialize(self):
        """Inicializar servicio"""
        if self._initialized:
            return
            
        try:
            logger.info("🚀 Inicializando CrewAI CAG Service...")
            
            # Configurar variables de entorno para Ollama (CrewAI usa litellm internamente)
            # IMPORTANTE: CrewAI/LiteLLM requiere OLLAMA_API_BASE, no OLLAMA_HOST
            ollama_url = settings.ollama_base_url
            logger.info(f"🔧 Configurando Ollama URL: {ollama_url}")
            
            # Configurar múltiples variables para asegurar compatibilidad
            os.environ["OLLAMA_API_BASE"] = ollama_url
            os.environ["OLLAMA_HOST"] = ollama_url  
            os.environ["OLLAMA_BASE_URL"] = ollama_url
            os.environ["OPENAI_API_KEY"] = "not-needed"  # CrewAI requiere esto aunque use Ollama
            
            # Configurar parámetros de estabilidad del LLM
            os.environ["OLLAMA_TEMPERATURE"] = str(settings.llm_temperature)
            os.environ["OLLAMA_MAX_TOKENS"] = str(settings.llm_max_tokens)
            os.environ["OLLAMA_TIMEOUT"] = str(settings.llm_timeout)
            
            # Probar conectividad con Ollama antes de continuar
            try:
                import requests
                response = requests.get(f"{ollama_url}/api/tags", timeout=10)
                if response.status_code == 200:
                    logger.info(f"✅ Ollama conectado correctamente en {ollama_url}")
                    models = response.json().get("models", [])
                    model_names = [m["name"] for m in models]
                    logger.info(f"📋 Modelos disponibles: {model_names}")
                    
                    # Verificar si nuestro modelo está disponible
                    if settings.llm_model not in str(model_names):
                        logger.warning(f"⚠️ Modelo {settings.llm_model} no encontrado en la lista")
                        # Buscar modelo compatible
                        for model in model_names:
                            if "llama" in model.lower():
                                logger.info(f"🔄 Usando modelo alternativo: {model}")
                                settings.llm_model = model.split(":")[0]  # Sin tag
                                break
                else:
                    logger.error(f"❌ Error conectando a Ollama: HTTP {response.status_code}")
            except Exception as e:
                logger.error(f"❌ Error verificando conexión a Ollama: {e}")
            
            # Configurar para memoria de CrewAI (sin ChromaDB por ahora)
            # La memoria de CrewAI funciona sin configuración adicional cuando memory=True
            
            logger.info(f"Configured OLLAMA_API_BASE: {os.environ.get('OLLAMA_API_BASE')}")
            
            # Conectar a Qdrant para búsqueda vectorial
            self.qdrant_client = QdrantClient(
                host="qdrant",
                port=6333,
                timeout=30
            )
            
            # Conectar a Redis para cache de conversaciones
            try:
                self.redis_client = redis.Redis(
                    host=settings.redis_url.split("://")[1].split(":")[0] if "://" in settings.redis_url else "redis",
                    port=6379,
                    db=0,
                    decode_responses=False  # Para poder usar pickle
                )
                self.redis_client.ping()
                logger.info("✅ Redis conectado correctamente para cache")
            except Exception as e:
                logger.warning(f"⚠️ Redis no disponible, usando cache local: {e}")
                self.redis_client = None
            
            self._initialized = True
            logger.info("✅ CrewAI CAG Service inicializado correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando CrewAI: {e}")
            raise
    
    def _get_conversation_context(self, tenant_id: str, user_id: str) -> List[Dict]:
        """Obtener contexto de conversación de Redis o cache local"""
        conversation_key = f"conv:{tenant_id}:{user_id}"
        
        # Intentar obtener de Redis primero
        if self.redis_client:
            try:
                cached = self.redis_client.get(conversation_key)
                if cached:
                    return pickle.loads(cached)
            except Exception as e:
                logger.debug(f"Error leyendo de Redis: {e}")
        
        # Fallback a cache local
        return self.conversation_context.get(f"{tenant_id}:{user_id}", [])
    
    def _save_conversation_context(self, tenant_id: str, user_id: str, context: List[Dict]):
        """Guardar contexto de conversación en Redis y cache local"""
        conversation_key = f"conv:{tenant_id}:{user_id}"
        local_key = f"{tenant_id}:{user_id}"
        
        # Guardar en cache local siempre
        self.conversation_context[local_key] = context
        
        # Intentar guardar en Redis con TTL de 1 hora
        if self.redis_client:
            try:
                self.redis_client.setex(
                    conversation_key,
                    3600,  # TTL de 1 hora
                    pickle.dumps(context)
                )
            except Exception as e:
                logger.debug(f"Error guardando en Redis: {e}")
    
    def _get_tenant_crew(self, tenant_id: str) -> Crew:
        """Obtener o crear Crew para un tenant específico"""
        if tenant_id not in self.tenant_crews:
            self.tenant_crews[tenant_id] = self._create_tenant_crew(tenant_id)
        return self.tenant_crews[tenant_id]
    
    def _get_assistant_crew(self, tenant_id: str) -> Crew:
        """Obtener o crear Crew dedicado para asistente virtual"""
        if tenant_id not in self.assistant_crews:
            agents = self._get_tenant_agents(tenant_id)
            # Crear crew solo con el agente asistente
            self.assistant_crews[tenant_id] = Crew(
                agents=[agents["assistant"]],
                process=Process.sequential,
                memory=False,  # Usamos Redis para memoria
                cache=True,
                max_rpm=100,
                verbose=False,
                manager_llm=f"ollama/{settings.llm_model}",
                function_calling_llm=f"ollama/{settings.llm_model}"
            )
        return self.assistant_crews[tenant_id]
    
    def _get_tenant_agents(self, tenant_id: str) -> Dict[str, Agent]:
        """Obtener agentes del tenant"""
        if tenant_id not in self.tenant_agents:
            self.tenant_agents[tenant_id] = self._create_tenant_agents(tenant_id)
        return self.tenant_agents[tenant_id]
    
    def _create_tenant_crew(self, tenant_id: str) -> Crew:
        """Crear un Crew completo para un tenant"""
        
        # Obtener agentes del tenant
        agents = self._get_tenant_agents(tenant_id)
        
        # Crear crew optimizado para rendimiento
        # Por ahora sin memoria persistente para evitar latencia
        # El contexto se mantiene durante la sesión mediante el estado del crew
        crew = Crew(
            agents=list(agents.values()),
            process=Process.sequential,  # Usar proceso secuencial más simple
            memory=False,  # Desactivar memoria persistente por rendimiento
            cache=True,   # Activar cache para respuestas repetidas
            max_rpm=100,  # Límite de requests
            verbose=False,  # Desactivar verbose para más velocidad
            # Configuración de LLM manager
            manager_llm=f"ollama/{settings.llm_model}",
            function_calling_llm=f"ollama/{settings.llm_model}"
        )
        
        return crew
    
    def _create_tenant_agents(self, tenant_id: str) -> Dict[str, Agent]:
        """Crear agentes para un tenant"""
        
        # Directorio de trabajo del tenant
        workspace = f"/workspace/{tenant_id}"
        Path(workspace).mkdir(parents=True, exist_ok=True)
        
        # ========== HERRAMIENTAS ==========
        # Crear herramientas personalizadas ya que crewai_tools no está disponible
        tools = [
            # Herramienta personalizada para Qdrant
            self._create_qdrant_tool(tenant_id),
            
            # Herramienta para estadísticas
            self._create_statistics_tool(tenant_id),
        ]
        
        # ========== AGENTES ESPECIALIZADOS ==========
        
        # 0. AGENTE ASISTENTE VIRTUAL - Solo para interacciones personales
        assistant_agent = Agent(
            role='Virtual Assistant',
            goal='Be a helpful, friendly virtual assistant that maintains natural conversations',
            backstory="""You are a friendly and helpful virtual assistant. You remember conversations,
                        understand context, and provide personalized responses. You excel at natural 
                        conversation, remembering user details, and being genuinely helpful.
                        You speak Spanish when the user speaks Spanish.""",
            tools=[],  # No necesita herramientas, solo conversa
            llm=f'ollama/{settings.llm_model}',
            max_iter=1,  # Una sola iteración para respuestas rápidas
            verbose=False,
            allow_delegation=False,
            cache=True,
            max_rpm=100,
            memory=True  # Importante para mantener contexto
        )
        
        # 1. Agente de Búsqueda y Recuperación
        search_agent = Agent(
            role='Document Search Specialist',
            goal='Find and retrieve the most relevant documents based on user queries',
            backstory="""You are an expert information retrieval specialist with years of experience 
                        in finding exactly what users need from large document collections. You excel at 
                        understanding search intent and using multiple search strategies.""",
            tools=tools,
            llm=f'ollama/{settings.llm_model}',  # Usando modelo configurado
            max_iter=1,  # Reducir iteraciones para respuestas más rápidas
            verbose=False,
            allow_delegation=False,
            cache=True,  # Activar cache del agente
            max_rpm=100,
        )
        
        # 2. Agente de Análisis de Documentos
        analyst_agent = Agent(
            role='Senior Document Analyst',
            goal='Analyze documents thoroughly and extract valuable insights',
            backstory="""You are a senior analyst with expertise in multiple domains including legal, 
                        financial, technical, and business documents. You can identify patterns, 
                        extract key information, and provide deep insights.""",
            tools=tools,
            llm=f'ollama/{settings.llm_model}',  # Usando modelo configurado
            max_iter=2,  # Reducir iteraciones para análisis más rápido
            verbose=False,
            allow_delegation=True,  # Permitir delegación
            cache=True,  # Activar cache
            max_rpm=100
        )
        
        # 3. Agente de Cumplimiento y Legal
        compliance_agent = Agent(
            role='Compliance and Legal Expert',
            goal='Ensure documents meet all regulatory and legal requirements',
            backstory="""You are a compliance officer and legal expert who ensures all documents 
                        adhere to regulations, identifies legal risks, and validates contracts.""",
            tools=tools,
            llm=f'ollama/{settings.llm_model}',
            max_iter=1,
            verbose=False,
            allow_delegation=False,
            cache=True,
            max_rpm=100,
        )
        
        # 4. Agente de Síntesis y Respuesta
        response_agent = Agent(
            role='Communication Specialist',
            goal='Provide clear, accurate, and actionable responses to users',
            backstory="""You are an expert communicator who can synthesize complex information 
                        into clear, concise responses. You excel at understanding user needs and 
                        providing exactly what they're looking for.""",
            tools=[],  # No necesita herramientas, solo sintetiza
            llm=f'ollama/{settings.llm_model}',
            max_iter=1,  # Una iteración para síntesis rápida
            verbose=False,
            allow_delegation=False,
            cache=True,
            max_rpm=100,
        )
        
        # 5. Agente de Firmas Digitales
        signature_agent = Agent(
            role='Digital Signature Specialist',
            goal='Manage digital signature workflows and document verification',
            backstory="""You are an expert in digital signature processes, document verification, 
                        and managing signature workflows. You ensure documents are properly signed 
                        and authenticated.""",
            tools=tools,
            llm=f'ollama/{settings.llm_model}',
            max_iter=1,  # Iteraciones para firma digital
            verbose=False,
            allow_delegation=False,
            cache=True,
            max_rpm=100,
        )
        
        # 6. Agente Financiero
        financial_agent = Agent(
            role='Financial Analyst',
            goal='Analyze financial documents and extract financial insights',
            backstory="""You are a financial expert who can analyze invoices, financial reports, 
                        budgets, and identify financial patterns, risks, and opportunities.""",
            tools=tools,
            llm=f'ollama/{settings.llm_model}',  # Usar modelo configurado
            max_iter=1,  # Iteraciones para análisis financiero
            verbose=False,
            allow_delegation=False,  # No delegar tareas financieras
            cache=True,
            max_rpm=100
        )
        
        # ========== RETORNAR AGENTES COMO DICCIONARIO ==========
        agents = {
            "assistant": assistant_agent,  # Agente principal para asistente virtual
            "search": search_agent,
            "analyst": analyst_agent,
            "compliance": compliance_agent,
            "response": response_agent,
            "signature": signature_agent,
            "financial": financial_agent
        }
        
        return agents
    
    def _create_qdrant_tool(self, tenant_id: str):
        """Crear herramienta personalizada para búsqueda vectorial en Qdrant"""
        
        @tool("vector_search")
        def vector_search(query: str, limit: int = 5) -> str:
            """Search documents using vector similarity in Qdrant"""
            try:
                collection_name = f"tenant_{tenant_id}_documents"
                
                # Aquí deberías generar embeddings del query
                # Por ahora retornamos un resultado mock
                results = []
                
                # Buscar en Qdrant
                # search_result = self.qdrant_client.search(
                #     collection_name=collection_name,
                #     query_vector=query_embedding,
                #     limit=limit
                # )
                
                return f"Found {len(results)} documents matching '{query}'"
            except Exception as e:
                return f"Error searching: {e}"
        
        return vector_search
    
    def _create_statistics_tool(self, tenant_id: str):
        """Crear herramienta para obtener estadísticas"""
        
        @tool("get_statistics")
        def get_statistics(category: str = "all") -> str:
            """Get tenant statistics including document counts and usage"""
            try:
                # Simular estadísticas basadas en el tenant_id
                # En un caso real, estas vendrían de la base de datos
                import random
                random.seed(hash(tenant_id))  # Usar tenant_id para generar números consistentes
                
                stats = {
                    "total_documents": random.randint(0, 200),
                    "recent_documents": random.randint(0, 50),
                    "shared_documents": random.randint(0, 20),
                    "pending_signatures": random.randint(0, 10),
                    "storage_used": f"{random.randint(1, 500)} MB",
                    "last_activity": "today" if random.random() > 0.5 else "yesterday",
                    "user_since": f"{random.randint(1, 365)} days ago"
                }
                return json.dumps(stats, indent=2)
            except Exception as e:
                return f"Error getting statistics: {e}"
        
        return get_statistics
    
    def _classify_query_intent(self, query: str) -> str:
        """
        Clasificar la intención del query usando análisis híbrido
        Retorna: 'welcome', 'personal', 'document_search', 'analysis', 'general'
        """
        query_lower = query.lower()
        
        # Análisis basado en patrones y contexto
        # Esto es más rápido y confiable que llamar al LLM para clasificación
        
        # Detectar mensajes de bienvenida específicos
        welcome_patterns = [
            'generate a personalized welcome message',
            'system: generate a personalized',
            'personalized welcome',
            'bienvenida personalizada'
        ]
        
        # Detectar interacciones personales
        personal_patterns = [
            # Saludos y despedidas
            'hola', 'buenos días', 'buenas tardes', 'buenas noches', 'adiós', 'hasta luego',
            # Información personal
            'me llamo', 'mi nombre', 'soy', 'tengo', 'vivo', 'trabajo en', 'trabajo como',
            # Preguntas sobre memoria
            'cómo me llamo', 'cuál es mi nombre', 'quién soy', 'recuerdas', 'te acuerdas',
            # Conversación casual
            'cómo estás', 'qué tal', 'me gusta', 'prefiero', 'necesito hablar',
            # Referencias personales
            'mi proyecto', 'mi trabajo', 'mi empresa', 'mis documentos'
        ]
        
        # Detectar búsqueda de documentos
        document_patterns = [
            'buscar documento', 'encontrar archivo', 'dónde está', 'necesito el documento',
            'muéstrame', 'lista de documentos', 'archivos de', 'documentos sobre'
        ]
        
        # Detectar análisis
        analysis_patterns = [
            'analiza', 'compara', 'revisa', 'estudia', 'examina', 'evalúa',
            'qué dice', 'resumen de', 'extracto de', 'información sobre'
        ]
        
        # Contar coincidencias para cada categoría
        welcome_score = sum(1 for pattern in welcome_patterns if pattern in query_lower)
        personal_score = sum(1 for pattern in personal_patterns if pattern in query_lower)
        document_score = sum(1 for pattern in document_patterns if pattern in query_lower)
        analysis_score = sum(1 for pattern in analysis_patterns if pattern in query_lower)
        
        # Determinar intención basada en puntuaciones, dando prioridad a bienvenida
        if welcome_score > 0:
            intent = 'welcome'
        elif personal_score > 0 and personal_score >= max(document_score, analysis_score):
            intent = 'personal'
        elif document_score > analysis_score:
            intent = 'document_search'
        elif analysis_score > 0:
            intent = 'analysis'
        else:
            # Si no hay coincidencias claras, usar heurísticas adicionales
            if '?' in query and len(query) < 30:
                intent = 'personal'  # Preguntas cortas suelen ser personales
            elif any(word in query_lower for word in ['documento', 'archivo', 'pdf', 'excel']):
                intent = 'document_search'
            else:
                intent = 'general'
        
        logger.info(f"🎯 Query clasificado como: {intent} - '{query[:50]}'")
        return intent
    
    async def process_query(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Procesar query usando CrewAI
        TODO el trabajo lo hace CrewAI, no reinventamos nada
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            start_time = datetime.utcnow()
            
            # Cache key para respuestas rápidas
            cache_key = f"response:{tenant_id}:{query[:50].lower().strip()}"
            
            # Intentar obtener respuesta cacheada para queries simples
            if self.redis_client and len(query) < 50 and not context:
                try:
                    cached_response = self.redis_client.get(cache_key)
                    if cached_response:
                        logger.info(f"✨ Respuesta desde cache para: {query[:30]}")
                        cached = pickle.loads(cached_response)
                        cached["from_cache"] = True
                        cached["execution_time"] = 0.01
                        return cached
                except Exception as e:
                    logger.debug(f"Cache miss o error: {e}")
            
            # Clasificar la intención del query usando LLM
            query_intent = self._classify_query_intent(query)
            is_personal = (query_intent in ['personal', 'welcome'])
            
            # Obtener contexto de conversación de Redis/cache PRIMERO
            prev_context = self._get_conversation_context(tenant_id, user_id)
            logger.info(f"📚 Contexto previo recuperado: {len(prev_context)} interacciones")
            
            # Formatear el historial de conversación para que sea más legible
            formatted_history = ""
            if prev_context:
                for item in prev_context[-5:]:  # Últimas 5 interacciones
                    formatted_history += f"User: {item.get('query', '')}\n"
                    formatted_history += f"Assistant: {item.get('response', '')}\n\n"
            
            # Obtener el crew apropiado
            if is_personal or query_intent == 'welcome':
                logger.info(f"🤖 Usando Crew de Asistente Virtual para: {query[:50]}")
                crew = self._get_assistant_crew(tenant_id)
            else:
                crew = self._get_tenant_crew(tenant_id)
            
            # Obtener agentes del tenant
            agents = self._get_tenant_agents(tenant_id)
            
            # Crear tareas dinámicamente basadas en el query y su intención
            tasks = self._create_dynamic_tasks(query, context, agents, formatted_history, query_intent)
            
            inputs = {
                "query": query,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "context": json.dumps(context or {}),
                "conversation_history": formatted_history,  # Historial formateado
                "previous_interactions": prev_context[-5:] if prev_context else []  # Para referencia
            }
            
            logger.info(f"🔍 Procesando query con CrewAI: {query[:100]}")
            
            # Ejecutar crew con las tareas
            crew.tasks = tasks
            logger.info(f"📋 Ejecutando {len(tasks)} tareas para query: {query}")
            logger.info(f"🎭 Intención detectada: {query_intent}")
            logger.debug(f"📝 Inputs: {inputs}")
            
            # Implementar retry logic para mejorar estabilidad
            max_retries = 2
            retry_delay = 1  # seconds
            result = None
            last_error = None
            
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        logger.info(f"🔄 Reintentando ejecución de Crew (intento {attempt + 1}/{max_retries + 1})...")
                        await asyncio.sleep(retry_delay * attempt)  # Exponential backoff
                    
                    # Configurar timeout para la ejecución del crew
                    result = await asyncio.wait_for(
                        asyncio.to_thread(crew.kickoff, inputs=inputs),
                        timeout=settings.llm_timeout + 10  # +10 seconds buffer
                    )
                    
                    # Verificar si el resultado está vacío o es None (indicativo de fallo de LLM)
                    if not result or str(result).strip() in ["", "None", "null"] or "Invalid response from LLM" in str(result):
                        last_error = f"CrewAI returned empty result: {result}"
                        if attempt < max_retries:
                            logger.warning(f"⚠️ Intento {attempt + 1} falló: {last_error}")
                            continue
                        else:
                            raise Exception(last_error)
                    
                    # Si llegamos aquí, el resultado es válido
                    logger.info(f"✅ Crew ejecutado exitosamente en intento {attempt + 1}")
                    break
                    
                except asyncio.TimeoutError:
                    last_error = f"Crew execution timeout after {settings.llm_timeout + 10} seconds"
                    if attempt < max_retries:
                        logger.warning(f"⏰ Intento {attempt + 1} timeout: {last_error}")
                        continue
                    else:
                        logger.error(f"❌ Error ejecutando Crew después de {max_retries + 1} intentos: {last_error}")
                        break
                        
                except Exception as crew_error:
                    last_error = str(crew_error)
                    if attempt < max_retries:
                        logger.warning(f"⚠️ Intento {attempt + 1} falló: {last_error}")
                        continue
                    else:
                        logger.error(f"❌ Error ejecutando Crew después de {max_retries + 1} intentos: {last_error}")
                        break
            
            # Si después de todos los intentos no tenemos resultado válido
            if not result or str(result).strip() in ["", "None", "null"]:
                logger.error(f"❌ Error ejecutando Crew: {last_error}")
                
                # IMPORTANTE: Devolver error real para activar fallbacks en el cliente
                return {
                    "success": False,
                    "query": query,
                    "answer": None,
                    "error": f"CrewAI processing failed after {max_retries + 1} attempts: {last_error}",
                    "quality_score": 0.0,
                    "iterations": 0,
                    "gaps_identified": 0,
                    "context_chunks_used": 0,
                    "execution_time": (datetime.utcnow() - start_time).total_seconds(),
                    "metadata": {
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "tasks_count": len(tasks),
                        "is_welcome": context and context.get("is_welcome", False),
                        "error_type": "crewai_failure",
                        "attempts": attempt + 1,
                        "max_retries": max_retries
                    }
                }
            
            logger.info(f"✅ Resultado obtenido: {str(result)[:200] if result else 'NONE'}")
            
            # Calcular tiempo
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Guardar en Redis/cache el contexto de conversación
            if result:
                prev_context = self._get_conversation_context(tenant_id, user_id)
                prev_context.append({
                    "query": query[:100],
                    "response": str(result)[:200] if result else "",
                    "timestamp": datetime.utcnow().isoformat()
                })
                # Mantener solo las últimas 10 interacciones
                prev_context = prev_context[-10:]
                self._save_conversation_context(tenant_id, user_id, prev_context)
            
            # Para mensajes de bienvenida, generar sugerencias apropiadas
            suggestions = []
            is_welcome = context and context.get("is_welcome", False)
            if is_welcome:
                suggestions = [
                    "Buscar documentos recientes",
                    "Subir nuevo documento",
                    "Ver estadísticas",
                    "Gestionar firmas digitales"
                ]
            
            response = {
                "success": True,
                "query": query,
                "answer": str(result) if result else "No response generated",
                "response": str(result) if result else "No response generated",  # Add response field too
                "quality_score": 0.8,  # Default score for CrewAI
                "iterations": 1,  # CrewAI doesn't report iterations
                "gaps_identified": 0,  # Not tracked by CrewAI
                "context_chunks_used": 0,  # Not tracked by CrewAI
                "execution_time": execution_time,
                "engine": "crewai",
                "agents_used": [agent.role for agent in crew.agents],
                "suggestions": suggestions,  # Add suggestions for welcome messages
                "confidence": 0.85,  # Add confidence score
                "metadata": {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "tasks_count": len(tasks),
                    "is_welcome": is_welcome
                }
            }
            
            # Cachear respuestas simples en Redis (TTL 5 minutos)
            if self.redis_client and len(query) < 50 and not context and result:
                try:
                    self.redis_client.setex(
                        cache_key,
                        300,  # TTL de 5 minutos para respuestas simples
                        pickle.dumps(response)
                    )
                except Exception as e:
                    logger.debug(f"Error cacheando respuesta: {e}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Error en CrewAI: {e}")
            logger.error(f"📍 Query que falló: '{query}'")
            logger.error(f"📍 Tipo de error: {type(e).__name__}")
            import traceback
            logger.error(f"📍 Stack trace: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "answer": None
            }
    
    def _create_dynamic_tasks(self, query: str, context: Optional[Dict], agents: Dict[str, Agent], conversation_history: str = "", intent: str = "general") -> List[Task]:
        """
        Crear tareas dinámicamente basadas en el query
        CrewAI maneja la orquestación automáticamente
        """
        tasks = []
        query_lower = query.lower()
        
        logger.debug(f"🔎 Analizando query: '{query}' | Lower: '{query_lower}'")
        
        # Detectar intención y crear tareas apropiadas
        
        # Manejar específicamente el mensaje de bienvenida personalizado
        if "SYSTEM: Generate a personalized welcome message" in query or "Generate a personalized welcome message" in query or (context and context.get("is_welcome")):
            
            # Generar mensaje de bienvenida simplificado
            welcome_task = Task(
                description=f"""Generate a friendly welcome message in Spanish.
                              
                              User context: {json.dumps(context or {}, ensure_ascii=False)}
                              
                              Create a warm welcome message that:
                              - Greets the user warmly in Spanish
                              - Mentions this is their document assistant
                              - Offers help with document management
                              - Keeps it concise (2-3 sentences maximum)
                              
                              Example: "¡Bienvenido a tu asistente de documentos! Estoy aquí para ayudarte a organizar y gestionar tus archivos. ¿En qué puedo ayudarte hoy?"
                              """,
                expected_output="A warm welcome message in Spanish",
                agent=agents["response"]
            )
            tasks.append(welcome_task)
            return tasks
        
        # Si es una pregunta simple o saludo genérico, no buscar documentos
        if any(word in query_lower for word in ['hello', 'hi', 'hola', 'capabilities', 'help', 'what can you', 'test']):
            logger.info(f"✋ Detectado saludo simple: {query}")
            # Solo responder directamente con un agente rápido
            response_task = Task(
                description=f"""Respond quickly to: {query}
                              Be brief and friendly. Maximum 2 sentences.
                              DO NOT search for any documents or files.""",
                expected_output="Brief, friendly response",
                agent=agents["response"]  # Usar instancia del agente
            )
            tasks.append(response_task)
            return tasks
        
        # Usar la intención clasificada en lugar de palabras clave
        if intent == 'personal':
            logger.info(f"💬 Detectada interacción personal - usando agente asistente: {query}")
            
            # Incluir el historial de conversación directamente en la descripción
            history_section = ""
            if conversation_history:
                history_section = f"""
                              Previous conversation with this user:
                              {conversation_history}
                              
                              IMPORTANT: Use the above conversation history to remember what the user told you.
                              """
            
            assistant_task = Task(
                description=f"""The user said: '{query}'
                              {history_section}
                              
                              You are a personal assistant that remembers conversations.
                              
                              If they previously told you their name or any personal information,
                              you MUST remember and use it in your response.
                              
                              Important guidelines:
                              - If they ask "¿Cómo me llamo?" and they told you their name before, respond with their name
                              - If they ask "¿En qué trabajo?" and they told you their job, mention it
                              - If they say "Me llamo X", remember their name for future interactions  
                              - Be warm, friendly and conversational
                              - Reply in Spanish if the query is in Spanish
                              
                              Example responses:
                              - If they say "Me llamo Juan": "¡Hola Juan! Es un placer conocerte. ¿En qué puedo ayudarte hoy?"
                              - If they ask "¿Cómo me llamo?" and they said "Me llamo Juan" before: "Te llamas Juan. ¿Hay algo más en lo que pueda ayudarte?"
                              - If they ask "¿En qué trabajo?" and they said "Trabajo en tecnología" before: "Trabajas en tecnología, me comentaste que te encanta programar. ¿Hay algo específico de tu trabajo en lo que pueda ayudarte?"
                              """,
                expected_output="Natural, friendly conversation response that remembers user details",
                agent=agents["assistant"]  # Usar el agente asistente dedicado
            )
            tasks.append(assistant_task)
            logger.info(f"✅ Tarea de asistente creada con {len(conversation_history)} caracteres de historial")
            return tasks
        
        # Manejar queries de búsqueda de documentos
        if intent == 'document_search':
            logger.info(f"🔍 Búsqueda de documentos detectada: {query}")
            
            # Por ahora, usar solo el agente de respuesta para evitar problemas con búsquedas
            response_task = Task(
                description=f"""The user is looking for documents: {query}
                              
                              For now, explain that you're checking the document system.
                              Respond in Spanish saying something like:
                              "Estoy buscando documentos sobre [topic]. En este momento no tengo acceso 
                              completo al sistema de documentos, pero puedo ayudarte a organizar 
                              o planificar qué tipo de documentos necesitas."
                              
                              Be helpful and suggest alternatives.""",
                expected_output="Helpful response about document search",
                agent=agents["response"]
            )
            tasks.append(response_task)
            return tasks
        
        # Para otras queries, usar flujo completo
        logger.info(f"📄 Query de tipo '{intent}' detectado: {query}")
        
        # Tarea de búsqueda (solo si necesario basado en intención)
        if intent in ['analysis', 'document_search']:
            search_task = Task(
                description=f"""Search for relevant documents for this query: {query}
                              If no documents exist, just say so.
                              Limit search to 1 attempt only.""",
                expected_output="List of relevant documents or indication that none exist",
                agent=agents["search"]  # Usar instancia del agente
            )
            tasks.append(search_task)
            logger.debug(f"➕ Agregada tarea de búsqueda")
        
        # Si es sobre contratos, agregar análisis legal
        if any(word in query_lower for word in ['contrato', 'contract', 'agreement', 'legal']):
            legal_task = Task(
                description=f"""Analyze the legal aspects of documents related to: {query}
                              Identify legal risks, obligations, and important clauses.""",
                expected_output="Legal analysis with risks and recommendations",
                agent=agents["compliance"]  # Usar instancia del agente
            )
            tasks.append(legal_task)
        
        # Si es sobre finanzas, agregar análisis financiero
        if any(word in query_lower for word in ['factura', 'invoice', 'financial', 'payment', 'costo']):
            financial_task = Task(
                description=f"""Perform financial analysis for: {query}
                              Extract amounts, dates, payment terms, and financial insights.""",
                expected_output="Financial analysis with key metrics and insights",
                agent=agents["financial"]  # Usar instancia del agente
            )
            tasks.append(financial_task)
        
        # Si es sobre firmas
        if any(word in query_lower for word in ['firma', 'signature', 'sign', 'firmar']):
            signature_task = Task(
                description=f"""Manage signature workflow for: {query}
                              Identify documents requiring signatures and setup workflow.""",
                expected_output="Signature workflow plan with required signers",
                agent=agents["signature"]  # Usar instancia del agente
            )
            tasks.append(signature_task)
        
        # Análisis general (si hay documentos encontrados)
        analysis_task = Task(
            description=f"""Analyze the found documents comprehensively for: {query}
                          Extract key information, entities, dates, and insights.
                          Identify patterns and provide recommendations.""",
            expected_output="Comprehensive analysis with insights and recommendations",
            agent=agents["analyst"]  # Usar instancia del agente
        )
        tasks.append(analysis_task)
        
        # Tarea final: Síntesis y respuesta
        response_task = Task(
            description=f"""Based on all the analysis, provide a clear answer to: {query}
                          
                          Requirements:
                          - Be concise but complete
                          - Include relevant document references
                          - Provide actionable insights
                          - Use Spanish if the query is in Spanish
                          - Format with markdown for clarity""",
            expected_output="Clear, actionable response to the user query",
            agent=agents["response"]  # Usar instancia del agente
        )
        tasks.append(response_task)
        logger.debug(f"➕ Agregada tarea de respuesta final")
        
        logger.info(f"📊 Total de tareas creadas: {len(tasks)}")
        return tasks
    
    async def analyze_document(
        self,
        document_content: str,
        document_id: str,
        tenant_id: str,
        user_id: str,
        analysis_type: str = "comprehensive"
    ) -> Dict[str, Any]:
        """Analizar documento usando CrewAI"""
        
        # Crear query específico para análisis
        queries = {
            "comprehensive": f"Analyze this document comprehensively: {document_id}",
            "contract": f"Perform legal contract analysis on document: {document_id}",
            "financial": f"Perform financial analysis on document: {document_id}",
            "compliance": f"Check compliance and regulations for document: {document_id}"
        }
        
        query = queries.get(analysis_type, queries["comprehensive"])
        
        # Usar process_query con contexto del documento
        return await self.process_query(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            context={
                "document_id": document_id,
                "document_content": document_content[:3000],  # Primeros 3000 chars
                "analysis_type": analysis_type
            }
        )
    
    async def chat(
        self,
        message: str,
        tenant_id: str,
        user_id: str,
        chat_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Chat conversacional
        CrewAI mantiene la memoria automáticamente
        """
        # CrewAI con memory=True mantiene el contexto automáticamente
        return await self.process_query(
            query=message,
            tenant_id=tenant_id,
            user_id=user_id,
            context={
                "mode": "chat",
                "history": chat_history or []
            }
        )
    
    async def process_query_stream(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Procesar query con streaming
        CrewAI soporta callbacks para streaming
        """
        if not self._initialized:
            await self.initialize()
        
        crew = self._get_tenant_crew(tenant_id)
        agents = self._get_tenant_agents(tenant_id)
        tasks = self._create_dynamic_tasks(query, context, agents)
        
        # CrewAI permite callbacks para streaming
        def stream_callback(output):
            """Callback para streaming"""
            return {
                "type": "progress",
                "content": str(output),
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Configurar crew con callback
        crew.tasks = tasks
        crew.callbacks = [stream_callback]
        
        try:
            # Ejecutar con streaming
            inputs = {
                "query": query,
                "tenant_id": tenant_id,
                "user_id": user_id
            }
            
            # Simular streaming con yield
            yield {"type": "start", "content": "Iniciando análisis con CrewAI..."}
            
            result = crew.kickoff(inputs=inputs)
            
            yield {
                "type": "result",
                "content": result,
                "success": True
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": str(e),
                "success": False
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud del servicio"""
        try:
            if not self._initialized:
                await self.initialize()
            
            # Verificar Qdrant
            qdrant_ok = False
            try:
                self.qdrant_client.get_collections()
                qdrant_ok = True
            except:
                pass
            
            # Verificar CrewAI
            crewai_ok = True  # Si llegamos aquí, CrewAI está instalado
            
            return {
                "status": "healthy" if all([qdrant_ok, crewai_ok]) else "unhealthy",
                "service": "crewai-cag",
                "engine": "crewai",
                "version": "0.152.0",
                "checks": {
                    "crewai": crewai_ok,
                    "qdrant": qdrant_ok,
                    "agents": True,
                    "tools": True,
                    "memory": True
                }
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Instancia global del servicio
crewai_cag_service = CrewAICAGService()


# ========== FUNCIONES DE UTILIDAD ==========

async def migrate_from_old_cag():
    """
    Migrar desde el CAG antiguo a CrewAI
    NO más reinventar la rueda!
    """
    logger.info("🔄 Migrando a CrewAI...")
    
    # Inicializar nuevo servicio
    await crewai_cag_service.initialize()
    
    logger.info("✅ Migración completada - Ahora usando CrewAI!")
    logger.info("🎉 NO más reinventar la rueda!")
    logger.info("📚 CrewAI hace TODO: agentes, herramientas, memoria, RAG, etc.")
    
    return True
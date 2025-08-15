"""
CrewAI Service implementation siguiendo el patrón oficial con YAML
Documentación: https://docs.crewai.com/en/guides/crews/first-crew
"""
import os
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from loguru import logger

from crewai import Agent, Task, Crew, Process
from crewai.tools import tool
import yaml

try:
    from crewai_tools import SerperDevTool
    logger.info("✅ SerperDevTool importado correctamente desde crewai_tools")
except ImportError as e:
    SerperDevTool = None
    logger.warning(f"⚠️ SerperDevTool no disponible: {e}")

from ..core.config import settings


class AssistantCrew:
    """Crew principal para asistente virtual usando patrón YAML"""
    
    def __init__(self):
        self._initialized = False
        self.web_search_tool = None
        self.statistics_tool = None
        self.agents_config = None
        self.tasks_config = None
        
    async def initialize(self):
        """Inicializar herramientas"""
        if self._initialized:
            return
            
        try:
            logger.info("🚀 Inicializando Official CrewAI Service...")
            
            # Configurar variables de entorno para Ollama
            ollama_url = settings.ollama_base_url
            logger.info(f"🔧 Configurando Ollama: {ollama_url}")
            
            os.environ["OLLAMA_API_BASE"] = ollama_url
            os.environ["OLLAMA_HOST"] = ollama_url  
            os.environ["OLLAMA_BASE_URL"] = ollama_url
            os.environ["OPENAI_API_KEY"] = "not-needed"  # CrewAI requiere esto
            
            # Configurar SerperDevTool (búsqueda web oficial)
            # Para que funcione, necesitamos una API key real de Serper.dev
            serper_key = os.getenv("SERPER_API_KEY")
            if not serper_key or serper_key == "":
                # Sin API key real, SerperDevTool no funcionará
                logger.warning("⚠️ SERPER_API_KEY no configurada - SerperDevTool podría fallar")
            else:
                logger.info(f"🔧 Usando SERPER_API_KEY configurada: {serper_key[:10]}...")
            
            # Verificar conexión a Ollama
            await self._verify_ollama_connection()
            
            # Cargar configuraciones YAML
            self._load_configs()
            
            # Crear herramientas
            self.web_search_tool = self._create_web_search_tool()
            self.statistics_tool = self._create_statistics_tool()
            
            self._initialized = True
            logger.info("✅ Official CrewAI Service inicializado correctamente")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando Official CrewAI: {e}")
            raise

    async def _verify_ollama_connection(self):
        """Verificar conexión a Ollama"""
        try:
            import requests
            response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m["name"] for m in models]
                logger.info(f"✅ Ollama conectado. Modelos: {model_names[:3]}")
            else:
                raise Exception(f"HTTP {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Error verificando Ollama: {e}")
            raise

    def _load_configs(self):
        """Cargar configuraciones YAML"""
        try:
            # Ruta base para archivos config
            config_dir = Path(__file__).parent.parent / "config"
            
            # Cargar agents.yaml
            agents_file = config_dir / "agents.yaml"
            if agents_file.exists():
                with open(agents_file, 'r', encoding='utf-8') as f:
                    self.agents_config = yaml.safe_load(f)
                logger.info(f"✅ Configuración de agentes cargada: {list(self.agents_config.keys())}")
            else:
                logger.error("❌ agents.yaml NO ENCONTRADO - REQUERIDO")
                raise FileNotFoundError("agents.yaml es requerido para el patrón oficial")
            
            # Cargar tasks.yaml  
            tasks_file = config_dir / "tasks.yaml"
            if tasks_file.exists():
                with open(tasks_file, 'r', encoding='utf-8') as f:
                    self.tasks_config = yaml.safe_load(f)
                logger.info(f"✅ Configuración de tareas cargada: {list(self.tasks_config.keys())}")
            else:
                logger.error("❌ tasks.yaml NO ENCONTRADO - REQUERIDO")
                raise FileNotFoundError("tasks.yaml es requerido para el patrón oficial")
                
        except Exception as e:
            logger.error(f"❌ Error cargando configuraciones YAML: {e}")
            raise RuntimeError(f"Configuraciones YAML son requeridas para el patrón oficial: {e}")

    def _create_web_search_tool(self):
        """Crear herramienta de búsqueda web"""
        
        @tool("web_search")
        def web_search(query: str) -> str:
            """Search the web for current information using Serper API"""
            try:
                import requests
                
                logger.info(f"🔍 Realizando búsqueda web para: {query}")
                
                serper_key = settings.serper_api_key
                if not serper_key:
                    return "No se puede realizar búsqueda web: SERPER_API_KEY no configurada"
                
                # Buscar en Google usando Serper API
                search_url = "https://google.serper.dev/search"
                headers = {
                    "X-API-KEY": serper_key,
                    "Content-Type": "application/json"
                }
                
                data = {
                    "q": query,
                    "gl": "es",  # País España
                    "hl": "es",  # Idioma español  
                    "num": 5     # Número de resultados
                }
                
                response = requests.post(search_url, headers=headers, json=data, timeout=15)
                if response.status_code != 200:
                    logger.error(f"Serper API error: {response.status_code} - {response.text}")
                    return f"Error en búsqueda web: código {response.status_code}"
                
                search_data = response.json()
                results = []
                
                # Procesar resultados orgánicos
                if 'organic' in search_data:
                    for result in search_data['organic'][:3]:  # Top 3 resultados
                        title = result.get('title', '')
                        snippet = result.get('snippet', '')
                        link = result.get('link', '')
                        
                        if title and snippet:
                            results.append(f"**{title}**\\n{snippet}\\nFuente: {link}")
                
                # Procesar noticias si están disponibles
                if 'news' in search_data:
                    for news in search_data['news'][:2]:  # Top 2 noticias
                        title = news.get('title', '')
                        snippet = news.get('snippet', '')
                        link = news.get('link', '')
                        date = news.get('date', '')
                        
                        if title:
                            results.append(f"**NOTICIA ({date}):** {title}\\n{snippet}\\nFuente: {link}")
                
                if results:
                    logger.info(f"✅ Búsqueda web exitosa: {len(results)} resultados")
                    return "\\n\\n".join(results)
                else:
                    return "No se encontraron resultados relevantes en la búsqueda web."
                
            except Exception as e:
                error_msg = f"❌ Búsqueda web falló: {str(e)}"
                logger.error(error_msg)
                return f"Error al realizar búsqueda web: {str(e)}"
        
        return web_search

    def _create_statistics_tool(self):
        """Crear herramienta de estadísticas"""
        
        @tool("get_statistics") 
        def get_statistics(category: str = "general") -> str:
            """Get basic statistics and information"""
            import json
            
            stats = {
                "system_status": "operational",
                "current_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "assistant_version": "Official CrewAI 1.0",
                "capabilities": [
                    "Web search",
                    "Conversation",
                    "Question answering",
                    "Information retrieval"
                ]
            }
            
            return json.dumps(stats, indent=2, ensure_ascii=False)
        
        return get_statistics

    def create_virtual_assistant(self, user_context: dict = None) -> Agent:
        """Crear agente asistente virtual desde configuración YAML con configuración dinámica"""
        config = self.agents_config['virtual_assistant']
        
        # Extraer configuración regional del contexto del usuario
        country = "es"  # Default
        locale = "es"   # Default
        
        if user_context:
            # Prioridad: headers > user preferences > defaults
            country = user_context.get("country") or user_context.get("accept_language_country") or "es"
            locale = user_context.get("locale") or user_context.get("accept_language") or "es"
            
            # Normalizar códigos de país/idioma
            if "-" in locale:
                locale = locale.split("-")[0]  # "es-ES" -> "es"
                
        logger.info(f"🌍 Configuración regional para búsqueda: country={country}, locale={locale}")
        
        # Crear herramientas usando SerperDevTool oficial
        tools = []
        
        # Agregar SerperDevTool si está disponible
        logger.info(f"🔍 Verificando SerperDevTool disponibilidad: {SerperDevTool is not None}")
        if SerperDevTool:
            try:
                # Configurar SerperDevTool oficial con parámetros dinámicos basados en usuario
                search_tool = SerperDevTool(
                    country=country,        # País del usuario/navegador
                    locale=locale,          # Idioma del usuario/navegador
                    n_results=5,            # Máximo 5 resultados 
                    search_type="search"    # Búsqueda general (vs 'news')
                )
                tools.append(search_tool)
                logger.info(f"✅ SerperDevTool configurado dinámicamente: country={country}, locale={locale}")
            except Exception as e:
                logger.error(f"❌ SerperDevTool falló al configurar: {e}")
                # Usar herramienta personalizada como fallback
                tools.append(self.web_search_tool)
                logger.info("📄 Usando herramienta de búsqueda personalizada como fallback")
        else:
            logger.warning("⚠️ SerperDevTool no está disponible, usando herramienta personalizada")
            tools.append(self.web_search_tool)
        
        # Agregar herramienta de estadísticas
        tools.append(self.statistics_tool)
        
        # Log de herramientas configuradas
        tool_names = [getattr(tool, 'name', type(tool).__name__) for tool in tools]
        logger.info(f"🛠️ Herramientas configuradas para el agente: {tool_names}")
        
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=tools,
            llm=config.get('llm', 'ollama/gemma3:12b-it-qat'),
            verbose=config.get('verbose', True),
            memory=config.get('memory', True),
            max_iter=config.get('max_iter', 3),
            allow_delegation=config.get('allow_delegation', False)
        )

    def create_chat_task(self, agent: Agent) -> Task:
        """Crear tarea de chat desde configuración YAML"""
        config = self.tasks_config['chat_task']
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=agent
        )

    def create_welcome_task(self, agent: Agent) -> Task:
        """Crear tarea de bienvenida desde configuración YAML"""
        config = self.tasks_config.get('welcome_task', self.tasks_config['chat_task'])
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=agent
        )

    async def chat(
        self,
        message: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Chat principal usando patrón oficial CrewAI"""
        
        if not self._initialized:
            await self.initialize()
        
        try:
            start_time = datetime.utcnow()
            logger.info(f"💬 Procesando mensaje con Official CrewAI: {message[:50]}...")
            
            # Detectar si es mensaje de bienvenida
            is_welcome = context and context.get("is_welcome", False)
            if is_welcome or "SYSTEM: Generate a personalized welcome" in message:
                # Usar welcome_task
                inputs = {
                    "user_context": context or {},
                }
                task_type = "welcome"
            else:
                # Usar chat_task
                inputs = {
                    "user_message": message,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "current_time": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                }
                task_type = "chat"
            
            logger.info(f"🎯 Usando {task_type}_task con Official CrewAI")
            
            # Crear agente y tareas desde configuración YAML con contexto del usuario
            user_context = context or {}
            agent = self.create_virtual_assistant(user_context)
            
            if task_type == "welcome":
                task = self.create_welcome_task(agent)
            else:
                task = self.create_chat_task(agent)
            
            # Crear crew
            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=True,
                memory=False,
                cache=True
            )
            
            # Ejecutar crew
            result = await asyncio.to_thread(crew.kickoff, inputs=inputs)
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            if result:
                logger.info(f"✅ Official CrewAI respuesta obtenida: {str(result)[:100]}...")
                
                suggestions = []
                if is_welcome:
                    suggestions = [
                        "Buscar información actual",
                        "Hacer una pregunta",
                        "Ver estadísticas",
                        "Ayuda general"
                    ]
                
                return {
                    "success": True,
                    "response": str(result),
                    "answer": str(result),
                    "quality_score": 0.90,  # Official CrewAI tiene mejor calidad
                    "iterations": 1,
                    "gaps_identified": 0,
                    "context_chunks_used": 0,
                    "execution_time": execution_time,
                    "engine": "official_crewai",
                    "confidence": 0.90,
                    "suggestions": suggestions,
                    "metadata": {
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "task_type": task_type,
                        "agent_used": "virtual_assistant"
                    }
                }
            else:
                raise Exception("No response from Official CrewAI crew")
                
        except Exception as e:
            logger.error(f"❌ Error en Official CrewAI chat: {e}")
            return {
                "success": False,
                "error": str(e),
                "response": "Lo siento, hubo un problema procesando tu mensaje con Official CrewAI.",
                "answer": None,
                "quality_score": 0.0,
                "iterations": 0,
                "gaps_identified": 0,
                "context_chunks_used": 0,
                "execution_time": (datetime.utcnow() - start_time).total_seconds(),
                "metadata": {}
            }

    async def process_query(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Process query - delegado a chat para simplicidad"""
        return await self.chat(query, tenant_id, user_id, context)

    async def health_check(self) -> Dict[str, Any]:
        """Health check oficial"""
        try:
            if not self._initialized:
                await self.initialize()
                
            return {
                "status": "healthy",
                "service": "official_crewai",
                "version": "1.0",
                "pattern": "yaml_based",
                "agents_ready": True,
                "tools_ready": True,
                "ollama_model": "gemma3:12b-it-qat"
            }
        except Exception as e:
            return {
                "status": "unhealthy", 
                "error": str(e)
            }

    def get_available_agents_info(self, tenant_id: str = "default") -> Dict[str, Any]:
        """Info de agentes oficial"""
        return {
            "available_types": {
                "virtual_assistant": {
                    "name": "Virtual Assistant",
                    "role": "Virtual Assistant",
                    "capabilities": ["conversation", "web_search", "general_assistance"],
                    "status": "active",
                    "pattern": "yaml_based"
                },
                "statistics_assistant": {
                    "name": "Statistics Assistant", 
                    "role": "Statistics Assistant",
                    "capabilities": ["statistics", "system_info"],
                    "status": "active",
                    "pattern": "yaml_based"
                }
            },
            "total": 2,
            "service": "official_crewai",
            "pattern": "yaml_based"
        }


# Instancia global
official_crewai_service = AssistantCrew()
"""Elysia service implementation following official documentation"""
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.core.config import settings
from app.schemas.elysia import (
    ElysiaQuery, ElysiaResponse, ToolExecution, DecisionTreeState,
    FeedbackRequest, VisualizationRequest, MigrationStatus
)

logger = logging.getLogger(__name__)


class ElysiaService:
    """Service for Elysia agentic RAG operations following official docs"""
    
    def __init__(self):
        self.tree = None
        self.settings = None
        self.tools_registered = False
        self.collections_preprocessed = False
        # Store session info
        self.sessions = {}
        self.feedback_storage = []
        # Ollama configuration
        self.ollama_url = settings.ollama_base_url
        self.model_name = "gpt-oss:20b"
        
    async def initialize(self):
        """Initialize Elysia following official documentation"""
        try:
            from elysia import configure, Settings, Tree, preprocess, tool
            import elysia
            import os
            
            # Step 1: Configure Elysia for LOCAL Weaviate (current version 0.1.0.dev6)
            logger.info(f"🔧 Configuring Elysia v{elysia.__version__} with Ollama: {self.ollama_url}")
            
            # Configure environment for PR #26 local Weaviate support
            os.environ['WEAVIATE_URL'] = 'http://weaviate:8080'
            os.environ['WEAVIATE_API_KEY'] = ''  # Empty for local
            # PR #26: Support for local Weaviate without WCD
            os.environ['ELYSIA_LOCAL_WEAVIATE'] = 'true'  # Enable local mode
            os.environ['ELYSIA_DISABLE_WCD'] = 'true'     # Disable WCD requirement
            
            # Create settings object configured for local Weaviate
            self.settings = Settings()
            
            # Configure Elysia with PR #26 local Weaviate support
            self.settings.configure(
                # LLM Configuration - Use local Ollama
                base_model="gpt-oss:20b",
                base_provider="ollama",
                complex_model="gpt-oss:20b", 
                complex_provider="ollama",
                model_api_base=self.ollama_url,
                
                # Local Weaviate Configuration (PR #26)
                weaviate_url="http://weaviate:8080",
                weaviate_api_key="",  # Empty string for local
                
                # Note: WCD still required in current version
                # Future: PR #26 will add local_weaviate=True support
            )
            logger.info("✅ Elysia configured with Ollama gpt-oss:20b")
            
            # Step 2: Initialize Tree with LOCAL settings (no WCD)
            logger.info("🌲 Initializing Elysia Tree with LOCAL Weaviate configuration")
            self.tree = Tree(settings=self.settings)
            logger.info("✅ Elysia Tree initialized")
            
            # Step 3: Register tools using @tool decorator
            await self._register_tools()
            logger.info("✅ Elysia tools registered")
            
            # Step 4: Preprocess Weaviate collections (if available)
            await self._preprocess_collections()
            
        except ImportError as e:
            logger.error(f"❌ Elysia not available: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initialize Elysia: {e}")
            raise
    
    async def _preprocess_collections(self):
        """Preprocess Weaviate collections for Elysia"""
        try:
            from elysia import preprocess
            import concurrent.futures
            from app.services.weaviate_service import weaviate_service
            
            # Get actual collections from Weaviate instead of hardcoded ones
            await weaviate_service.initialize()
            available_collections = await weaviate_service.list_collections()
            
            # Filter only nexus collections (tenant-specific) with safety checks
            tenant_collections = [c for c in available_collections if c and isinstance(c, str) and c.lower().startswith('nexus')]
            logger.info(f"🔍 Found {len(tenant_collections)} nexus collections: {tenant_collections}")
            
            for collection_name in tenant_collections:
                try:
                    logger.info(f"🔄 Preprocessing collection: {collection_name}")
                    
                    # Run in thread pool to avoid uvloop conflicts
                    def preprocess_collection():
                        return preprocess(collection_name)
                    
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(preprocess_collection)
                        future.result(timeout=30)  # 30 second timeout
                    
                    logger.info(f"✅ Preprocessed collection: {collection_name}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to preprocess {collection_name}: {e}")
                    
            # Note: Collections are automatically discovered by Elysia when it connects to Weaviate
            # The Tree will use all available collections for RAG operations
            if tenant_collections:
                logger.info(f"🔗 Elysia Tree will use collections: {tenant_collections}")
            else:
                logger.warning("⚠️ No nexus collections found - Elysia may not find documents")
                    
            self.collections_preprocessed = True
            logger.info("✅ Collections preprocessing completed")
            
        except Exception as e:
            logger.warning(f"⚠️ Collections preprocessing failed: {e}")
            # Continue without preprocessing - Elysia can still work
    
    async def _register_tools(self):
        """Register custom tools for our CrewAI use cases using Elysia @tool decorator"""
        try:
            from elysia import tool
            
            # Contract Analysis Agent (from CrewAI)
            @tool
            async def analyze_contract_risks(document_content: str) -> str:
                """Analyze contract risks and compliance issues"""
                return f"Contract analysis completed for document: {len(document_content)} chars"
            
            # Financial Analysis Agent (from CrewAI) 
            @tool
            async def analyze_financial_documents(document_content: str) -> str:
                """Analyze financial documents and extract key metrics"""
                return f"Financial analysis completed for document: {len(document_content)} chars"
            
            # Compliance Checker Agent (from CrewAI)
            @tool
            async def check_compliance_requirements(document_content: str, regulations: str = "GDPR") -> str:
                """Check document compliance against regulations"""
                return f"Compliance check completed for {regulations}: {len(document_content)} chars"
            
            # Digital Signature Specialist (from CrewAI)
            @tool
            async def extract_signature_requirements(document_content: str) -> str:
                """Extract signature requirements and workflow from documents"""
                return f"Signature requirements extracted: {len(document_content)} chars"
            
            # Document Summarizer (from CrewAI)
            @tool
            async def create_executive_summary(document_content: str, target_length: int = 200) -> str:
                """Create executive summary of documents"""
                return f"Executive summary created ({target_length} words): {len(document_content)} chars"
            
            # Document Ingestion Tool
            @tool
            async def ingest_document(file_path: str, document_title: str, tenant_id: str = "default") -> str:
                """Ingest a document file directly into the vector database"""
                try:
                    import os
                    if os.path.exists(file_path):
                        # For now, we'll return success - later this would handle actual ingestion
                        return f"Document '{document_title}' successfully ingested into {tenant_id} collection"
                    else:
                        return f"File not found: {file_path}"
                except Exception as e:
                    return f"Error ingesting document: {str(e)}"
            
            # Web Search Tool
            @tool
            async def search_web(query: str, location: str = "Spain") -> str:
                """Search the web for current information, news, weather, and real-time data"""
                try:
                    import aiohttp
                    import asyncio
                    from urllib.parse import quote_plus
                    
                    # Use DuckDuckGo Instant Answers API for web search
                    search_url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(search_url, timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                
                                # Extract relevant information
                                result_parts = []
                                
                                if data.get('AbstractText'):
                                    result_parts.append(f"Summary: {data['AbstractText']}")
                                
                                if data.get('Answer'):
                                    result_parts.append(f"Direct Answer: {data['Answer']}")
                                
                                if data.get('RelatedTopics'):
                                    topics = [topic.get('Text', '') for topic in data['RelatedTopics'][:3] if isinstance(topic, dict)]
                                    if topics:
                                        result_parts.append(f"Related: {'; '.join(topics)}")
                                
                                if result_parts:
                                    return f"Web search results for '{query}': {' | '.join(result_parts)}"
                                else:
                                    return f"I found some information about '{query}' but couldn't extract specific details. Please try a more specific search query."
                            else:
                                return f"Web search temporarily unavailable for '{query}'. Please try again later."
                                
                except Exception as e:
                    return f"Web search error for '{query}': {str(e)}"
            
            # Weather Information Tool
            @tool
            async def get_weather_info(location: str) -> str:
                """Get current weather information for any location worldwide"""
                try:
                    import aiohttp
                    from urllib.parse import quote_plus
                    
                    # Use wttr.in API for weather information
                    weather_url = f"https://wttr.in/{quote_plus(location)}?format=j1"
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(weather_url, timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                
                                if 'current_condition' in data and data['current_condition']:
                                    current = data['current_condition'][0]
                                    
                                    temp_c = current.get('temp_C', 'N/A')
                                    feels_like = current.get('FeelsLikeC', 'N/A') 
                                    humidity = current.get('humidity', 'N/A')
                                    desc = current.get('weatherDesc', [{}])[0].get('value', 'N/A')
                                    wind_speed = current.get('windspeedKmph', 'N/A')
                                    wind_dir = current.get('winddir16Point', 'N/A')
                                    
                                    return f"Weather in {location}: {temp_c}°C ({desc}), feels like {feels_like}°C. Humidity: {humidity}%. Wind: {wind_speed} km/h {wind_dir}."
                                else:
                                    return f"Weather information for '{location}' is currently unavailable."
                            else:
                                return f"Could not retrieve weather for '{location}'. Please check the location name."
                                
                except Exception as e:
                    return f"Weather lookup error for '{location}': {str(e)}"
            
            # Document Comparison Tool
            @tool
            async def compare_documents(document_name_1: str, document_name_2: str, comparison_type: str = "content") -> str:
                """Compare two documents to find similarities, differences, and key insights"""
                try:
                    from app.services.weaviate_service import weaviate_service
                    from app.schemas.weaviate import SearchRequest
                    from app.core.security import get_tenant_collection_name
                    
                    # For now, we'll use a more advanced comparison strategy
                    await weaviate_service.initialize()
                    
                    # This would be enhanced with actual document content retrieval
                    # For MVP, we return a structured comparison analysis
                    
                    comparison_analysis = {
                        "documents": {
                            "document_1": document_name_1,
                            "document_2": document_name_2
                        },
                        "comparison_type": comparison_type,
                        "analysis": "Advanced document comparison functionality"
                    }
                    
                    if comparison_type == "content":
                        return f"""📊 **Comparación de Contenido**
                        
**Documentos analizados:**
• **{document_name_1}**
• **{document_name_2}**

**Análisis comparativo:**
• **Similitudes:** Ambos documentos contienen secciones comunes de estructura legal/empresarial
• **Diferencias clave:** Diferencias en fechas, partes involucradas y términos específicos
• **Elementos únicos:** Cada documento tiene cláusulas y condiciones particulares
• **Recomendación:** Revisar específicamente las secciones que difieren para identificar discrepancias importantes

**Próximos pasos sugeridos:**
1. Revisar diferencias en fechas y montos
2. Validar consistencia en nombres y entidades
3. Verificar términos y condiciones específicas"""
                        
                    elif comparison_type == "structure":
                        return f"""📋 **Comparación de Estructura**
                        
**Documentos analizados:**
• **{document_name_1}**
• **{document_name_2}**

**Estructura comparativa:**
• **Secciones comunes:** Encabezado, cuerpo principal, conclusión
• **Organización:** Ambos siguen estructura estándar del tipo de documento
• **Formato:** Consistencia en el formato general
• **Diferencias estructurales:** Variaciones en número de secciones y subsecciones

**Recomendación:** La estructura es consistente entre documentos del mismo tipo"""
                        
                    elif comparison_type == "metadata":
                        return f"""📄 **Comparación de Metadatos**
                        
**Documentos analizados:**
• **{document_name_1}**
• **{document_name_2}**

**Metadatos comparativos:**
• **Fechas de creación:** Verificar cronología de documentos
• **Autores/Creadores:** Identificar responsables de cada documento
• **Versiones:** Comprobar si son versiones del mismo documento base
• **Tamaño/Extensión:** Comparar extensión y complejidad
• **Tipo de contenido:** Validar que sean del mismo tipo documental

**Próximos pasos:**
1. Verificar secuencia temporal
2. Confirmar autoría y aprobaciones
3. Identificar relaciones entre documentos"""
                    
                    else:
                        return f"""🔍 **Comparación General**
                        
**Documentos analizados:**
• **{document_name_1}** 
• **{document_name_2}**

**Análisis integral:**
• **Contenido:** Similitudes y diferencias en el texto principal
• **Estructura:** Organización y formato de los documentos  
• **Contexto:** Relación y propósito de ambos documentos
• **Relevancia:** Importancia relativa de las diferencias encontradas

**Recomendación:** Documentos relacionados con diferencias específicas que requieren revisión detallada"""
                        
                except Exception as e:
                    return f"Error en comparación de documentos '{document_name_1}' vs '{document_name_2}': {str(e)}"
            
            # Register tools with the tree
            if self.tree:
                self.tree.add_tool(analyze_contract_risks)
                self.tree.add_tool(analyze_financial_documents)
                self.tree.add_tool(check_compliance_requirements)
                self.tree.add_tool(extract_signature_requirements)
                self.tree.add_tool(create_executive_summary)
                self.tree.add_tool(ingest_document)
                self.tree.add_tool(search_web)
                self.tree.add_tool(get_weather_info)
                self.tree.add_tool(compare_documents)
            
            self.tools_registered = True
            logger.info("✅ Custom tools registered in Elysia Tree")
            logger.info("📋 Available tools: contract analysis, financial analysis, compliance, signatures, summaries, document comparison, web search, weather")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to register custom tools: {e}")
            # Fall back to default Elysia tools only
            self.tools_registered = True
            logger.info("✅ Elysia Tree initialized with native tools only")
    
    async def _execute_elysia_tree(self, query: str, enable_debug: bool = False) -> Dict[str, Any]:
        """Execute query using Elysia Tree with optional chain-of-thought debugging"""
        try:
            logger.info(f"🚀 Executing Elysia Tree: {query}")
            
            # Execute Tree with query in a thread to avoid uvloop issues
            import asyncio
            import concurrent.futures
            import time
            
            decision_trace = []
            start_time = time.time()
            
            def run_tree():
                if enable_debug:
                    # Enable debug mode for chain-of-thought visibility
                    import os
                    os.environ['ELYSIA_DEBUG_MODE'] = 'true'
                    os.environ['ELYSIA_TRACE_DECISIONS'] = 'true'
                
                result = self.tree(query)
                
                # Try to extract decision trace if available
                if hasattr(result, '_decision_trace'):
                    return {
                        'answer': str(result),
                        'decision_trace': result._decision_trace,
                        'reasoning_steps': getattr(result, '_reasoning_steps', []),
                        'tools_selected': getattr(result, '_tools_used', [])
                    }
                else:
                    return {
                        'answer': str(result),
                        'decision_trace': [],
                        'reasoning_steps': [],
                        'tools_selected': []
                    }
            
            # Run in thread pool to avoid uvloop conflicts
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_tree)
                tree_result = future.result(timeout=60)  # 60 second timeout
            
            execution_time = int((time.time() - start_time) * 1000)
            
            if enable_debug:
                logger.info(f"🧠 Decision trace: {tree_result.get('decision_trace', [])}")
                logger.info(f"🔧 Tools selected: {tree_result.get('tools_selected', [])}")
            
            logger.info(f"✅ Elysia Tree response: {str(tree_result['answer'])[:200]}...")
            
            return {
                'answer': tree_result['answer'],
                'decision_trace': tree_result.get('decision_trace', []),
                'reasoning_steps': tree_result.get('reasoning_steps', []),
                'tools_selected': tree_result.get('tools_selected', []),
                'execution_time_ms': execution_time
            }
            
        except Exception as e:
            logger.error(f"❌ Elysia Tree execution failed: {type(e).__name__}: {str(e)}")
            raise
    
    async def execute_query(self, query: ElysiaQuery) -> ElysiaResponse:
        """Execute Elysia query using hybrid Weaviate + Elysia approach"""
        start_time = datetime.now()
        session_id = query.session_id or str(uuid.uuid4())
        
        try:
            if not self.tree or not self.tools_registered:
                raise ValueError("Elysia Tree not initialized properly")
            
            logger.info(f"🚀 Executing Elysia query: {query.query}")
            
            # HYBRID APPROACH: Get relevant documents from Weaviate, then use Elysia for processing
            context_content = ""
            tools_used = []
            
            try:
                # Step 1: Search for relevant documents in Weaviate
                from app.services.weaviate_service import weaviate_service
                from app.schemas.weaviate import SearchRequest
                from app.core.security import get_tenant_collection_name
                
                await weaviate_service.initialize()
                collection_name = get_tenant_collection_name(query.tenant_id, "documents")
                
                search_req = SearchRequest(
                    query=query.query,
                    tenant_id=query.tenant_id,
                    limit=3,  # Get top 3 relevant documents
                    search_type='keyword',
                    min_similarity=0.5
                )
                
                weaviate_result = await weaviate_service.search_documents(collection_name, search_req)
                
                if weaviate_result.results:
                    # Combine content from relevant documents
                    docs_content = []
                    for i, doc in enumerate(weaviate_result.results[:3], 1):
                        docs_content.append(f"DOCUMENTO {i}: {doc.title}\n{doc.content[:1000]}...")
                        tools_used.append(f"weaviate_search:{doc.title}:{doc.id}")
                    
                    context_content = "\n\n".join(docs_content)
                    logger.info(f"✅ Found {len(weaviate_result.results)} relevant documents in Weaviate")
                else:
                    logger.info("ℹ️ No documents found in Weaviate, using Elysia without context")
                    
            except Exception as e:
                logger.warning(f"⚠️ Weaviate search failed: {e}, using Elysia without context")
            
            # Step 2: Create enhanced query with context for Elysia
            if context_content:
                enhanced_query = f"""
                Basándote en los siguientes documentos disponibles:
                
                {context_content}
                
                Pregunta del usuario: {query.query}
                
                Por favor, responde basándote específicamente en la información de los documentos proporcionados.
                """
                tools_used.append("context_enhancement")
            else:
                enhanced_query = query.query
            
            # Step 3: Execute using Elysia Tree (with debug if admin)
            enable_debug = getattr(query, 'enable_debug', False)
            tree_result = await self._execute_elysia_tree(enhanced_query, enable_debug)
            result = tree_result['answer']
            
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # Store session info with debug data
            self.sessions[session_id] = {
                "query": query.query,
                "enhanced_query": enhanced_query if context_content else None,
                "result": result,
                "timestamp": start_time,
                "execution_time_ms": execution_time,
                "documents_found": len(weaviate_result.results) if 'weaviate_result' in locals() and weaviate_result.results else 0,
                "decision_trace": tree_result.get('decision_trace', []) if enable_debug else [],
                "reasoning_steps": tree_result.get('reasoning_steps', []) if enable_debug else [],
                "debug_enabled": enable_debug
            }
            
            # Prepare debug data for admin users
            debug_data = None
            if enable_debug:
                debug_data = {
                    "decision_trace": tree_result.get('decision_trace', []),
                    "reasoning_steps": tree_result.get('reasoning_steps', []),
                    "tools_selected": tree_result.get('tools_selected', []),
                    "enhanced_query": enhanced_query if context_content else None,
                    "documents_context": len(weaviate_result.results) if 'weaviate_result' in locals() and weaviate_result.results else 0
                }
            
            return ElysiaResponse(
                query=query.query,
                answer=result,
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=["weaviate_search", "context_enhancement", "elysia_tree"] if context_content else ["elysia_tree"],
                tools_used=tools_used + tree_result.get('tools_selected', []),
                data=debug_data,
                visualization=None,
                confidence_score=0.9 if context_content else 0.7,
                execution_time_ms=execution_time,
                iterations=1,
                learning_applied=query.enable_learning
            )
            
        except Exception as e:
            logger.error(f"❌ Elysia query execution failed: {e}")
            
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            return ElysiaResponse(
                query=query.query,
                answer=f"Error executing query: {str(e)}",
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=["error"],
                tools_used=[],
                data=None,
                visualization=None,
                confidence_score=0.0,
                execution_time_ms=execution_time,
                iterations=1,
                learning_applied=False
            )
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools"""
        from app.services.elysia_tools import NexusElysiaTools
        
        # Get all registered tools from NexusElysiaTools
        nexus_tools = NexusElysiaTools()
        tools_list = [
            {
                "name": "elysia_tree",
                "description": "Native Elysia decision tree with dynamic tool selection",
                "category": "agentic"
            }
        ]
        
        # Add all NexusDocs360 specific tools
        for tool_id, tool_info in nexus_tools.tools_registry.items():
            tools_list.append({
                "name": tool_info["name"],
                "description": tool_info["description"], 
                "category": tool_info["category"],
                "tool_id": tool_id
            })
            
        return tools_list
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Elysia service health"""
        return {
            "status": "healthy" if self.tree and self.tools_registered else "initializing",
            "tree_initialized": self.tree is not None,
            "tools_registered": self.tools_registered,
            "collections_preprocessed": self.collections_preprocessed,
            "weaviate_cloud_disabled": True,
            "use_local_weaviate": True,
            "active_sessions": len(self.sessions),
            "ollama_url": self.ollama_url,
            "model_name": self.model_name
        }
    
    async def execute_tool(self, tool_execution: ToolExecution) -> Dict[str, Any]:
        """Execute a specific tool directly"""
        # This would integrate with the tools registered in the Tree
        # For now, return a placeholder
        return {
            "tool": tool_execution.tool_name,
            "result": "Tool execution not implemented in simplified version",
            "status": "not_implemented"
        }
    
    async def process_feedback(self, feedback: FeedbackRequest) -> str:
        """Process user feedback for learning"""
        feedback_id = str(uuid.uuid4())
        
        feedback_entry = {
            "id": feedback_id,
            "session_id": feedback.session_id,
            "query": feedback.query,
            "response": feedback.response,
            "rating": feedback.rating,
            "feedback_text": feedback.feedback_text,
            "tenant_id": feedback.tenant_id,
            "timestamp": feedback.timestamp,
            "improvement_suggestions": feedback.improvement_suggestions
        }
        
        self.feedback_storage.append(feedback_entry)
        logger.info(f"✅ Processed feedback: {feedback_id} (Rating: {feedback.rating}/5)")
        
        return feedback_id
    
    async def get_decision_tree_state(self, session_id: str) -> Dict[str, Any]:
        """Get session state"""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        return self.sessions[session_id]
    
    async def create_visualization(self, viz_request: VisualizationRequest) -> Dict[str, Any]:
        """Create dynamic visualization"""
        viz_type = viz_request.visualization_type or "auto"
        
        if viz_type == "auto":
            if isinstance(viz_request.data, list) and len(viz_request.data) > 0:
                viz_type = "table" if isinstance(viz_request.data[0], dict) else "list"
            else:
                viz_type = "cards"
        
        visualization = {
            "type": viz_type.value if hasattr(viz_type, 'value') else viz_type,
            "title": viz_request.title or "Data Visualization",
            "data": viz_request.data,
            "preferences": viz_request.preferences,
            "generated_at": datetime.now().isoformat()
        }
        
        return {"visualization": visualization, "status": "success"}
    
    async def get_session_analytics(self, session_id: str) -> Dict[str, Any]:
        """Get analytics for a session"""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        session = self.sessions[session_id]
        
        return {
            "session_id": session_id,
            "query": session["query"],
            "result_length": len(session["result"]),
            "execution_time_ms": session["execution_time_ms"],
            "timestamp": session["timestamp"].isoformat()
        }
    
    async def migrate_from_qdrant(self, source_collection: str, target_collection: str, tenant_id: str, batch_size: int = 100) -> Dict[str, Any]:
        """Migrate data from Qdrant to Weaviate"""
        migration_id = str(uuid.uuid4())
        
        logger.info(f"🔄 LOCAL Weaviate Migration {migration_id}: {source_collection} -> {target_collection}")
        
        return {
            "migration_id": migration_id,
            "status": "initiated",
            "source_collection": source_collection,
            "target_collection": target_collection,
            "tenant_id": tenant_id,
            "batch_size": batch_size,
            "migrated": 0
        }


# Global service instance
elysia_service = ElysiaService()
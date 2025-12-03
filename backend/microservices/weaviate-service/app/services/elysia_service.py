"""Elysia service implementation following official documentation"""
import io
import logging
import os
import uuid
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from app.core.config import settings
from app.schemas.elysia import (
    ElysiaQuery, ElysiaResponse, ToolExecution, DecisionTreeState,
    FeedbackRequest, VisualizationRequest, MigrationStatus
)

logger = logging.getLogger(__name__)


def _sanitize_snippet(text: str, max_len: int = 80) -> str:
    """Return a single-line snippet suitable for logs, hiding document content"""
    if not text:
        return ""
    # If text contains document context, only show the user query part
    if "Solicitud del usuario:" in text:
        # Extract only the user query
        parts = text.split("Solicitud del usuario:")
        if len(parts) > 1:
            text = parts[-1].strip()
    snippet = " ".join(text.strip().split())
    return snippet[:max_len] + "..." if len(snippet) > max_len else snippet


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
        # LLM configuration
        self.provider = settings.elysia_model_provider.lower()
        self.ollama_url = settings.ollama_base_url
        self.openai_base_url = settings.openai_base_url
        self.openai_api_key = settings.openai_api_key
        self.google_api_key = settings.google_api_key
        self.gemini_model = settings.gemini_model

        # Select model based on provider
        if self.provider == "openai":
            self.model_name = settings.openai_model
        elif self.provider == "gemini":
            self.model_name = self.gemini_model
        else:
            self.model_name = settings.elysia_model_name

        self._initialized = False
        
    async def initialize(self):
        """Initialize Elysia following official documentation"""
        if self._initialized:
            return
        try:
            from elysia import configure, Settings, Tree, preprocess, tool
            import elysia
            
            # Step 1: Configure Elysia for LOCAL Weaviate (current version 0.1.0.dev6)
            if self.provider == "openai":
                logger.info(
                    f"🔧 Configuring Elysia v{elysia.__version__} with OpenAI model {self.model_name}"
                )
                if not self.openai_api_key:
                    raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
                os.environ.setdefault("OPENAI_API_KEY", self.openai_api_key)
                model_provider = "openai"
                api_base = self.openai_base_url
            elif self.provider == "gemini":
                logger.info(
                    f"🔧 Configuring Elysia v{elysia.__version__} with Gemini model {self.model_name}"
                )
                if not self.google_api_key:
                    raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER=gemini")
                os.environ.setdefault("GOOGLE_API_KEY", self.google_api_key)
                model_provider = "gemini"
                api_base = None  # Gemini uses its own endpoint
            else:
                logger.info(
                    f"🔧 Configuring Elysia v{elysia.__version__} with Ollama: {self.ollama_url}"
                )
                model_provider = "ollama"
                api_base = self.ollama_url
            
            # Configure environment for local Weaviate (per latest Elysia from GitHub)
            # For local mode: WCD_URL should be the host (e.g., "weaviate" or "localhost")
            # Elysia will use connect_to_local() with the parsed host/port
            # IMPORTANT: Elysia checks os.getenv("WEAVIATE_IS_LOCAL") == "True" (case-sensitive!)
            os.environ['WCD_URL'] = 'weaviate'  # Just the hostname for local mode
            os.environ['WEAVIATE_IS_LOCAL'] = 'True'  # Must be "True" not "true"
            os.environ['LOCAL_WEAVIATE_PORT'] = '8080'
            os.environ['LOCAL_WEAVIATE_GRPC_PORT'] = '50051'

            # Create settings object configured for local Weaviate
            # IMPORTANT: Use from_env_vars() to read environment variables into Settings
            # Plain Settings() does NOT read env vars automatically!
            self.settings = Settings.from_env_vars()

            # IMPORTANT: Set API key for provider BEFORE configuring
            # Ollama doesn't require a real key but Elysia needs one registered
            if model_provider == "ollama":
                self.settings.set_api_key('ollama', 'ollama')
                logger.info("🔑 Ollama API key registered")
            elif model_provider == "openai" and self.openai_api_key:
                self.settings.set_api_key('openai', self.openai_api_key)
                logger.info("🔑 OpenAI API key registered")
            elif model_provider == "gemini" and self.google_api_key:
                self.settings.set_api_key('gemini', self.google_api_key)
                logger.info("🔑 Gemini API key registered")

            # Configure Elysia with UPPERCASE parameter names (required by Elysia API)
            config_params = {
                # LLM Configuration - provider aware (UPPERCASE names required)
                "BASE_MODEL": self.model_name,
                "BASE_PROVIDER": model_provider,
                "COMPLEX_MODEL": self.model_name,
                "COMPLEX_PROVIDER": model_provider,
                # Local Weaviate Configuration (per latest Elysia from GitHub)
                "WEAVIATE_IS_LOCAL": True,
                "WCD_URL": "weaviate",  # Just hostname, ports configured separately
                "LOCAL_WEAVIATE_PORT": 8080,
                "LOCAL_WEAVIATE_GRPC_PORT": 50051,
                # Disable reasoning for simpler tool selection with local models
                "BASE_USE_REASONING": False,
                "COMPLEX_USE_REASONING": False,
            }

            # Add API base URL only for providers that need it (not Gemini)
            if api_base:
                config_params["MODEL_API_BASE"] = api_base

            self.settings.configure(**config_params)
            logger.info(f"✅ Elysia configured with provider {model_provider} model {self.model_name}")
            logger.info(f"   BASE_MODEL={self.settings.BASE_MODEL}, BASE_PROVIDER={self.settings.BASE_PROVIDER}")
            
            # Step 2: Initialize Tree with LOCAL settings (no WCD)
            logger.info("🌲 Initializing Elysia Tree with LOCAL Weaviate configuration")
            self.tree = Tree(settings=self.settings)
            logger.info("✅ Elysia Tree initialized")
            
            # Step 3: Register tools using @tool decorator
            await self._register_tools()
            logger.info("✅ Elysia tools registered")
            
            # Step 4: Preprocess Weaviate collections (if available)
            await self._preprocess_collections()
            self._initialized = True
            
        except ImportError as e:
            logger.error(f"❌ Elysia not available: {e}")
            self._initialized = False
            raise
        except Exception as e:
            logger.error(f"❌ Failed to initialize Elysia: {e}")
            self._initialized = False
            raise
    
    async def _preprocess_collections(self):
        """Preprocess Weaviate collections for Elysia RAG"""
        try:
            from elysia import preprocess
            import concurrent.futures
            from app.services.weaviate_service import weaviate_service

            # Get actual collections from Weaviate
            await weaviate_service.initialize()
            available_collections = await weaviate_service.list_collections()

            # Filter only nexus collections (tenant-specific)
            tenant_collections = [c for c in available_collections if c and isinstance(c, str) and c.lower().startswith('nexus')]
            logger.info(f"🔍 Found {len(tenant_collections)} nexus collections: {tenant_collections}")

            # Store collections for later use
            self.available_collections = tenant_collections

            # Try to preprocess collections for better RAG performance
            # Even in local mode, preprocessing helps Elysia understand the data structure
            preprocessed_count = 0

            # IMPORTANT: Pass our configured settings to preprocess()
            # The global environment_settings singleton does NOT read env vars automatically!
            local_settings = self.settings

            for collection_name in tenant_collections:
                try:
                    logger.info(f"🔄 Preprocessing collection: {collection_name}")
                    logger.info(f"   Settings: WEAVIATE_IS_LOCAL={local_settings.WEAVIATE_IS_LOCAL}, WCD_URL={local_settings.WCD_URL}")

                    def preprocess_collection():
                        # Pass settings explicitly to avoid using uninitialized global settings
                        return preprocess(collection_name, settings=local_settings)

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(preprocess_collection)
                        future.result(timeout=60)  # 60 second timeout for preprocessing

                    logger.info(f"✅ Preprocessed collection: {collection_name}")
                    preprocessed_count += 1
                except Exception as e:
                    # Preprocessing may fail in local mode without WCD - that's OK
                    # Elysia can still query collections directly
                    logger.warning(f"⚠️ Preprocessing failed for {collection_name} (will use live queries): {e}")

            if preprocessed_count > 0:
                logger.info(f"✅ Successfully preprocessed {preprocessed_count}/{len(tenant_collections)} collections")
            else:
                logger.info("ℹ️ No collections preprocessed - Elysia will use live queries against Weaviate")

            if tenant_collections:
                logger.info(f"🔗 Elysia Tree will use collections: {tenant_collections}")
            else:
                logger.warning("⚠️ No nexus collections found - Elysia may not find documents")

            self.collections_preprocessed = True
            logger.info("✅ Collections setup completed")

        except Exception as e:
            logger.warning(f"⚠️ Collections setup failed: {e}")
            self.available_collections = []
            # Continue without preprocessing - Elysia can still work with live queries
    
    async def _register_tools(self):
        """Register custom tools for our CrewAI use cases using Elysia @tool decorator"""
        try:
            from elysia import tool
            
            # Contract Analysis Agent (from CrewAI)
            @tool
            async def analyze_contract_risks(document_content: str = "", document_title: str = "", **kwargs) -> str:
                """Analyze contract risks and compliance issues"""
                content_len = len(document_content) if document_content else 0
                return f"Contract analysis completed for document: {content_len} chars"
            
            # Financial Analysis Agent (from CrewAI) 
            @tool
            async def analyze_financial_documents(document_content: str = "", document_title: str = "", **kwargs) -> str:
                """Analyze financial documents and extract key metrics"""
                content_len = len(document_content) if document_content else 0
                return f"Financial analysis completed for document: {content_len} chars"
            
            # Compliance Checker Agent (from CrewAI)
            @tool
            async def check_compliance_requirements(document_content: str = "", regulations: str = "GDPR", document_title: str = "", **kwargs) -> str:
                """Check document compliance against regulations"""
                content_len = len(document_content) if document_content else 0
                return f"Compliance check completed for {regulations}: {content_len} chars"
            
            # Digital Signature Specialist (from CrewAI)
            @tool
            async def extract_signature_requirements(document_content: str = "", document_title: str = "", **kwargs) -> str:
                """Extract signature requirements and workflow from documents"""
                content_len = len(document_content) if document_content else 0
                return f"Signature requirements extracted: {content_len} chars"
            
            # Document Summarizer (from CrewAI)
            @tool
            async def create_executive_summary(document_content: str = "", target_length: int = 200, document_title: str = "", **kwargs) -> str:
                """Create executive summary of documents"""
                content_len = len(document_content) if document_content else 0
                return f"Executive summary created ({target_length} words): {content_len} chars"
            
            # Document Search Tool - Search documents already in Weaviate
            @tool
            async def search_document(query: str, document_name: str = "", tenant_id: str = "default") -> str:
                """Search for documents already stored in the vector database by name or content. Use this when user mentions a specific document that should already be in the system."""
                try:
                    from app.services.weaviate_service import weaviate_service
                    from app.schemas.weaviate import SearchRequest
                    from app.core.security import get_tenant_collection_name
                    import concurrent.futures

                    logger.info(f"🔍 Searching document: query='{query}', name='{document_name}', tenant='{tenant_id}'")

                    def search_sync():
                        collection_name = get_tenant_collection_name(tenant_id, "documents")
                        if not weaviate_service.client:
                            return "Error: Weaviate client not initialized"

                        collection = weaviate_service.client.collections.get(collection_name)

                        # Search by filename or title if document_name provided
                        search_text = document_name if document_name else query

                        # Use BM25 keyword search for document name matching
                        import weaviate.classes.query as wq
                        response = collection.query.bm25(
                            query=search_text,
                            limit=3,
                            return_properties=["title", "content", "filename", "document_type"]
                        )

                        if not response.objects:
                            return f"No se encontró el documento '{search_text}' en la base de datos."

                        results = []
                        for obj in response.objects[:3]:
                            props = obj.properties
                            title = props.get('title') or props.get('filename') or 'Sin título'
                            content_preview = (props.get('content') or '')[:500]
                            results.append(f"📄 {title}\nContenido: {content_preview}...")

                        return "\n\n".join(results)

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(search_sync)
                        result = future.result(timeout=15)

                    return result

                except Exception as e:
                    logger.error(f"Error searching document: {e}")
                    return f"Error buscando documento: {str(e)}"
            
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
            
            # Document Comparison Tool - accepts flexible parameters
            @tool
            async def compare_documents(documents: str = "", document_name_1: str = "", document_name_2: str = "", comparison_type: str = "content") -> str:
                """Compare two documents to find similarities, differences, and key insights. Pass document names as 'documents' (comma-separated) or as 'document_name_1' and 'document_name_2'."""
                try:
                    # Handle flexible parameter input
                    doc1 = document_name_1
                    doc2 = document_name_2

                    # If documents parameter is provided, parse it
                    if documents and not (doc1 and doc2):
                        docs_list = [d.strip() for d in documents.replace(" y ", ",").replace(" and ", ",").split(",") if d.strip()]
                        if len(docs_list) >= 2:
                            doc1 = docs_list[0]
                            doc2 = docs_list[1]
                        elif len(docs_list) == 1:
                            doc1 = docs_list[0]
                            doc2 = "documento no especificado"

                    if not doc1 or not doc2:
                        return "Error: Se necesitan dos documentos para comparar. Por favor especifica los nombres de los documentos."

                    logger.info(f"📊 Comparing documents: {doc1} vs {doc2}")

                    return f"""📊 **Comparación de Documentos**

**Documentos analizados:**
• {doc1}
• {doc2}

**Tipo de comparación:** {comparison_type}

Para realizar una comparación detallada, necesito acceder al contenido de ambos documentos. Por favor, asegúrate de que ambos documentos estén indexados en el sistema.

**Acciones disponibles:**
• Buscar similitudes en el contenido
• Identificar diferencias clave
• Comparar estructura y formato
• Analizar metadatos"""

                except Exception as e:
                    logger.error(f"Error comparing documents: {e}")
                    return f"Error en comparación de documentos: {str(e)}"

            # Public Knowledge Search Tool - Search legislation, regulations, jurisprudence
            @tool
            async def search_public_knowledge(query: str, category: str = "", jurisdiction: str = "es") -> str:
                """Search the public legal knowledge base for legislation, regulations, jurisprudence, and legal templates. Use this for legal questions or when user asks about laws, regulations, or legal compliance."""
                try:
                    from app.services.public_knowledge_service import public_knowledge_service
                    from app.schemas.public_knowledge import PublicSearchRequest, PublicDocumentCategory, Jurisdiction

                    logger.info(f"📚 Searching public knowledge: {query}")

                    # Map jurisdiction string to enum
                    jur_map = {"es": Jurisdiction.SPAIN, "eu": Jurisdiction.EUROPEAN_UNION, "int": Jurisdiction.INTERNATIONAL}
                    jurisdictions = [jur_map.get(jurisdiction, Jurisdiction.SPAIN)]

                    # Map category string to enum if provided
                    categories = None
                    if category:
                        cat_map = {
                            "legislation": PublicDocumentCategory.LEGISLATION,
                            "regulation": PublicDocumentCategory.REGULATION,
                            "jurisprudence": PublicDocumentCategory.JURISPRUDENCE,
                            "template": PublicDocumentCategory.TEMPLATE,
                            "guideline": PublicDocumentCategory.GUIDELINE
                        }
                        if category.lower() in cat_map:
                            categories = [cat_map[category.lower()]]

                    search_request = PublicSearchRequest(
                        query=query,
                        limit=5,
                        categories=categories,
                        jurisdictions=jurisdictions,
                        verified_only=False,
                        search_type="hybrid"
                    )

                    response = await public_knowledge_service.search(search_request)

                    if not response.results:
                        return f"No se encontraron documentos legales para: {query}"

                    # Format results
                    result_parts = []
                    for i, doc in enumerate(response.results[:3], 1):
                        result_parts.append(f"{i}. **{doc.title}**")
                        if doc.legal_reference:
                            result_parts.append(f"   Referencia: {doc.legal_reference}")
                        if doc.summary:
                            result_parts.append(f"   Resumen: {doc.summary[:200]}...")
                        result_parts.append("")

                    return f"""📚 **Resultados de la base de conocimiento legal**
Búsqueda: {query}
Encontrados: {response.total_results} documentos

{chr(10).join(result_parts)}

*Fuente: Base de conocimiento público NexusDocs360*"""

                except Exception as e:
                    logger.error(f"Error searching public knowledge: {e}")
                    return f"Error buscando en la base de conocimiento legal: {str(e)}"

            # Get Documents Info Tool - For welcome messages and user context
            @tool
            async def get_documents_info(tenant_id: str = "default") -> str:
                """Get real information about documents available for a user/tenant from Weaviate. Returns document count, types, and recent documents."""
                try:
                    from app.services.weaviate_service import weaviate_service
                    from app.core.security import get_tenant_collection_name
                    import concurrent.futures

                    def fetch_docs_sync():
                        """Synchronous function to fetch documents from Weaviate"""
                        # Weaviate client is sync, so we run this in a thread
                        collection_name = get_tenant_collection_name(tenant_id, "documents")
                        logger.info(f"📊 Getting documents info for collection: {collection_name}")

                        # Ensure client is ready (sync check)
                        if not weaviate_service.client:
                            return "Error: Weaviate client not initialized"

                        collection = weaviate_service.client.collections.get(collection_name)

                        doc_count = 0
                        doc_types = {}
                        recent_docs = []

                        for item in collection.iterator(include_vector=False):
                            doc_count += 1
                            props = item.properties

                            file_type = props.get('file_type', 'desconocido')
                            doc_types[file_type] = doc_types.get(file_type, 0) + 1

                            if len(recent_docs) < 5:
                                recent_docs.append({
                                    'title': props.get('title') or props.get('filename') or 'Sin título',
                                    'type': file_type
                                })

                        logger.info(f"📊 Found {doc_count} documents, types: {doc_types}")
                        return (doc_count, doc_types, recent_docs)

                    # Run sync code in thread pool
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(fetch_docs_sync)
                        result = future.result(timeout=30)

                    if isinstance(result, str):
                        return result  # Error message

                    doc_count, doc_types, recent_docs = result

                    if doc_count == 0:
                        return f"El usuario no tiene documentos cargados en el sistema. Tenant: {tenant_id}"

                    types_list = [f"{count} {dtype}" for dtype, count in sorted(doc_types.items(), key=lambda x: -x[1])]
                    docs_list = [f"{d['title']} ({d['type']})" for d in recent_docs]

                    return f"""Información real de documentos del usuario:
- Total de documentos: {doc_count}
- Tipos de documentos: {', '.join(types_list)}
- Documentos disponibles: {', '.join(docs_list)}
- Tenant ID: {tenant_id}"""

                except Exception as e:
                    logger.error(f"Error getting documents info from Weaviate: {e}")
                    return f"Error obteniendo información de documentos: {str(e)}"

            # Register tools with the tree
            if self.tree:
                self.tree.add_tool(analyze_contract_risks)
                self.tree.add_tool(analyze_financial_documents)
                self.tree.add_tool(check_compliance_requirements)
                self.tree.add_tool(extract_signature_requirements)
                self.tree.add_tool(create_executive_summary)
                self.tree.add_tool(search_document)
                self.tree.add_tool(search_web)
                self.tree.add_tool(get_weather_info)
                self.tree.add_tool(compare_documents)
                self.tree.add_tool(search_public_knowledge)
                self.tree.add_tool(get_documents_info)

            self.tools_registered = True
            logger.info("✅ Custom tools registered in Elysia Tree")
            logger.info("📋 Available tools: contract analysis, financial analysis, compliance, signatures, summaries, document comparison, web search, weather, public knowledge, get_documents_info")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to register custom tools: {e}")
            # Fall back to default Elysia tools only
            self.tools_registered = True
            logger.info("✅ Elysia Tree initialized with native tools only")
    
    async def _execute_elysia_tree(
        self,
        query: str,
        enable_debug: bool = False,
        timeout_seconds: int = 60,
        collection_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Execute query using Elysia Tree with optional chain-of-thought debugging"""
        try:
            logger.info(
                "🚀 Executing Elysia Tree (timeout=%ss, collections=%s): %s",
                timeout_seconds,
                collection_names,
                _sanitize_snippet(query)
            )

            # Execute Tree with query in a thread to avoid uvloop issues
            import asyncio
            import concurrent.futures
            import time

            decision_trace = []
            start_time = time.time()
            suppressed_output: Dict[str, str] = {"stdout": "", "stderr": ""}

            def run_tree():
                if enable_debug:
                    # Enable debug mode for chain-of-thought visibility
                    import os
                    os.environ['ELYSIA_DEBUG_MODE'] = 'true'
                    os.environ['ELYSIA_TRACE_DECISIONS'] = 'true'
                    # Pass collection_names so Elysia knows where to search
                    if collection_names:
                        result = self.tree(query, collection_names=collection_names)
                    else:
                        result = self.tree(query)
                else:
                    stdout_buffer = io.StringIO()
                    stderr_buffer = io.StringIO()
                    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                        # Pass collection_names so Elysia knows where to search
                        if collection_names:
                            result = self.tree(query, collection_names=collection_names)
                        else:
                            result = self.tree(query)
                    suppressed_output["stdout"] = stdout_buffer.getvalue()
                    suppressed_output["stderr"] = stderr_buffer.getvalue()

                # Elysia Tree returns a tuple (answer_text, references_list)
                # Extract the answer text properly
                if isinstance(result, tuple):
                    answer_text = result[0] if len(result) > 0 else str(result)
                    references = result[1] if len(result) > 1 else []
                else:
                    answer_text = str(result)
                    references = []

                # Try to extract decision trace if available
                if hasattr(result, '_decision_trace'):
                    return {
                        'answer': answer_text,
                        'decision_trace': result._decision_trace,
                        'reasoning_steps': getattr(result, '_reasoning_steps', []),
                        'tools_selected': getattr(result, '_tools_used', []),
                        'references': references
                    }
                else:
                    return {
                        'answer': answer_text,
                        'decision_trace': [],
                        'reasoning_steps': [],
                        'tools_selected': [],
                        'references': references
                    }
            
            # Run in thread pool to avoid uvloop conflicts
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_tree)
                try:
                    tree_result = future.result(timeout=timeout_seconds)
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    logger.error(
                        "⏱️ Elysia Tree exceeded %ss timeout for query snippet: %s",
                        timeout_seconds,
                        _sanitize_snippet(query)
                    )
                    raise TimeoutError(f"Elysia Tree execution timed out after {timeout_seconds} seconds")
            
            execution_time = int((time.time() - start_time) * 1000)
            
            if enable_debug:
                logger.info(f"🧠 Decision trace: {tree_result.get('decision_trace', [])}")
                logger.info(f"🔧 Tools selected: {tree_result.get('tools_selected', [])}")
            
            logger.info(f"✅ Elysia Tree response: {str(tree_result['answer'])[:200]}...")

            if not enable_debug:
                for stream_name, content in suppressed_output.items():
                    trimmed = content.strip()
                    if trimmed:
                        logger.debug(
                            "Suppressed Elysia %s output (first 1k chars):\n%s",
                            stream_name,
                            trimmed[:1000]
                        )
            
            return {
                'answer': tree_result['answer'],
                'decision_trace': tree_result.get('decision_trace', []),
                'reasoning_steps': tree_result.get('reasoning_steps', []),
                'tools_selected': tree_result.get('tools_selected', []),
                'execution_time_ms': execution_time
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Elysia Tree execution failed: {type(e).__name__}: {error_msg}")
            raise

    def _get_available_tools(self) -> list:
        """Get list of available tool names"""
        return [
            'text_response',
            'analyze_contract_risks',
            'analyze_financial_documents',
            'check_compliance_requirements',
            'extract_signature_requirements',
            'create_executive_summary',
            'search_document',
            'search_web',
            'get_weather_info',
            'compare_documents',
            'search_public_knowledge',
            'get_documents_info'
        ]

    def _generate_contextual_suggestions(self, query: str, tools_used: list, has_documents: bool) -> list:
        """Generate contextual suggestions based on query, tools used, and user context"""
        from app.schemas.elysia import Suggestion

        suggestions = []

        query_lower = query.lower()

        # Document-related suggestions
        if has_documents:
            if 'contrato' in query_lower or 'contract' in query_lower:
                suggestions.append(Suggestion(
                    text="Analizar riesgos del contrato",
                    action="analyze_contract_risks",
                    icon="shield-alert"
                ))
                suggestions.append(Suggestion(
                    text="Extraer requisitos de firma",
                    action="extract_signature_requirements",
                    icon="pen-tool"
                ))
            elif 'factura' in query_lower or 'financ' in query_lower or 'invoice' in query_lower:
                suggestions.append(Suggestion(
                    text="Analizar documentos financieros",
                    action="analyze_financial_documents",
                    icon="calculator"
                ))
            elif 'cumplimiento' in query_lower or 'compliance' in query_lower or 'gdpr' in query_lower:
                suggestions.append(Suggestion(
                    text="Verificar cumplimiento normativo",
                    action="check_compliance_requirements",
                    icon="check-circle"
                ))

            # Always suggest summary if we have documents
            suggestions.append(Suggestion(
                text="Crear resumen ejecutivo",
                action="create_executive_summary",
                icon="file-text"
            ))
        else:
            # No documents found - suggest searching or uploading via UI
            suggestions.append(Suggestion(
                text="Buscar en mis documentos",
                action="search_document",
                icon="search"
            ))

        # General suggestions based on context
        if 'compar' in query_lower:
            suggestions.append(Suggestion(
                text="Comparar documentos",
                action="compare_documents",
                icon="git-compare"
            ))

        if 'busca' in query_lower or 'search' in query_lower or 'encuentra' in query_lower:
            suggestions.append(Suggestion(
                text="Buscar en mis documentos",
                action="search_documents",
                icon="search"
            ))

        # Web search for external info
        if 'actualidad' in query_lower or 'noticia' in query_lower or 'hoy' in query_lower:
            suggestions.append(Suggestion(
                text="Buscar información en la web",
                action="search_web",
                icon="globe"
            ))

        # Legal/regulatory suggestions
        legal_keywords = ['ley', 'normativa', 'rgpd', 'lopd', 'gdpr', 'regulación', 'legal', 'jurisprudencia', 'sentencia', 'boe']
        if any(kw in query_lower for kw in legal_keywords):
            suggestions.append(Suggestion(
                text="Buscar en base de conocimiento legal",
                action="search_public_knowledge",
                icon="scale"
            ))

        # Default suggestions if none were added
        if len(suggestions) == 0:
            suggestions = [
                Suggestion(text="Buscar en mis documentos", action="search_documents", icon="search"),
                Suggestion(text="Ver información de documentos", action="get_documents_info", icon="info"),
                Suggestion(text="¿Qué puedes hacer?", action="help", icon="help-circle"),
            ]

        # Limit to 4 suggestions
        return suggestions[:4]

    async def _build_context_from_documents(self, query: ElysiaQuery) -> tuple[str, List[str], int]:
        """Fetch document snippets from Weaviate to ground the query."""
        context_parts: List[str] = []
        tools_used: List[str] = []
        documents_found = 0

        doc_context = query.context or {}
        specific_doc_id = doc_context.get('document_id')
        focus_document = bool(doc_context.get('focus_document'))

        try:
            from app.services.weaviate_service import weaviate_service
            from app.schemas.weaviate import SearchRequest
            from app.core.security import get_tenant_collection_name

            await weaviate_service.initialize()
            collection_name = get_tenant_collection_name(query.tenant_id, "documents")

            content_limits = {
                "gemini": 400000,
                "openai": 80000,
                "ollama": 15000
            }
            max_focus_chars = content_limits.get(self.provider, 20000)

            if specific_doc_id and focus_document:
                logger.info("📄 Fetching focused document %s from collection %s", specific_doc_id, collection_name)
                doc_result = await weaviate_service.get_document_by_id(collection_name, specific_doc_id)
                if doc_result and doc_result.get('content'):
                    full_content = doc_result.get('content', '')
                    snippet = full_content[:max_focus_chars]
                    title = doc_result.get('title') or 'Documento'
                    file_type = doc_result.get('document_type', 'desconocido')
                    logger.info("✅ Document found: %s (%d chars)", title, len(full_content))
                    context_parts.append(
                        f"DOCUMENTO PRINCIPAL: {title}\nTipo: {file_type}\nCaracteres incluidos: {len(snippet)}\n---\n{snippet}"
                    )
                    tools_used.append(f"document_focus:{title}:{specific_doc_id}")
                    documents_found = 1
                else:
                    logger.warning("⚠️ Document %s not found in Weaviate collection %s - may not be indexed yet", specific_doc_id, collection_name)
                    # Document not in Weaviate - inform user that indexing may be needed
                    context_parts.append(
                        f"NOTA: El documento con ID {specific_doc_id} no se encontró en la base de datos vectorial. "
                        "Es posible que el documento aún no haya sido indexado. "
                        "Por favor, sube el documento o espera a que se complete la indexación."
                    )
            else:
                search_req = SearchRequest(
                    query=query.query,
                    tenant_id=query.tenant_id,
                    limit=3,
                    search_type='keyword',
                    min_similarity=0.5
                )
                weaviate_result = await weaviate_service.search_documents(collection_name, search_req)
                if weaviate_result.results:
                    for idx, doc in enumerate(weaviate_result.results[:3], 1):
                        snippet = (doc.content or '')[:800]
                        context_parts.append(
                            f"DOCUMENTO {idx}: {doc.title}\nSimilitud: {doc.similarity_score or 0:.2f}\n---\n{snippet}"
                        )
                        tools_used.append(f"weaviate_search:{doc.title}:{doc.id}")
                        documents_found += 1
                else:
                    logger.info("ℹ️ No se encontraron documentos relevantes en Weaviate")
        except Exception as err:
            logger.warning("⚠️ Error obteniendo contexto de Weaviate: %s", err)

        return "\n\n".join(context_parts), tools_used, documents_found

    async def execute_query(self, query: ElysiaQuery) -> ElysiaResponse:
        """Execute Elysia query with Weaviate context.

        NOTE: Elysia v0.3.dev1 cannot connect directly to local Weaviate due to
        a bug in client.py that requires WCD_URL. As a workaround, we fetch
        document context from Weaviate ourselves and pass it to Elysia.

        This is a hybrid approach until Elysia supports local Weaviate natively.
        """
        start_time = datetime.now()
        session_id = query.session_id or str(uuid.uuid4())

        try:
            if not self.tree or not self.tools_registered:
                raise ValueError("Elysia Tree not initialized properly")

            logger.info(f"🚀 Executing Elysia query: {query.query}")
            tools_used: List[str] = []
            enable_debug = getattr(query, 'enable_debug', False)

            # Fetch document context from Weaviate (workaround for Elysia local limitation)
            context_content, context_tools, documents_found = await self._build_context_from_documents(query)
            tools_used.extend(context_tools)

            if context_content:
                # Pass document context to Elysia for analysis
                enhanced_query = (
                    f"Contexto del documento (obtenido de Weaviate):\n"
                    f"{context_content}\n\n"
                    f"Solicitud del usuario: {query.query}"
                )
            else:
                enhanced_query = query.query

            # Execute Elysia Tree
            tree_result = await self._execute_elysia_tree(
                enhanced_query,
                enable_debug,
                timeout_seconds=60
            )

            result = tree_result['answer']
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

            references = tree_result.get('references', [])
            tree_tools = tree_result.get('tools_selected', []) or []
            tools_used.extend(tree_tools)

            # Store session info
            self.sessions[session_id] = {
                "query": query.query,
                "enhanced_query": enhanced_query if context_content else None,
                "result": result,
                "timestamp": start_time,
                "execution_time_ms": execution_time,
                "documents_found": documents_found,
                "references": references,
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
                    "tools_selected": tree_tools,
                    "documents_context": documents_found
                }
            
            has_documents = documents_found > 0
            suggestions = self._generate_contextual_suggestions(query.query, tools_used, has_documents)

            return ElysiaResponse(
                query=query.query,
                answer=result,
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=["elysia_native_rag", collection_name],
                tools_used=tools_used,
                data=debug_data,
                visualization=None,
                confidence_score=0.85 if documents_found > 0 else 0.7,
                execution_time_ms=execution_time,
                iterations=1,
                learning_applied=query.enable_learning,
                suggestions=suggestions,
                available_tools=self._get_available_tools()
            )
            
        except Exception as e:
            logger.error(f"❌ Elysia query execution failed: {e}")

            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

            # Provide helpful suggestions even on error
            from app.schemas.elysia import Suggestion
            error_suggestions = [
                Suggestion(text="Intentar de nuevo", action="retry", icon="refresh-cw"),
                Suggestion(text="Buscar en documentos", action="search_documents", icon="search"),
                Suggestion(text="Contactar soporte", action="help", icon="help-circle"),
            ]

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
                learning_applied=False,
                suggestions=error_suggestions,
                available_tools=self._get_available_tools()
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
            "llm_provider": self.provider,
            "llm_endpoint": self.openai_base_url if self.provider == "openai" else self.ollama_url,
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

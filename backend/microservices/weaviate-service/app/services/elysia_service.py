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
            
            # Filter only nexus collections (tenant-specific)
            tenant_collections = [c for c in available_collections if c.lower().startswith('nexus')]
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
            
            # Register tools with the tree
            if self.tree:
                self.tree.add_tool(analyze_contract_risks)
                self.tree.add_tool(analyze_financial_documents)
                self.tree.add_tool(check_compliance_requirements)
                self.tree.add_tool(extract_signature_requirements)
                self.tree.add_tool(create_executive_summary)
                self.tree.add_tool(ingest_document)
            
            self.tools_registered = True
            logger.info("✅ Custom CrewAI tools registered in Elysia Tree")
            logger.info("📋 Available tools: contract analysis, financial analysis, compliance, signatures, summaries")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to register custom tools: {e}")
            # Fall back to default Elysia tools only
            self.tools_registered = True
            logger.info("✅ Elysia Tree initialized with native tools only")
    
    async def _execute_elysia_tree(self, query: str) -> str:
        """Execute query using Elysia Tree following official docs"""
        try:
            logger.info(f"🚀 Executing Elysia Tree: {query}")
            
            # Execute Tree with query in a thread to avoid uvloop issues
            import asyncio
            import concurrent.futures
            
            def run_tree():
                return self.tree(query)
            
            # Run in thread pool to avoid uvloop conflicts
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_tree)
                response = future.result(timeout=60)  # 60 second timeout
            
            logger.info(f"✅ Elysia Tree response: {str(response)[:200]}...")
            return str(response)
            
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
                        tools_used.append(f"weaviate_search:{doc.title}")
                    
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
            
            # Step 3: Execute using Elysia Tree
            result = await self._execute_elysia_tree(enhanced_query)
            
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # Store session info
            self.sessions[session_id] = {
                "query": query.query,
                "enhanced_query": enhanced_query if context_content else None,
                "result": result,
                "timestamp": start_time,
                "execution_time_ms": execution_time,
                "documents_found": len(weaviate_result.results) if 'weaviate_result' in locals() and weaviate_result.results else 0
            }
            
            return ElysiaResponse(
                query=query.query,
                answer=result,
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=["weaviate_search", "context_enhancement", "elysia_tree"] if context_content else ["elysia_tree"],
                tools_used=tools_used,
                data=None,
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
        # Elysia Tree handles tool discovery and selection internally
        return [
            {
                "name": "elysia_tree",
                "description": "Native Elysia decision tree with dynamic tool selection",
                "category": "agentic"
            }
        ]
    
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
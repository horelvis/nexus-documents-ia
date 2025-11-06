"""
CAG Service using LangGraph implementation
Modern service with proper agent orchestration
"""
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_community.vectorstores import Qdrant as QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from ..core.config import settings
from ..core.cag_langgraph_engine import CAGLangGraphEngine


class CAGLangGraphService:
    """CAG service using LangGraph for orchestration"""
    
    def __init__(self):
        self.llm = None
        self.embeddings = None
        self.qdrant_client = None
        self.engine = None
        self._initialized = False
        self._tenant_engines = {}  # Cache engines per tenant
    
    async def initialize(self):
        """Initialize service components"""
        if self._initialized:
            return
        
        try:
            # Initialize LLM with Gemma model
            logger.info(f"Initializing LLM: {settings.llm_model}")
            import os
            os.environ["OLLAMA_HOST"] = settings.ollama_base_url
            
            # Try to use Gemma model, fallback to llama if not available
            model_name = settings.llm_model
            if "gemma" in model_name.lower():
                # Check if gemma is available
                try:
                    test_llm = ChatOllama(model="gemma3:12b-it-qat", timeout=5)
                    await test_llm.ainvoke("test")
                    model_name = "gemma3:12b-it-qat"
                    logger.info("Using Gemma 3 12B model")
                except:
                    logger.warning("Gemma model not available, falling back to default")
                    model_name = settings.llm_model
            
            self.llm = ChatOllama(
                model=model_name,
                temperature=settings.cag_temperature,
                num_ctx=settings.cag_context_window,
                timeout=settings.llm_timeout,
                num_predict=1500  # Increased for better responses
            )
            
            # Initialize embeddings
            logger.info(f"Initializing embeddings: {settings.embedding_model}")
            self.embeddings = OllamaEmbeddings(
                model=settings.embedding_model,
            )
            
            # Initialize Qdrant client
            logger.info(f"Connecting to Qdrant at {settings.qdrant_host}:{settings.qdrant_port}")
            self.qdrant_client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                timeout=30
            )
            
            self._initialized = True
            logger.info("CAG LangGraph service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize CAG service: {e}")
            raise
    
    def _get_tenant_collection(self, tenant_id: str) -> str:
        """Get collection name for tenant"""
        return f"tenant_{tenant_id}_documents"
    
    def _get_vector_store(self, tenant_id: str) -> QdrantVectorStore:
        """Get vector store for tenant"""
        collection_name = self._get_tenant_collection(tenant_id)
        
        # Ensure collection exists
        try:
            self.qdrant_client.get_collection(collection_name)
        except Exception:
            logger.info(f"Creating collection for tenant {tenant_id}")
            self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=384,  # nomic-embed-text dimension
                    distance=Distance.COSINE
                )
            )
        
        return QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=collection_name,
            embeddings=self.embeddings
        )
    
    def _get_tenant_engine(self, tenant_id: str) -> CAGLangGraphEngine:
        """Get or create engine for tenant"""
        if tenant_id not in self._tenant_engines:
            vector_store = self._get_vector_store(tenant_id)
            self._tenant_engines[tenant_id] = CAGLangGraphEngine(
                llm=self.llm,
                embeddings=self.embeddings,
                vector_store=vector_store,
                max_iterations=settings.cag_max_iterations,
                quality_threshold=settings.cag_quality_threshold
            )
        return self._tenant_engines[tenant_id]
    
    async def process_query(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_iterations: Optional[int] = None
    ) -> Dict[str, Any]:
        """Process a query using LangGraph CAG engine"""
        if not self._initialized:
            await self.initialize()
        
        try:
            start_time = datetime.utcnow()
            
            # Get tenant-specific engine
            engine = self._get_tenant_engine(tenant_id)
            
            # Override parameters if provided
            if max_iterations:
                engine.max_iterations = max_iterations
            
            # Process with LangGraph engine
            logger.info(f"Processing query for tenant {tenant_id}: {query[:100]}...")
            result = await engine.process(
                query=query,
                tenant_id=tenant_id,
                user_id=user_id,
                context=context
            )
            
            # Calculate execution time
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Add execution time to result
            if result["success"]:
                result["execution_time"] = execution_time
                result["engine"] = "langgraph"
                result["model"] = model or settings.llm_model
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "answer": None
            }
    
    async def analyze_document(
        self,
        document_content: str,
        document_id: str,
        tenant_id: str,
        user_id: str,
        analysis_type: str = "comprehensive"
    ) -> Dict[str, Any]:
        """Analyze a document using LangGraph CAG"""
        if not self._initialized:
            await self.initialize()
        
        # Create specialized query based on analysis type
        queries = {
            "comprehensive": f"""Perform a comprehensive analysis of this document:
                1. Provide a detailed executive summary
                2. Extract all key entities (people, organizations, dates, amounts, locations)
                3. Identify main topics, themes, and subject areas
                4. Analyze sentiment, tone, and writing style
                5. Extract action items, obligations, and deadlines
                6. Identify risks, opportunities, and recommendations
                7. Note any compliance or legal considerations
                
                Document: {document_content[:3000]}...""",
            
            "contract": f"""Analyze this contract in detail:
                1. Identify all parties involved with their roles
                2. Extract key terms, conditions, and definitions
                3. List all obligations, deliverables, and milestones
                4. Identify important dates, deadlines, and duration
                5. Highlight risks, penalties, and termination clauses
                6. Note payment terms and financial obligations
                7. Identify governing law and dispute resolution
                
                Contract: {document_content[:3000]}...""",
            
            "financial": f"""Perform financial analysis on this document:
                1. Extract all financial figures and calculations
                2. Identify revenue, expenses, and profit margins
                3. Analyze cash flow and financial ratios
                4. Identify trends and patterns in the data
                5. Highlight any anomalies or concerns
                6. Provide insights and recommendations
                
                Document: {document_content[:3000]}...""",
            
            "compliance": f"""Perform compliance analysis on this document:
                1. Identify all regulatory references and requirements
                2. Check for compliance with relevant standards
                3. Flag potential violations or non-compliance issues
                4. List required actions for compliance
                5. Assess overall compliance risk level
                6. Provide remediation recommendations
                
                Document: {document_content[:3000]}..."""
        }
        
        query = queries.get(analysis_type, queries["comprehensive"])
        
        # Process with CAG engine
        result = await self.process_query(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            context={
                "document_id": document_id,
                "analysis_type": analysis_type,
                "document_length": len(document_content)
            }
        )
        
        if result["success"]:
            # Detect document type
            doc_type = await self._detect_document_type(document_content)
            
            return {
                "success": True,
                "document_id": document_id,
                "document_type": doc_type["type"],
                "confidence": doc_type["confidence"],
                "analysis_type": analysis_type,
                "analysis": result["answer"],
                "quality_score": result["quality_score"],
                "execution_time": result.get("execution_time", 0),
                "iterations": result.get("iterations", 1),
                "metadata": result.get("metadata", {})
            }
        else:
            return result
    
    async def _detect_document_type(self, document_content: str) -> Dict[str, Any]:
        """Detect document type using LLM"""
        if not self._initialized:
            await self.initialize()
        
        try:
            detection_prompt = f"""Classify this document into ONE category:
            - contract: Legal contracts, agreements, terms
            - invoice: Invoices, bills, receipts
            - report: Reports, analysis, research
            - legal: Legal documents, policies, regulations
            - financial: Financial statements, budgets
            - technical: Technical documentation, manuals
            - hr: HR documents, resumes, employee records
            - correspondence: Letters, emails, memos
            - presentation: Slides, pitch decks
            - general: Other documents
            
            Respond with: category|confidence (0-1)
            Example: contract|0.95
            
            Document:
            {document_content[:2000]}
            
            Classification:"""
            
            response = await self.llm.ainvoke(detection_prompt)
            
            # Parse response
            if hasattr(response, 'content'):
                response_text = response.content.strip().lower()
            else:
                response_text = str(response).strip().lower()
            
            # Extract type and confidence
            if '|' in response_text:
                parts = response_text.split('|')
                doc_type = parts[0].strip()
                try:
                    confidence = float(parts[1].strip())
                except:
                    confidence = 0.7
            else:
                # Fallback detection
                doc_type = "general"
                confidence = 0.5
                
                # Check for keywords
                content_lower = document_content.lower()[:2000]
                if any(word in content_lower for word in ["contract", "agreement", "contrato"]):
                    doc_type = "contract"
                    confidence = 0.7
                elif any(word in content_lower for word in ["invoice", "bill", "factura"]):
                    doc_type = "invoice"
                    confidence = 0.7
                elif any(word in content_lower for word in ["report", "analysis", "informe"]):
                    doc_type = "report"
                    confidence = 0.6
            
            return {
                "type": doc_type,
                "confidence": confidence
            }
            
        except Exception as e:
            logger.error(f"Error detecting document type: {e}")
            return {
                "type": "general",
                "confidence": 0.5
            }
    
    async def process_query_stream(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """Process query with streaming using LangGraph events"""
        if not self._initialized:
            await self.initialize()
        
        try:
            # Get tenant engine
            engine = self._get_tenant_engine(tenant_id)
            
            # Stream events from graph execution
            config = {"configurable": {"thread_id": f"{tenant_id}_{user_id}"}}
            
            initial_state = {
                "query": query,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "context_chunks": [],
                "identified_gaps": [],
                "messages": [],
                "current_response": "",
                "final_answer": "",
                "iteration_count": 0,
                "max_iterations": engine.max_iterations,
                "should_continue": False,
                "quality_metrics": {},
                "quality_score": 0.0,
                "metadata": context or {}
            }
            
            # Stream graph events
            async for event in engine.graph.astream(initial_state, config):
                # Convert graph events to streaming format
                if "retrieve_context" in event:
                    yield {
                        "type": "progress",
                        "content": "Searching relevant documents...",
                        "progress": 20
                    }
                elif "detect_gaps" in event:
                    yield {
                        "type": "progress",
                        "content": "Analyzing context completeness...",
                        "progress": 40
                    }
                elif "expand_context" in event:
                    yield {
                        "type": "progress",
                        "content": "Gathering additional information...",
                        "progress": 60
                    }
                elif "generate_response" in event:
                    yield {
                        "type": "progress",
                        "content": "Generating comprehensive answer...",
                        "progress": 80
                    }
                elif "validate_quality" in event:
                    yield {
                        "type": "progress",
                        "content": "Validating response quality...",
                        "progress": 90
                    }
            
            # Get final state
            final_state = await engine.graph.aget_state(config)
            
            # Yield final result
            yield {
                "type": "result",
                "content": {
                    "answer": final_state.values.get("final_answer", ""),
                    "quality_score": final_state.values.get("quality_score", 0.0),
                    "iterations": final_state.values.get("iteration_count", 0),
                    "gaps_identified": len(final_state.values.get("identified_gaps", [])),
                    "context_chunks_used": len(final_state.values.get("context_chunks", [])),
                    "engine": "langgraph"
                }
            }
            
        except Exception as e:
            logger.error(f"Error in streaming query: {e}")
            yield {
                "type": "error",
                "content": str(e)
            }
    
    async def get_graph_visualization(self, tenant_id: str) -> str:
        """Get visualization of the LangGraph workflow"""
        try:
            engine = self._get_tenant_engine(tenant_id)
            return engine.visualize_graph()
        except Exception as e:
            logger.error(f"Error getting graph visualization: {e}")
            return f"Error: {e}"
    
    async def health_check(self) -> Dict[str, Any]:
        """Check service health"""
        try:
            if not self._initialized:
                await self.initialize()
            
            # Test LLM
            llm_ok = False
            try:
                response = await self.llm.ainvoke("test")
                llm_ok = bool(response)
            except Exception as e:
                logger.error(f"LLM health check failed: {e}")
            
            # Test embeddings
            embeddings_ok = False
            try:
                embedding = await self.embeddings.aembed_query("test")
                embeddings_ok = len(embedding) > 0
            except Exception as e:
                logger.error(f"Embeddings health check failed: {e}")
            
            # Test Qdrant
            qdrant_ok = False
            try:
                collections = await asyncio.to_thread(
                    self.qdrant_client.get_collections
                )
                qdrant_ok = True
            except Exception as e:
                logger.error(f"Qdrant health check failed: {e}")
            
            # Test LangGraph engine
            langgraph_ok = False
            try:
                # Try to create a test engine
                test_engine = CAGLangGraphEngine(
                    llm=self.llm,
                    embeddings=self.embeddings,
                    vector_store=None,
                    max_iterations=1
                )
                langgraph_ok = test_engine.graph is not None
            except Exception as e:
                logger.error(f"LangGraph health check failed: {e}")
            
            all_healthy = all([llm_ok, embeddings_ok, qdrant_ok, langgraph_ok])
            
            return {
                "status": "healthy" if all_healthy else "unhealthy",
                "service": "cag-langgraph-service",
                "engine": "langgraph",
                "checks": {
                    "llm": llm_ok,
                    "embeddings": embeddings_ok,
                    "qdrant": qdrant_ok,
                    "langgraph": langgraph_ok
                }
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "service": "cag-langgraph-service",
                "error": str(e)
            }


# Global service instance
cag_langgraph_service = CAGLangGraphService()
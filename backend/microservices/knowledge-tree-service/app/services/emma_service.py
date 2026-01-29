"""
Emma AI Service - Personal AI Assistant for NouxCubeIA

Emma is the user-facing name for the AI assistant.
This module provides the Emma service interface using:
- Emma (PRIMARY): Simplified async agent with SIL fast path
- RAGPipeline (FALLBACK): Simple RAG for when agents are disabled

ARCHITECTURE:
Emma uses a native async LLM client with:
1. SIL Fast Path - Structural queries answered without LLM (70-90% token savings)
2. Domain Routing - Dynamic prompt loading based on query domain
3. Skill Loading - Procedural knowledge loaded on-demand
4. Agentic Loop - Tool-calling loop for complex queries
5. Redis persistence for conversation history

References:
- Anthropic Contextual Retrieval: https://www.anthropic.com/news/contextual-retrieval
- Anthropic Agent Skills: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
"""

import logging
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncGenerator

import yaml

from app.schemas.emma import (
    EmmaQuery, EmmaResponse, ToolExecution, DecisionTreeState,
    FeedbackRequest, VisualizationRequest, Suggestion, ToolInfo
)
from app.core.config import settings
from app.services.tool_integration import ToolIntegration, get_tool_integration
from app.services.memory import MemoryService, get_memory_service

# PRIMARY: Emma with SIL fast path and domain routing
from app.agents.emma import (
    Emma, EmmaResult, ExecutionContext, EmmaConfig
)

# LangGraph multi-agent RAG (optional, enabled via LANGGRAPH_RAG_ENABLED)
from app.agents.langgraph import (
    is_langgraph_enabled_for_tenant,
    execute_langgraph_query,
    stream_langgraph_query,
    LangGraphQueryResponse,
)

# NexusRouter: ML-based intent classification
from app.services.nexus_router import (
    nexus_router,
    IntentClassification,
    RequiredAction,
    Intent,
)

logger = logging.getLogger(__name__)


class EmmaService:
    """
    Emma AI Service - Personal AI Assistant

    Uses Emma as the PRIMARY execution path for agent-based queries.
    Falls back to RAGPipeline only when agents are disabled (settings.agents_enabled=False).

    Emma features:
    - SIL Fast Path: Structural queries answered without LLM
    - Domain Routing: Dynamic prompts based on query domain
    - Skill Loading: Procedural knowledge on-demand
    """

    def __init__(self):
        # PRIMARY: Emma with SIL fast path
        self._emma: Emma = Emma()

        self._initialized = False
        self._available_tools = []
        self._conversational_config = None
        self._analysis_keywords = []

        # Tool Framework integration
        self._tool_integration: ToolIntegration = get_tool_integration()
        # Memory Protocol integration
        self._memory: MemoryService = get_memory_service()

        # NexusRouter: ML-based intent classification (replaces hardcoded patterns)
        self._nexus_router = nexus_router
        self._nexus_router_enabled = True  # Can be disabled via config if needed

        self._load_config()
        logger.info("Initializing Emma AI Service (Emma primary, NexusRouter intent classification)")

    def _load_config(self):
        """Load Emma configuration from YAML"""
        try:
            config_path = Path(__file__).parent.parent.parent / "config" / "prompts" / "emma_prompts.yaml"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    self._conversational_config = config.get('conversational', {})
                    analysis_config = config.get('analysis_detection', {})
                    self._analysis_keywords = analysis_config.get('keywords', [])
                    logger.info(f"✅ Loaded config: {len(self._conversational_config)} conversational, {len(self._analysis_keywords)} analysis keywords")
            else:
                logger.warning(f"⚠️ Config not found at {config_path}")
        except Exception as e:
            logger.error(f"❌ Failed to load config: {e}")

    def _check_conversational_query(self, query: str) -> Optional[str]:
        """Check if query matches conversational patterns."""
        if not self._conversational_config:
            return None

        query_lower = query.lower().strip()

        for category, data in self._conversational_config.items():
            patterns = data.get('patterns', [])
            response = data.get('response', '')

            for pattern in patterns:
                pattern_lower = pattern.lower()
                if category == 'greetings':
                    if query_lower.startswith(pattern_lower) or query_lower == pattern_lower:
                        logger.info(f"🗣️ Detected greeting: '{pattern}'")
                        return response.strip()
                else:
                    if pattern_lower in query_lower:
                        logger.info(f"🗣️ Detected {category}: '{pattern}'")
                        return response.strip()

        return None

    async def _classify_user_intent(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Use LLM to classify user intent."""
        import httpx

        try:
            from app.agents.config import agent_config

            context_section = ""
            if conversation_history and len(conversation_history) > 0:
                recent_history = conversation_history[-6:]
                history_lines = []
                for msg in recent_history:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")[:200]
                    if role == "user":
                        history_lines.append(f"Usuario: {content}")
                    elif role == "assistant":
                        history_lines.append(f"Emma: {content}")
                if history_lines:
                    context_section = "\nContexto de conversación anterior:\n" + "\n".join(history_lines) + "\n"

            system_msg = "Eres un clasificador de intención. Responde SOLO con una palabra: ANALYSIS, CONVERSATION o SEARCH."

            classification_prompt = f"""Clasifica la intención del usuario: ANALYSIS, CONVERSATION o SEARCH

SEARCH - busca o pide más información (documentos, emails, "más detalles", "mostrar")
ANALYSIS - pide analizar estructura, cláusulas, riesgos de documentos específicos
CONVERSATION - SOLO saludos simples como "hola", "gracias"

REGLA: Si hace referencia a algo anterior ("ese", "más detalles"), SIEMPRE es SEARCH.
{context_section}
Mensaje actual: "{query}"

Responde SOLO una palabra:"""

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{agent_config.vllm_base_url}/chat/completions",
                    json={
                        "model": agent_config.vllm_model,
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": classification_prompt}
                        ],
                        "max_tokens": 300,
                        "temperature": 0.0
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    raw_response = data["choices"][0]["message"]["content"].strip()

                    if "</think>" in raw_response:
                        raw_response = raw_response.split("</think>")[-1].strip()
                    elif "<think>" in raw_response and "</think>" not in raw_response:
                        return self._keyword_based_intent(query)

                    intent_text = raw_response.upper()

                    if "ANALYSIS" in intent_text:
                        logger.info(f"🧠 Intent: ANALYSIS - '{query[:50]}...'")
                        return "analysis"
                    elif "CONVERSATION" in intent_text:
                        logger.info(f"🧠 Intent: CONVERSATION - '{query[:50]}...'")
                        return "conversation"
                    else:
                        logger.info(f"🧠 Intent: SEARCH - '{query[:50]}...'")
                        return "search"
                else:
                    return self._keyword_based_intent(query)

        except Exception as e:
            logger.warning(f"⚠️ Intent classification failed: {e}")
            return self._keyword_based_intent(query)

    def _keyword_based_intent(self, query: str) -> str:
        """Fallback keyword-based intent detection."""
        query_lower = query.lower().strip()
        for keyword in self._analysis_keywords:
            if keyword.lower() in query_lower:
                return "analysis"
        return "search"

    async def _get_enriched_user_context(
        self,
        tenant_id: str,
        user_id: Optional[str],
        request_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get user context enriched with request data.

        Combines stored preferences with request context to ensure
        user information (name, email, role) is available for personalization.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            request_context: Context from the API request (may contain user_name, user_email)

        Returns:
            Enriched user context dictionary
        """
        user_context = None

        # First, try to load from MemoryService (stored preferences)
        if user_id and self._memory:
            try:
                user_context = await self._memory.get_user_context(tenant_id, user_id)
            except Exception as e:
                logger.warning(f"⚠️ Failed to load user context from memory: {e}")

        # If no context yet, create base structure
        if not user_context:
            user_context = {}

        # Enrich with request context data (this data comes from authenticated user)
        if request_context:
            # User name from request (priority over stored if available)
            if request_context.get("user_name") and not user_context.get("name"):
                user_context["name"] = request_context["user_name"]
            # User email
            if request_context.get("user_email") and not user_context.get("email"):
                user_context["email"] = request_context["user_email"]
            # User role
            if request_context.get("user_role") and not user_context.get("role"):
                user_context["role"] = request_context["user_role"]
            # Profession (for legal domain)
            if request_context.get("profession") and not user_context.get("profession"):
                user_context["profession"] = request_context["profession"]
            # Document context (for focused document analysis)
            if request_context.get("document_id"):
                user_context["document_id"] = request_context["document_id"]
                # Load document content for direct analysis (reduces LLM calls)
                await self._load_document_content(tenant_id, request_context["document_id"], user_context)
            if request_context.get("focus_document"):
                user_context["focus_document"] = request_context["focus_document"]

        # Log what we have
        if user_context.get("name"):
            logger.info(f"👤 User context: {user_context.get('name', 'Unknown')}")
        else:
            logger.debug(f"👤 No user name in context for user_id={user_id}")

        # Log document context if present
        if user_context.get("document_id"):
            logger.info(f"📄 Document context: {user_context.get('document_id')}")

        return user_context if user_context else None

    async def _load_document_content(
        self,
        tenant_id: str,
        document_id: str,
        user_context: Dict[str, Any]
    ) -> None:
        """
        Load document content into user_context for direct analysis.

        This allows Emma to analyze simple documents (invoices, payslips)
        directly without calling additional tools, reducing LLM calls.
        """
        try:
            from app.services.weaviate_service import WeaviateService
            from app.core.security import get_tenant_collection_name

            service = WeaviateService()
            collection_name = get_tenant_collection_name(tenant_id)

            doc = await service.get_document_by_id(
                collection_name=collection_name,
                document_id=document_id
            )

            if doc:
                content = doc.get("content", "")
                title = doc.get("title", doc.get("filename", "Document"))

                # Load document content if reasonable size (< 20000 chars)
                # This allows direct analysis without tool calls for most documents
                if len(content) < 20000:
                    user_context["document_content"] = content
                    user_context["document_title"] = title
                    logger.info(f"📄 Loaded document content: {title} ({len(content)} chars)")
                else:
                    # For very large documents, provide title but instruct to use tool
                    user_context["document_title"] = title
                    user_context["document_too_large"] = True
                    logger.info(f"📄 Document too large for direct context: {title} ({len(content)} chars) - use analyze_document tool")
            else:
                logger.warning(f"⚠️ Document not found in collection: {document_id}")

        except Exception as e:
            logger.warning(f"⚠️ Could not load document content: {e}")

    async def initialize(self):
        """Initialize Emma components."""
        if self._initialized:
            return

        try:
            # PRIMARY: Initialize Emma
            await self._emma.initialize()
            logger.info("✅ Emma initialized (SIL fast path + domain routing + skills)")

            # Initialize Tool Framework
            await self._tool_integration.initialize()
            logger.info("✅ Tool Framework initialized")

            # Initialize Memory Protocol
            await self._memory.initialize()
            logger.info("✅ Memory Protocol initialized")

            # Initialize NexusRouter (ML-based intent classification)
            if self._nexus_router_enabled:
                try:
                    await self._nexus_router.initialize()
                    logger.info("✅ NexusRouter initialized (ML intent classification)")
                except Exception as e:
                    logger.warning(f"⚠️ NexusRouter init failed (using fallback): {e}")

            # Build available tools list (nexus_ prefix for search tools)
            legacy_tools = [
                "nexus_semantic_search", "nexus_hybrid_search", "nexus_keyword_search",
                "nexus_search_public_knowledge", "nexus_search_with_legal_context",
                "analyze_document", "compare_documents", "rag_answer",
                "get_document_content", "summarize_documents"
            ]
            framework_tools = self._tool_integration.get_tool_info()
            framework_tool_names = [t["name"] for t in framework_tools]
            self._available_tools = legacy_tools + framework_tool_names

            logger.info(f"✅ Emma AI initialized: Emma (primary) + NexusRouter (intent) + RAGPipeline (fallback)")
            self._initialized = True

        except Exception as e:
            logger.warning(f"⚠️ Initialization failed: {e}")
            self._initialized = True

    async def execute_query(self, query: EmmaQuery) -> EmmaResponse:
        """Execute Emma AI query."""
        start_time = time.time()
        session_id = query.session_id or str(uuid.uuid4())

        if not self._initialized:
            await self.initialize()

        # Load conversation history
        conversation_history = []
        try:
            if session_id:
                conversation_history = await self._memory.get_conversation_history(
                    tenant_id=query.tenant_id,
                    session_id=session_id,
                    max_messages=10
                )
        except Exception as e:
            logger.warning(f"⚠️ Failed to load conversation history: {e}")

        # Check conversational patterns FIRST (greetings, introductions, thanks)
        # These don't need RAG/LLM - respond directly
        conversational_response = self._check_conversational_query(query.query)
        if conversational_response:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.info(f"💬 Conversational response for: '{query.query[:30]}...'")
            # Store conversation for context continuity
            user_id = query.user_id or (query.context.get("user_id") if query.context else None)
            try:
                await self._store_conversation(
                    tenant_id=query.tenant_id,
                    session_id=session_id,
                    user_query=query.query,
                    assistant_response=conversational_response,
                    user_id=user_id,
                    tools_used=[]
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to store conversational exchange: {e}")
            return EmmaResponse(
                query=query.query,
                answer=conversational_response,
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=["conversational"],
                tools_used=[],
                confidence_score=1.0,
                execution_time_ms=execution_time_ms,
                iterations=0,
                suggestions=self._generate_suggestions(query.query),
                available_tools=self._available_tools
            )

        try:
            # ALL queries go through Emma which:
            # 1. Tries SIL fast path for structural queries (count, list, exists)
            # 2. Uses domain routing for dynamic prompt loading
            # 3. Falls back to agentic loop with tools for complex queries
            if settings.agents_enabled:
                return await self._execute_with_emma(query, session_id, conversation_history, start_time)

            # Fallback to RAG pipeline
            return await self._fallback_rag_query(query, session_id, start_time)

        except Exception as e:
            logger.error(f"❌ Emma query failed: {e}")
            import traceback
            traceback.print_exc()
            execution_time_ms = int((time.time() - start_time) * 1000)
            return EmmaResponse(
                query=query.query,
                answer=f"Error processing query: {str(e)}",
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=["error"],
                tools_used=[],
                confidence_score=0.0,
                execution_time_ms=execution_time_ms,
                iterations=0,
                suggestions=[],
                available_tools=self._available_tools
            )

    async def _execute_with_emma(
        self,
        query: EmmaQuery,
        session_id: str,
        conversation_history: List[Dict[str, str]],
        start_time: float
    ) -> EmmaResponse:
        """
        Execute query using Emma or LangGraph (if enabled).

        Flow:
        1. Check if LangGraph is enabled for this tenant
           - If enabled, route to LangGraph multi-agent RAG
        2. Otherwise, use Emma:
           a. NexusRouter classifies intent (~10ms) for pre-search if needed
           b. Emma tries SIL fast path for structural queries (no LLM needed)
           c. If content needed, domain routing selects appropriate prompt
           d. Agentic loop with tools handles complex queries

        Emma features:
        - SIL Fast Path: Structural queries answered without LLM (70-90% token savings)
        - Domain Routing: Dynamic prompts based on query domain (~700 vs ~4250 tokens)
        - Skill Loading: Procedural knowledge loaded on-demand
        - ACL context (user_role_ids, is_admin) propagated for document filtering
        """
        # Get user_id from query directly (set by API endpoint) or from context
        user_id = query.user_id or (query.context.get("user_id") if query.context else None)

        # =====================================================================
        # LangGraph Routing (if enabled)
        # =====================================================================
        if is_langgraph_enabled_for_tenant(query.tenant_id):
            logger.info(f"🔀 LangGraph enabled for tenant {query.tenant_id}, routing to LangGraph")
            return await self._execute_with_langgraph(query, session_id, user_id, conversation_history, start_time)

        # Get user context for personalization
        user_context = await self._get_enriched_user_context(
            query.tenant_id, user_id, query.context
        )

        # =====================================================================
        # NexusRouter Pre-Classification (NEW)
        # =====================================================================
        classification: Optional[IntentClassification] = None
        forced_search_results = None

        if self._nexus_router_enabled:
            try:
                classification = await self._nexus_router.classify(
                    query=query.query,
                    tenant_id=query.tenant_id,
                )
                logger.info(
                    f"🎯 NexusRouter: {classification.intent.value} "
                    f"({classification.confidence:.2f}) → {classification.required_action.value}"
                )

                # If search is required, execute it BEFORE LLM
                if classification.needs_search:
                    forced_search_results = await self._execute_forced_search(
                        query=query,
                        classification=classification,
                        user_id=user_id,
                    )

                    # Inject results into user_context for the coordinator
                    if forced_search_results and user_context:
                        user_context["forced_search_results"] = forced_search_results
                        user_context["forced_search_intent"] = classification.intent.value
                        logger.info(
                            f"📋 Injected {len(forced_search_results.get('results', []))} "
                            f"forced search results into context"
                        )
                    elif forced_search_results:
                        user_context = {
                            "forced_search_results": forced_search_results,
                            "forced_search_intent": classification.intent.value,
                        }

            except Exception as e:
                logger.warning(f"⚠️ NexusRouter classification failed: {e}")
                # Continue without pre-classification

        try:
            logger.info(f"🤖 Executing with Emma: {query.query[:50]}...")
            logger.info(f"📋 Query context: tenant={query.tenant_id}, session={session_id[:16]}...")
            logger.info(f"📋 User context: {user_context}")
            logger.info(f"🔐 ACL context: user={user_id}, roles={len(query.user_role_ids or [])}, admin={query.is_admin}")
            if classification:
                logger.info(f"🎯 NexusRouter classification: {classification.intent.value} ({classification.confidence:.2f})")

            # Create execution context for Emma
            exec_context = ExecutionContext(
                tenant_id=query.tenant_id,
                user_id=user_id,
                role_ids=query.user_role_ids or [],
                is_admin=query.is_admin or False,
                thread_id=session_id,
                conversation_id=session_id,
            )

            result: EmmaResult = await self._emma.execute(
                query=query.query,
                context=exec_context,
            )

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Log result details
            logger.info(f"📤 Emma result: success={result.success}")
            logger.info(f"📤 SIL answered: {result.sil_answered}, tokens_saved: {result.tokens_saved}")
            logger.info(f"📤 Domain: {result.domain.value}, tools_called: {result.tools_called}")
            logger.info(f"📤 Skills used: {result.skills_used}")
            logger.info(f"📤 Answer preview: {result.answer[:200] if result.answer else 'None'}...")

            # Build decision path (include NexusRouter if used)
            decision_path = []
            if classification:
                decision_path.append(f"nexus_router:{classification.intent.value}")
                if classification.needs_search:
                    decision_path.append("forced_search")
            decision_path.append("emma")
            if result.sil_answered:
                decision_path.append("sil_fast_path")
            decision_path.append(f"domain:{result.domain.value}")
            if result.tools_called:
                decision_path.extend([f"tool:{t}" for t in result.tools_called])
            decision_path.append("completed" if result.success else "error")

            # Build debug data
            debug_data = None
            if query.enable_debug:
                debug_data = {
                    "emma_success": result.success,
                    "sil_answered": result.sil_answered,
                    "tokens_saved": result.tokens_saved,
                    "domain": result.domain.value,
                    "tools_called": result.tools_called,
                    "skills_used": result.skills_used,
                    "iterations": result.iterations,
                    "thread_id": result.thread_id,
                    "framework": "emma",
                    "metadata": result.metadata,
                    # NexusRouter info
                    "nexus_router": classification.to_dict() if classification else None,
                    "forced_search_count": len(forced_search_results.get("results", [])) if forced_search_results else 0,
                }

            # Store conversation
            await self._store_conversation(
                tenant_id=query.tenant_id,
                session_id=session_id,
                user_query=query.query,
                assistant_response=result.answer,
                user_id=user_id,
                tools_used=result.tools_called
            )

            return EmmaResponse(
                query=query.query,
                answer=result.answer,
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=decision_path,
                tools_used=result.tools_called,
                data=debug_data,
                visualization=None,
                confidence_score=0.9 if result.success else 0.5,
                execution_time_ms=execution_time_ms,
                iterations=result.iterations,
                learning_applied=user_context.get("learning_applied", False) if user_context else False,
                suggestions=self._generate_suggestions(query.query),
                available_tools=self._available_tools
            )

        except Exception as e:
            logger.error(f"❌ Emma execution failed: {e}")
            import traceback
            traceback.print_exc()

            execution_time_ms = int((time.time() - start_time) * 1000)

            return EmmaResponse(
                query=query.query,
                answer=f"Lo siento, hubo un error procesando tu consulta. Por favor, intenta de nuevo. Error: {str(e)[:100]}",
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=["emma", "error"],
                tools_used=[],
                data={"error": str(e), "emma_failed": True} if query.enable_debug else None,
                visualization=None,
                confidence_score=0.0,
                execution_time_ms=execution_time_ms,
                iterations=0,
                learning_applied=False,
                suggestions=[],
                available_tools=self._available_tools
            )

    async def _execute_with_langgraph(
        self,
        query: EmmaQuery,
        session_id: str,
        user_id: Optional[str],
        conversation_history: List[Dict[str, str]],
        start_time: float
    ) -> EmmaResponse:
        """
        Execute query using LangGraph multi-agent RAG.

        LangGraph provides:
        - State-based graph execution with checkpointing
        - Multi-agent coordination (Privacy, Legal, General, etc.)
        - Structured planning and synthesis
        - SLM fast-path for structural queries

        Args:
            query: EmmaQuery with user request
            session_id: Conversation session ID
            user_id: User ID for ACL
            conversation_history: Previous conversation messages
            start_time: Execution start time for latency tracking

        Returns:
            EmmaResponse with answer and metadata
        """
        try:
            logger.info(f"🤖 Executing with LangGraph: {query.query[:50]}...")
            logger.debug(f"📜 Conversation history: {len(conversation_history)} messages")

            result: LangGraphQueryResponse = await execute_langgraph_query(
                query=query.query,
                tenant_id=query.tenant_id,
                user_id=user_id,
                user_role_ids=query.user_role_ids,
                is_admin=query.is_admin or False,
                thread_id=session_id,
                conversation_history=conversation_history,
            )

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Build decision path
            decision_path = ["langgraph"]
            if result.slm_fast_path:
                decision_path.append("slm_fast_path")
            if result.domains:
                decision_path.extend([f"domain:{d}" for d in result.domains])
            if result.agents_used:
                decision_path.extend([f"agent:{a}" for a in result.agents_used])
            decision_path.append("completed" if result.success else "error")

            # Build debug data
            debug_data = None
            if query.enable_debug:
                debug_data = {
                    "langgraph": True,
                    "success": result.success,
                    "slm_fast_path": result.slm_fast_path,
                    "domains": result.domains,
                    "agents_used": result.agents_used,
                    "thread_id": result.thread_id,
                    "langgraph_latency_ms": result.latency_ms,
                    "metadata": result.metadata,
                }

            # Store conversation
            await self._store_conversation(
                tenant_id=query.tenant_id,
                session_id=session_id,
                user_query=query.query,
                assistant_response=result.answer,
                user_id=user_id,
                tools_used=result.agents_used
            )

            return EmmaResponse(
                query=query.query,
                answer=result.answer,
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=decision_path,
                tools_used=result.agents_used,
                data=debug_data,
                visualization=None,
                confidence_score=0.95 if result.success else 0.5,
                execution_time_ms=execution_time_ms,
                iterations=len(result.agents_used),
                learning_applied=False,
                suggestions=self._generate_suggestions(query.query),
                available_tools=self._available_tools
            )

        except Exception as e:
            logger.error(f"❌ LangGraph execution failed: {e}")
            import traceback
            traceback.print_exc()

            execution_time_ms = int((time.time() - start_time) * 1000)

            return EmmaResponse(
                query=query.query,
                answer=f"Error en LangGraph: {str(e)[:100]}",
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=["langgraph", "error"],
                tools_used=[],
                data={"error": str(e), "langgraph_failed": True} if query.enable_debug else None,
                visualization=None,
                confidence_score=0.0,
                execution_time_ms=execution_time_ms,
                iterations=0,
                learning_applied=False,
                suggestions=[],
                available_tools=self._available_tools
            )

    async def _execute_forced_search(
        self,
        query: EmmaQuery,
        classification: IntentClassification,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute forced search based on NexusRouter classification.

        This is called BEFORE the LLM to pre-fetch relevant documents
        when the classification indicates search is needed.

        Args:
            query: Original query
            classification: NexusRouter classification result
            user_id: User ID for ACL

        Returns:
            Dict with search results or None if search fails
        """
        try:
            from app.services.weaviate_service import weaviate_service
            from app.schemas.weaviate import SearchRequest

            # Get search parameters from router
            search_params = self._nexus_router.get_search_params(
                classification, query.query
            )

            logger.info(f"🔍 Executing forced search: {search_params}")

            # Determine limit based on intent
            if classification.intent == Intent.COUNT:
                limit = search_params.get("top_k", 100)
            elif classification.intent == Intent.LIST:
                limit = search_params.get("top_k", 50)
            else:
                limit = search_params.get("top_k", 10)

            # Build SearchRequest
            # Note: include_channels=False to avoid channel_id filter on collections without it
            search_request = SearchRequest(
                query=query.query,
                limit=limit,
                tenant_id=query.tenant_id,
                user_id=user_id,
                user_role_ids=query.user_role_ids,
                is_admin=query.is_admin or False,
                search_type="hybrid",
                include_channels=False,  # Disable channel filtering for forced search
            )

            # Execute search
            search_response = await weaviate_service.search(search_request)

            # Extract results
            results = []
            if search_response and hasattr(search_response, 'results'):
                for r in search_response.results:
                    results.append({
                        "id": r.id,
                        "title": getattr(r, 'title', None),
                        "content_preview": getattr(r, 'content', '')[:200] if hasattr(r, 'content') else '',
                        "score": getattr(r, 'score', 0.0),
                        "metadata": getattr(r, 'metadata', {}),
                    })

            # Build response based on intent
            if classification.intent == Intent.COUNT:
                return {
                    "type": "count",
                    "count": len(results),
                    "results": results[:10],  # Return sample for context
                    "query": query.query,
                    "document_types": classification.document_types,
                }
            elif classification.intent == Intent.LIST:
                return {
                    "type": "list",
                    "count": len(results),
                    "results": results,
                    "query": query.query,
                    "document_types": classification.document_types,
                }
            else:
                return {
                    "type": "search",
                    "count": len(results),
                    "results": results,
                    "query": query.query,
                    "document_types": classification.document_types,
                    "entities": classification.entities,
                }

        except Exception as e:
            logger.error(f"❌ Forced search failed: {e}")
            return None

    async def execute_query_stream(self, query: EmmaQuery) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute Emma AI query with streaming progress."""
        session_id = query.session_id or str(uuid.uuid4())

        # AGGRESSIVE STREAMING: Emit progress immediately
        yield {
            "event": "progress",
            "data": {"message": "Procesando consulta...", "stage": "init", "session_id": session_id}
        }

        if not self._initialized:
            await self.initialize()

        # Load conversation history (in background, don't block streaming)
        conversation_history = []
        try:
            if session_id:
                conversation_history = await self._memory.get_conversation_history(
                    tenant_id=query.tenant_id,
                    session_id=session_id,
                    max_messages=10
                )
        except Exception as e:
            logger.warning(f"⚠️ Failed to load conversation history: {e}")

        # Check conversational patterns FIRST (greetings, introductions, thanks)
        # These don't need RAG/LLM - respond directly via streaming
        conversational_response = self._check_conversational_query(query.query)
        if conversational_response:
            logger.info(f"💬 Streaming conversational response for: '{query.query[:30]}...'")
            # Stream the response word by word for consistent UX
            words = conversational_response.split(' ')
            for i, word in enumerate(words):
                token = f" {word}" if i > 0 else word
                yield {
                    "event": "token",
                    "data": {"text": token, "session_id": session_id}
                }
            yield {
                "event": "complete",
                "data": {
                    "session_id": session_id,
                    "final_result": {
                        "confidence_score": 1.0,
                        "decision_path": ["conversational"],
                        "tools_used": [],
                    },
                    "execution_time_ms": 0,
                    "confidence_score": 1.0,
                }
            }
            # Store conversation for context continuity
            try:
                user_id = query.user_id or (query.context.get("user_id") if query.context else None)
                await self._store_conversation(
                    tenant_id=query.tenant_id,
                    session_id=session_id,
                    user_query=query.query,
                    assistant_response=conversational_response,
                    user_id=user_id,
                    tools_used=[]
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to store conversational exchange: {e}")
            return

        try:
            # Get user_id from query directly (set by API endpoint) or from context
            user_id = query.user_id or (query.context.get("user_id") if query.context else None)
            document_id = query.context.get("document_id") if query.context else None

            # AGGRESSIVE STREAMING: Show document loading progress
            if document_id:
                yield {
                    "event": "progress",
                    "data": {"message": "Cargando documento...", "stage": "loading_document", "session_id": session_id}
                }

            # Get enriched user context (includes document content loading)
            user_context = await self._get_enriched_user_context(
                query.tenant_id, user_id, query.context
            )

            # AGGRESSIVE STREAMING: Show document identified
            if user_context and user_context.get("document_title"):
                yield {
                    "event": "progress",
                    "data": {
                        "message": f"Analizando: {user_context['document_title']}",
                        "stage": "analyzing",
                        "document": user_context["document_title"],
                        "session_id": session_id
                    }
                }

            logger.debug(f"🔐 Stream ACL context: user={user_id}, roles={len(query.user_role_ids or [])}, admin={query.is_admin}")

            # Collect response for learning/memory storage
            full_response = []
            tools_used = []

            # Create execution context for Emma
            exec_context = ExecutionContext(
                tenant_id=query.tenant_id,
                user_id=user_id,
                role_ids=query.user_role_ids or [],
                is_admin=query.is_admin or False,
                thread_id=session_id,
                conversation_id=session_id,
            )

            async for event in self._emma.execute_stream(
                query=query.query,
                context=exec_context,
            ):
                # Transform Emma event format to expected format
                # Emma uses {"type": "...", "content": "..."}
                # UI expects {"event": "...", "data": {...}}
                event_type = event.get("type", event.get("event", ""))

                # Transform to expected format
                if event_type == "content":
                    # Real LLM streaming - pass tokens directly (no fake word splitting)
                    content = event.get("content", "")
                    if content:
                        full_response.append(content)
                        yield {
                            "event": "token",
                            "data": {
                                "text": content,
                                "session_id": session_id,
                            }
                        }
                elif event_type == "thinking":
                    yield {
                        "event": "thinking",
                        "data": {"content": event.get("content", ""), "session_id": session_id}
                    }
                elif event_type == "tool_call":
                    tool_name = event.get("name", "")
                    tools_used.append(tool_name)
                    yield {
                        "event": "tool_use",
                        "data": {
                            "tool": tool_name,
                            "arguments": event.get("arguments", {}),
                            "session_id": session_id
                        }
                    }
                elif event_type == "tool_result":
                    yield {
                        "event": "tool_result",
                        "data": {
                            "tool": event.get("name", ""),
                            "result": event.get("result", {}),
                            "session_id": session_id
                        }
                    }
                elif event_type == "done":
                    result = event.get("result", {})
                    process_info = result.get("process_info", {})
                    # Extract tool names as strings (active_tools may contain objects)
                    active_tools = process_info.get("active_tools", [])
                    tools_list = [
                        t.get("name") if isinstance(t, dict) else str(t)
                        for t in active_tools
                    ] if active_tools else []
                    # Don't include 'answer' - let UI use accumulated streaming_text
                    # This prevents the "flash" of replacing streamed content
                    yield {
                        "event": "complete",
                        "data": {
                            "session_id": session_id,
                            "final_result": {
                                "confidence_score": 0.95 if process_info.get("sil_used") else 0.85,
                                "decision_path": ["sil_fast_path"] if process_info.get("sil_used") else ["emma"],
                                "tools_used": tools_list,
                            },
                            "execution_time_ms": process_info.get("execution_time_ms", 0),
                            "confidence_score": 0.95 if process_info.get("sil_used") else 0.85,
                        }
                    }
                elif event_type == "error":
                    yield {
                        "event": "error",
                        "data": {"error": event.get("error", "Unknown error"), "session_id": session_id}
                    }
                else:
                    # Pass through any other events
                    if "data" not in event:
                        event["data"] = {}
                    event["data"]["session_id"] = session_id
                    if "type" in event and "event" not in event:
                        event["event"] = event.pop("type")
                    yield event

            # Store conversation and record interaction for learning
            if full_response:
                response_text = "".join(full_response)
                try:
                    await self._store_conversation(
                        tenant_id=query.tenant_id,
                        session_id=session_id,
                        user_query=query.query,
                        assistant_response=response_text,
                        user_id=user_id,
                        tools_used=tools_used
                    )
                    logger.debug(f"💾 Stream conversation stored for learning")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to store stream conversation: {e}")

        except Exception as e:
            logger.error(f"❌ Emma stream failed: {e}")
            yield {
                "event": "error",
                "data": {"error": str(e), "message": f"Error: {str(e)}"}
            }

    async def _fallback_rag_query(
        self,
        query: EmmaQuery,
        session_id: str,
        start_time: float
    ) -> EmmaResponse:
        """Fallback to RAG pipeline."""
        user_id = query.context.get("user_id") if query.context else None

        try:
            from app.services.rag.rag_pipeline import RAGPipeline

            pipeline = RAGPipeline()

            include_public = self._should_include_public_knowledge(query.query, query.context)

            result = await pipeline.process_query(
                query=query.query,
                tenant_id=query.tenant_id,
                validate_claims=True,
                include_public_knowledge=include_public
            )

            execution_time_ms = int((time.time() - start_time) * 1000)

            await self._store_conversation(
                tenant_id=query.tenant_id,
                session_id=session_id,
                user_query=query.query,
                assistant_response=result.answer,
                user_id=user_id,
                tools_used=["rag_answer"]
            )

            return EmmaResponse(
                query=query.query,
                answer=result.answer,
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=["rag_pipeline"],
                tools_used=["rag_answer"],
                data={
                    "sources": [
                        {"id": s.id, "title": s.title, "score": s.score}
                        for s in (result.sources or [])[:5]
                    ]
                } if query.enable_debug else None,
                visualization=None,
                confidence_score=result.confidence if hasattr(result, 'confidence') else 0.7,
                execution_time_ms=execution_time_ms,
                iterations=1,
                learning_applied=False,
                suggestions=self._generate_suggestions(query.query),
                available_tools=["rag_answer", "nexus_semantic_search", "nexus_hybrid_search"]
            )
        except Exception as e:
            logger.error(f"❌ RAG fallback failed: {e}")
            raise

    def _should_include_public_knowledge(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Determine if public knowledge should be included."""
        if context and context.get("include_public_knowledge") is not None:
            return context.get("include_public_knowledge")

        query_lower = query.lower()
        legal_keywords = [
            "legal", "ley", "legislación", "normativa", "contrato", "cláusula",
            "gdpr", "rgpd", "lopd", "cumplimiento", "compliance", "privacidad",
            "jurídico", "jurisprudencia", "regulation", "law", "contract"
        ]

        for keyword in legal_keywords:
            if keyword in query_lower:
                return True

        return settings.rag_public_knowledge_enabled

    def _generate_suggestions(self, query: str) -> List[Suggestion]:
        """Generate contextual suggestions."""
        suggestions = []
        query_lower = query.lower()

        if "contrato" in query_lower or "contract" in query_lower:
            suggestions.append(Suggestion(
                text="Analizar riesgos del contrato",
                action="analyze_contract_risks",
                icon="file-warning"
            ))
            suggestions.append(Suggestion(
                text="Verificar cumplimiento normativo",
                action="check_compliance",
                icon="shield-check"
            ))
        elif "buscar" in query_lower or "search" in query_lower:
            suggestions.append(Suggestion(
                text="Buscar en todos los documentos",
                action="search_all",
                icon="search"
            ))
        else:
            suggestions.append(Suggestion(
                text="Resumir documentos relacionados",
                action="summarize",
                icon="file-text"
            ))
            suggestions.append(Suggestion(
                text="Comparar con documentos similares",
                action="compare",
                icon="git-compare"
            ))

        return suggestions[:3]

    async def _store_conversation(
        self,
        tenant_id: str,
        session_id: str,
        user_query: str,
        assistant_response: str,
        user_id: Optional[str] = None,
        tools_used: Optional[List[str]] = None
    ) -> None:
        """Store conversation in Memory Protocol."""
        try:
            await self._memory.add_exchange(
                tenant_id=tenant_id,
                session_id=session_id,
                user_message=user_query,
                assistant_message=assistant_response,
                user_id=user_id,
                tools_used=tools_used or []
            )
            logger.debug(f"💾 Stored conversation for session {session_id[:8]}...")
        except Exception as e:
            logger.warning(f"⚠️ Failed to store conversation: {e}")

    async def execute_tool(self, tool_execution: ToolExecution) -> Dict[str, Any]:
        """Execute a specific tool."""
        if not self._initialized:
            await self.initialize()

        try:
            from app.agents.tools import (
                SemanticSearchTool, HybridSearchTool, KeywordSearchTool,
                AnalyzeDocumentTool, CompareDocumentsTool, RAGAnswerTool
            )
            import json

            # Map tool names to tool classes (nexus_ prefix for search tools)
            tool_class_map = {
                "nexus_semantic_search": SemanticSearchTool,
                "nexus_hybrid_search": HybridSearchTool,
                "nexus_keyword_search": KeywordSearchTool,
                "analyze_document": AnalyzeDocumentTool,
                "compare_documents": CompareDocumentsTool,
                "rag_answer": RAGAnswerTool,
            }

            tool_class = tool_class_map.get(tool_execution.tool_name)
            if not tool_class:
                raise ValueError(f"Unknown tool: {tool_execution.tool_name}")

            # Instantiate tool and call with parameters
            tool_instance = tool_class()
            params = {"tenant_id": tool_execution.tenant_id, **tool_execution.parameters}
            result = tool_instance.call(json.dumps(params))

            return {"status": "success", "tool": tool_execution.tool_name, "result": result}
        except Exception as e:
            logger.error(f"❌ Tool execution failed: {e}")
            return {"status": "error", "tool": tool_execution.tool_name, "error": str(e)}

    async def list_tools(self) -> List[ToolInfo]:
        """List all available tools (using nexus_ prefix for search tools)."""
        return [
            ToolInfo(name="nexus_semantic_search", description="Search by semantic meaning",
                     parameters={"query": "string", "tenant_id": "string", "top_k": "int"},
                     return_type="list", category="search"),
            ToolInfo(name="nexus_hybrid_search", description="Search combining vectors and keywords",
                     parameters={"query": "string", "tenant_id": "string", "top_k": "int"},
                     return_type="list", category="search"),
            ToolInfo(name="nexus_keyword_search", description="Search by exact keywords",
                     parameters={"query": "string", "tenant_id": "string", "top_k": "int"},
                     return_type="list", category="search"),
            ToolInfo(name="analyze_document", description="Deep analysis of a document",
                     parameters={"document_id": "string", "tenant_id": "string"},
                     return_type="dict", category="analysis"),
            ToolInfo(name="rag_answer", description="Generate answer using RAG pipeline",
                     parameters={"query": "string", "tenant_id": "string"},
                     return_type="string", category="rag"),
        ]

    async def health_check(self) -> Dict[str, Any]:
        """Health check for Emma service."""
        from app.agents.langgraph import is_langgraph_enabled

        emma_status = {
            "initialized": self._emma._initialized if self._emma else False,
            "sil_enabled": self._emma.config.enable_sil_fast_path if self._emma else False,
            "domain_routing_enabled": self._emma.config.enable_domain_routing if self._emma else False,
            "skills_enabled": self._emma.config.enable_skills if self._emma else False,
        }

        # LangGraph status
        langgraph_status = {
            "enabled": is_langgraph_enabled(),
            "description": "Multi-agent RAG with StateGraph",
        }

        # List of available agents/capabilities
        agents = [
            "search",           # Búsqueda semántica e híbrida
            "read_document",    # Lectura de documentos
            "analyze",          # Análisis profundo con RAG
            "legal_search",     # Conocimiento legal público
            "ask_user",         # Clarificación HITL
        ]

        return {
            "status": "healthy",
            "agents_enabled": settings.agents_enabled,
            "langgraph_enabled": is_langgraph_enabled(),
            "agents": agents,
            "initialized": self._initialized,
            "emma_available": self._emma is not None,
            "available_tools_count": len(self._available_tools),
            "orchestration_type": "LangGraph" if is_langgraph_enabled() else "Emma",
            "emma_status": emma_status,
            "langgraph_status": langgraph_status,
        }

    async def get_decision_tree_state(self, session_id: str) -> DecisionTreeState:
        """Get decision tree state for debugging."""
        from datetime import datetime
        return DecisionTreeState(
            session_id=session_id,
            current_node="coordinator",
            visited_nodes=["start", "intent_classification", "coordinator"],
            execution_path=[],
            context={},
            tools_executed=[],
            start_time=datetime.now(),
            last_update=datetime.now()
        )

    async def create_visualization(self, viz_request: VisualizationRequest) -> Dict[str, Any]:
        """Create visualization."""
        viz_type = viz_request.visualization_type or "table"
        return {
            "type": viz_type.value if hasattr(viz_type, 'value') else viz_type,
            "title": viz_request.title or "Data Visualization",
            "data": viz_request.data,
            "config": viz_request.preferences
        }

    async def process_feedback(self, feedback: FeedbackRequest) -> str:
        """Process user feedback."""
        feedback_id = str(uuid.uuid4())
        logger.info(f"📝 Feedback received: {feedback_id} - Rating: {feedback.rating}/5")
        return feedback_id

    async def get_session_analytics(self, session_id: str) -> Dict[str, Any]:
        """Get session analytics."""
        return {
            "session_id": session_id,
            "queries_count": 0,
            "tools_used": [],
            "average_response_time_ms": 0,
            "feedback_rating": None
        }


# Global service instance
emma_service = EmmaService()

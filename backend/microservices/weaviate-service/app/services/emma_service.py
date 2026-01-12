"""
Emma AI Service - Personal AI Assistant for NexusDocs360

Emma is the user-facing name for the AI assistant.
This module provides the Emma service interface using:
- EmmaCoordinator (PRIMARY): Single coordinator agent with .as_tool() delegation
- RAGPipeline (FALLBACK): Simple RAG for when agents are disabled

ARCHITECTURE:
EmmaCoordinator uses Microsoft Agent Framework's native .as_tool() pattern:
1. Single ChatAgent as coordinator
2. Specialist agents converted to tools via .as_tool()
3. AgentThread maintains conversation context automatically
4. Redis persistence for cross-session context
5. LLM naturally decides when to delegate to specialists

NOTE: EmmaHandoffWorkflow is retained for reference but NOT used as fallback.
Using different context systems between coordinator and handoff causes context loss.
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

# PRIMARY: EmmaCoordinator with .as_tool() delegation
from app.agents.emma_coordinator import (
    EmmaCoordinator, EmmaCoordinatorResult,
    get_emma_coordinator
)

logger = logging.getLogger(__name__)


class EmmaService:
    """
    Emma AI Service - Personal AI Assistant

    Uses EmmaCoordinator as the ONLY execution path for agent-based queries.
    Falls back to RAGPipeline only when agents are disabled (settings.agents_enabled=False).
    """

    def __init__(self):
        # PRIMARY: EmmaCoordinator with .as_tool() delegation
        self._coordinator: EmmaCoordinator = get_emma_coordinator()

        self._initialized = False
        self._available_tools = []
        self._conversational_config = None
        self._analysis_keywords = []

        # Tool Framework integration
        self._tool_integration: ToolIntegration = get_tool_integration()
        # Memory Protocol integration
        self._memory: MemoryService = get_memory_service()

        self._load_config()
        logger.info("Initializing Emma AI Service (EmmaCoordinator primary, RAGPipeline fallback)")

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

                # Only load if content is reasonable size (< 6000 chars)
                # Larger documents should use analyze_document tool
                if len(content) < 6000:
                    user_context["document_content"] = content
                    user_context["document_title"] = title
                    logger.info(f"📄 Loaded document content: {title} ({len(content)} chars)")
                else:
                    logger.info(f"📄 Document too large for direct analysis: {title} ({len(content)} chars)")

        except Exception as e:
            logger.warning(f"⚠️ Could not load document content: {e}")

    async def initialize(self):
        """Initialize Emma components."""
        if self._initialized:
            return

        try:
            # PRIMARY: Initialize EmmaCoordinator
            await self._coordinator.initialize()
            logger.info("✅ EmmaCoordinator initialized (8 subagent tools with .as_tool())")

            # Initialize Tool Framework
            await self._tool_integration.initialize()
            logger.info("✅ Tool Framework initialized")

            # Initialize Memory Protocol
            await self._memory.initialize()
            logger.info("✅ Memory Protocol initialized")

            # Build available tools list
            legacy_tools = [
                "semantic_search", "hybrid_search", "keyword_search",
                "search_public_knowledge", "search_with_legal_context",
                "analyze_document", "compare_documents", "rag_answer",
                "get_document_content", "summarize_documents"
            ]
            framework_tools = self._tool_integration.get_tool_info()
            framework_tool_names = [t["name"] for t in framework_tools]
            self._available_tools = legacy_tools + framework_tool_names

            logger.info(f"✅ Emma AI initialized: EmmaCoordinator (primary) + RAGPipeline (fallback)")
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

        # NOTE: Removed conversational query interception here.
        # ALL queries now go through EmmaCoordinator to maintain AgentThread context.
        # The Coordinator handles greetings, identity questions, etc. while preserving memory.

        try:
            # ALL queries go through EmmaCoordinator to maintain AgentThread context
            # The Coordinator handles intent classification internally and preserves memory
            if settings.agents_enabled:
                return await self._execute_with_coordinator(query, session_id, start_time)

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

    async def _execute_with_coordinator(
        self,
        query: EmmaQuery,
        session_id: str,
        start_time: float
    ) -> EmmaResponse:
        """
        Execute query using EmmaCoordinator (PRIMARY).

        EmmaCoordinator uses .as_tool() to delegate to specialized subagents.
        Context is maintained automatically via AgentThread + Redis persistence.
        ACL context (user_role_ids, is_admin) is propagated for document filtering.
        """
        # Get user_id from query directly (set by API endpoint) or from context
        user_id = query.user_id or (query.context.get("user_id") if query.context else None)

        # Get user context for personalization
        user_context = await self._get_enriched_user_context(
            query.tenant_id, user_id, query.context
        )

        try:
            # Get orchestration hint from context (optional)
            orchestration_hint = None
            if query.context:
                orchestration_hint = query.context.get("orchestration")

            logger.info(f"🤖 Executing with EmmaCoordinator: {query.query[:50]}...")
            logger.info(f"📋 Query context: tenant={query.tenant_id}, session={session_id[:16]}...")
            logger.info(f"📋 User context: {user_context}")
            logger.info(f"🔐 ACL context: user={user_id}, roles={len(query.user_role_ids or [])}, admin={query.is_admin}")
            logger.info(f"📋 Orchestration hint: {orchestration_hint}")

            result: EmmaCoordinatorResult = await self._coordinator.execute(
                query=query.query,
                tenant_id=query.tenant_id,
                session_id=session_id,
                user_id=user_id,
                user_role_ids=query.user_role_ids,
                is_admin=query.is_admin,
                user_context=user_context,
                orchestration_hint=orchestration_hint
            )

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Log result details
            logger.info(f"📤 Coordinator result: success={result.success}")
            logger.info(f"📤 Agents delegated: {result.agents_delegated}")
            logger.info(f"📤 Tools called: {result.tools_called}")
            logger.info(f"📤 Answer preview: {result.answer[:200] if result.answer else 'None'}...")

            # Build decision path
            decision_path = ["emma_coordinator"]
            if result.agents_delegated:
                decision_path.extend([f"delegated:{a}" for a in result.agents_delegated])
            decision_path.append("completed" if result.success else "error")

            # Build debug data
            debug_data = None
            if query.enable_debug:
                debug_data = {
                    "coordinator_success": result.success,
                    "agents_delegated": result.agents_delegated,
                    "tools_called": result.tools_called,
                    "thread_id": result.thread_id,
                    "framework": "microsoft_agent_framework",
                    "orchestration_pattern": result.metadata.get("pattern", "handoff"),
                    "context_maintained": True,
                    "metadata": result.metadata
                }

            # Store conversation
            await self._store_conversation(
                tenant_id=query.tenant_id,
                session_id=session_id,
                user_query=query.query,
                assistant_response=result.answer,
                user_id=user_id,
                tools_used=result.agents_delegated or result.tools_called
            )

            return EmmaResponse(
                query=query.query,
                answer=result.answer,
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=decision_path,
                tools_used=result.agents_delegated or result.tools_called,
                data=debug_data,
                visualization=None,
                confidence_score=0.9 if result.success else 0.5,
                execution_time_ms=execution_time_ms,
                iterations=len(result.agents_delegated) if result.agents_delegated else 1,
                learning_applied=False,
                suggestions=self._generate_suggestions(query.query),
                available_tools=self._available_tools
            )

        except Exception as e:
            logger.error(f"❌ EmmaCoordinator execution failed: {e}")
            import traceback
            traceback.print_exc()

            # Log the error but do NOT fallback to EmmaHandoffWorkflow
            # Reason: Fallback can cause context degradation because it uses
            # a different thread storage and context format than EmmaCoordinator.
            # Instead, return an error response and let the user retry.
            execution_time_ms = int((time.time() - start_time) * 1000)

            return EmmaResponse(
                query=query.query,
                answer=f"Lo siento, hubo un error procesando tu consulta. Por favor, intenta de nuevo. Error: {str(e)[:100]}",
                session_id=session_id,
                tenant_id=query.tenant_id,
                decision_path=["emma_coordinator", "error"],
                tools_used=[],
                data={"error": str(e), "coordinator_failed": True} if query.enable_debug else None,
                visualization=None,
                confidence_score=0.0,
                execution_time_ms=execution_time_ms,
                iterations=0,
                learning_applied=False,
                suggestions=[],
                available_tools=self._available_tools
            )

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

            async for event in self._coordinator.execute_stream(
                query=query.query,
                tenant_id=query.tenant_id,
                session_id=session_id,
                user_id=user_id,
                user_role_ids=query.user_role_ids,
                is_admin=query.is_admin,
                user_context=user_context
            ):
                if "data" not in event:
                    event["data"] = {}
                event["data"]["session_id"] = session_id
                yield event

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
                available_tools=["rag_answer", "semantic_search", "hybrid_search"]
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
            from app.agents.tools import search_tools, analysis_tools, rag_tools

            tool_map = {
                "semantic_search": search_tools.semantic_search,
                "hybrid_search": search_tools.hybrid_search,
                "keyword_search": search_tools.keyword_search,
                "analyze_document": analysis_tools.analyze_document,
                "compare_documents": analysis_tools.compare_documents,
                "rag_answer": rag_tools.rag_answer,
            }

            tool_func = tool_map.get(tool_execution.tool_name)
            if not tool_func:
                raise ValueError(f"Unknown tool: {tool_execution.tool_name}")

            result = await tool_func(
                tenant_id=tool_execution.tenant_id,
                **tool_execution.parameters
            )

            return {"status": "success", "tool": tool_execution.tool_name, "result": result}
        except Exception as e:
            logger.error(f"❌ Tool execution failed: {e}")
            return {"status": "error", "tool": tool_execution.tool_name, "error": str(e)}

    async def list_tools(self) -> List[ToolInfo]:
        """List all available tools."""
        return [
            ToolInfo(name="semantic_search", description="Search by semantic meaning",
                     parameters={"query": "string", "tenant_id": "string", "top_k": "int"},
                     return_type="list", category="search"),
            ToolInfo(name="hybrid_search", description="Search combining vectors and keywords",
                     parameters={"query": "string", "tenant_id": "string", "top_k": "int"},
                     return_type="list", category="search"),
            ToolInfo(name="keyword_search", description="Search by exact keywords",
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
        coordinator_status = self._coordinator.get_status() if self._coordinator else {}
        return {
            "status": "healthy",
            "agents_enabled": settings.agents_enabled,
            "initialized": self._initialized,
            "coordinator_available": self._coordinator is not None,
            "available_tools_count": len(self._available_tools),
            "orchestration_type": "EmmaCoordinator",
            "coordinator_status": coordinator_status
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

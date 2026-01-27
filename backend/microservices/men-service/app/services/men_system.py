"""
MEN System - Main Coordinator.

Orchestrates the full MEN pipeline:
1. Orchestrator classifies domain
2. Expert provides technical data (if available)
3. LLM Modeler synthesizes final response

Total VRAM: ~4.5-5 GB (vs 16GB for single 7B model)
"""

import logging
from typing import Dict, Optional, Set

from ..core.config import MENConfig, settings

from .expert import MicroLLMExpert
from .llm_modeler import LLMModeler
from .orchestrator import Orchestrator
from .tenant_expert_manager import TenantExpertManager

logger = logging.getLogger(__name__)

# Global instance
_men_system: Optional["MENSystem"] = None


def get_men_system() -> "MENSystem":
    """Get or create the global MENSystem instance."""
    global _men_system
    if _men_system is None:
        config = MENConfig.from_settings(settings)
        _men_system = MENSystem(config)
    return _men_system


def initialize_men_system() -> "MENSystem":
    """Initialize the MEN system (call at startup)."""
    system = get_men_system()
    system.load()
    return system


class MENSystem:
    """
    Main MEN System coordinator.

    Manages the full query pipeline:
    1. Domain classification (Orchestrator)
    2. Expert knowledge retrieval (if applicable)
    3. Response synthesis (LLM Modeler)

    Architecture benefits:
    - Low VRAM footprint (~4.5 GB base)
    - Dynamic expert loading/unloading
    - Conversational memory per session
    - Tenant-specific customization via LoRA
    """

    def __init__(self, config: MENConfig):
        """
        Initialize MEN System with configuration.

        Args:
            config: MENConfig instance with model paths and settings
        """
        self.config = config

        # Core components
        self.orchestrator = Orchestrator(
            model_name=config.orchestrator_model,
            domains=config.domains,
            confidence_threshold=config.orchestrator_confidence_threshold
        )

        self.llm_modeler = LLMModeler(
            model_name=config.llm_modeler_model,
            max_history_turns=config.llm_modeler_history_turns,
            max_tokens=config.llm_modeler_max_tokens,
            temperature=config.llm_modeler_temperature
        ) if config.modeler_enabled else None

        self.tenant_manager = TenantExpertManager(
            experts_dir=config.experts_dir
        ) if config.experts_enabled else None

        # Expert cache
        self._experts: Dict[str, MicroLLMExpert] = {}
        self._loaded_experts: Set[str] = set()

        self._loaded = False

    def load(self) -> None:
        """
        Load core components at startup.

        Loads orchestrator and modeler (always in memory).
        Experts are loaded on-demand.
        """
        if self._loaded:
            logger.info("MEN System already loaded")
            return

        logger.info("=" * 60)
        logger.info("Loading MEN System...")
        logger.info("=" * 60)

        # 1. Load Orchestrator (~1.5 GB)
        logger.info("Step 1/3: Loading Orchestrator...")
        self.orchestrator.load()
        logger.info("  ✓ Orchestrator loaded (~1.5 GB VRAM)")

        # 2. Load LLM Modeler (~2.5 GB)
        if self.llm_modeler:
            logger.info("Step 2/3: Loading LLM Modeler...")
            self.llm_modeler.load()
            logger.info("  ✓ LLM Modeler loaded (~2.5 GB VRAM)")
        else:
            logger.info("Step 2/3: LLM Modeler disabled")

        # 3. Initialize Tenant Manager (no VRAM, just filesystem scan)
        if self.tenant_manager:
            logger.info("Step 3/3: Initializing Expert Manager...")
            self.tenant_manager.initialize()
            logger.info("  ✓ Expert Manager initialized")
        else:
            logger.info("Step 3/3: Expert Manager disabled")

        self._loaded = True
        logger.info("=" * 60)
        logger.info("MEN System ready!")
        logger.info(f"  Base VRAM: ~4.0 GB")
        logger.info(f"  Peak VRAM: ~4.5-5.0 GB (with expert)")
        logger.info("=" * 60)

    def unload(self) -> None:
        """Unload all components."""
        logger.info("Unloading MEN System...")

        # Unload experts
        for expert in self._experts.values():
            expert.unload()
        self._experts.clear()
        self._loaded_experts.clear()

        # Unload modeler
        if self.llm_modeler:
            self.llm_modeler.unload()

        # Unload orchestrator
        self.orchestrator.unload()

        self._loaded = False
        logger.info("MEN System unloaded")

    async def query(
        self,
        user_input: str,
        tenant_id: str,
        session_id: str = "default",
        tenant_schema: Optional[dict] = None
    ) -> dict:
        """
        Process a user query through the full MEN pipeline.

        Pipeline:
        1. Orchestrator classifies domain
        2. If expert available → get technical info
        3. LLM Modeler synthesizes final response

        Args:
            user_input: User's query
            tenant_id: Tenant identifier
            session_id: Session for conversational memory
            tenant_schema: Tenant metadata (document types, clients, etc.)

        Returns:
            Dict with response and metadata
        """
        if not self._loaded:
            self.load()

        logger.info(f"Processing query: '{user_input[:50]}...' (tenant={tenant_id})")

        # 1. Orchestrator: classify domain
        domains = self.orchestrator.route(user_input)
        selected_domain = domains[0] if domains else "none"
        logger.info(f"  Domain classified: {selected_domain}")

        # 2. Expert: get technical information (if available)
        raw_expert_info = None
        expert_used = None

        if selected_domain != "none" and self.tenant_manager:
            # Select expert (tenant-specific or generic)
            expert_path, expert_source = self.tenant_manager.select_expert(
                tenant_id=tenant_id,
                query=user_input,
                document_type=self._infer_doc_type(user_input, tenant_schema),
                domain=selected_domain
            )

            if expert_path:
                expert = self._get_or_load_expert(expert_path, selected_domain)
                raw_expert_info = expert.query(
                    user_input,
                    max_tokens=self.config.expert_max_tokens
                )
                expert_used = expert_source
                logger.info(f"  Expert used: {expert_used}")

                # Unload expert to free VRAM
                if self.config.unload_experts_after_query:
                    expert.unload()
                    self._loaded_experts.discard(selected_domain)
                    logger.debug(f"  Expert '{selected_domain}' unloaded")

        # 3. LLM Modeler: synthesize final response
        if self.llm_modeler:
            # Build tenant context from schema
            tenant_context = None
            if tenant_schema:
                tenant_context = self._format_tenant_context(tenant_schema)

            # Generate response with memory
            full_session_id = f"{tenant_id}:{session_id}"
            final_response = self.llm_modeler.generate_response(
                user_input=user_input,
                session_id=full_session_id,
                expert_data=raw_expert_info,
                tenant_context=tenant_context
            )
        else:
            # No modeler - return expert data directly or simple response
            final_response = raw_expert_info or f"Query recibida sobre '{selected_domain}'. Sin experto disponible."

        logger.info(f"  Response generated ({len(final_response)} chars)")

        return {
            "response": final_response,
            "domain": selected_domain,
            "expert_used": expert_used,
            "has_expert_data": raw_expert_info is not None,
            "session_id": session_id,
            "tenant_id": tenant_id,
        }

    async def decide(self, user_input: str) -> dict:
        """
        Classification-only endpoint (no response generation).

        Useful for routing decisions without full query processing.

        Args:
            user_input: User's query

        Returns:
            Dict with domain classification
        """
        if not self._loaded:
            self.load()

        domain, confidence = self.orchestrator.route_with_confidence(user_input)

        return {
            "domain": domain,
            "confidence": confidence,
            "requires_expert": domain not in ["none", "general"],
        }

    def clear_session(self, tenant_id: str, session_id: str) -> bool:
        """Clear conversational memory for a session."""
        if not self.llm_modeler:
            return False

        full_session_id = f"{tenant_id}:{session_id}"
        return self.llm_modeler.clear_history(full_session_id)

    def get_session_history(self, tenant_id: str, session_id: str) -> list:
        """Get conversation history for a session."""
        if not self.llm_modeler:
            return []

        full_session_id = f"{tenant_id}:{session_id}"
        return self.llm_modeler.get_history(full_session_id)

    def _get_or_load_expert(self, expert_path: str, domain: str) -> MicroLLMExpert:
        """Get cached expert or load new one."""
        cache_key = f"{domain}:{expert_path}"

        if cache_key not in self._experts:
            self._experts[cache_key] = MicroLLMExpert(
                domain=domain,
                model_path=expert_path,
                base_model=self.config.expert_base_model,
                max_tokens=self.config.expert_max_tokens
            )

        if cache_key not in self._loaded_experts:
            self._experts[cache_key].load()
            self._loaded_experts.add(cache_key)

        return self._experts[cache_key]

    def _infer_doc_type(
        self,
        query: str,
        tenant_schema: Optional[dict]
    ) -> Optional[str]:
        """Infer document type from query based on tenant schema."""
        if not tenant_schema:
            return None

        query_lower = query.lower()
        for doc_type in tenant_schema.get("document_types", []):
            if doc_type.lower() in query_lower:
                return doc_type

        return None

    def _format_tenant_context(self, schema: dict) -> str:
        """Format tenant schema as context string."""
        parts = []

        if schema.get("tenant_name"):
            parts.append(f"Cliente: {schema['tenant_name']}")

        if schema.get("document_types"):
            doc_types = schema["document_types"][:5]
            parts.append(f"Tipos de documentos: {', '.join(doc_types)}")

        if schema.get("known_clients"):
            clients = schema["known_clients"][:5]
            parts.append(f"Clientes conocidos: {', '.join(clients)}")

        if schema.get("terminology"):
            terms = [f"{k}={v}" for k, v in list(schema["terminology"].items())[:3]]
            parts.append(f"Terminología: {', '.join(terms)}")

        return ". ".join(parts) if parts else None

    @property
    def is_loaded(self) -> bool:
        """Check if system is loaded."""
        return self._loaded

    def get_status(self) -> dict:
        """Get system status."""
        return {
            "loaded": self._loaded,
            "orchestrator_loaded": self.orchestrator.is_loaded if self.orchestrator else False,
            "modeler_loaded": self.llm_modeler.is_loaded if self.llm_modeler else False,
            "modeler_enabled": self.config.modeler_enabled,
            "experts_enabled": self.config.experts_enabled,
            "loaded_experts": list(self._loaded_experts),
            "active_sessions": self.llm_modeler.get_session_count() if self.llm_modeler else 0,
            "available_domains": self.tenant_manager.get_all_domains() if self.tenant_manager else [],
        }

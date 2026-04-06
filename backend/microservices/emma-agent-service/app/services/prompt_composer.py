"""
Prompt Composer — Main orchestrator for the Prompt Management system.

Combines:
- Langfuse Prompts (versioning, web UI, A/B testing)
- Rule Engine (dynamic injection by conditions)
- Guardrail Service (post-processing validation)

Usage:
    composer = get_prompt_composer()
    prompt = await composer.compose_agent_prompt("LaborAgent", state)
    validated = await composer.validate_output(content, "LaborAgent")
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.config import settings
from app.services.langfuse_prompt_client import get_langfuse_prompt_client, CachedPrompt
from app.services.rule_engine import get_rule_engine, RuleContext, RuleAction
from app.services.guardrail_service import get_guardrail_service, OverallValidationResult

logger = logging.getLogger(__name__)


@dataclass
class ComposedPrompt:
    """Result of prompt composition with full metadata."""
    content: str
    agent_name: str
    # Source tracking
    prompt_name: Optional[str] = None
    prompt_version: Optional[int] = None
    is_fallback: bool = False
    # Applied modifications
    rules_applied: List[str] = field(default_factory=list)
    context_modifications: Dict[str, Any] = field(default_factory=dict)
    # Timing
    composition_time_ms: float = 0.0


@dataclass
class ValidatedOutput:
    """Result of output validation."""
    content: str
    original_content: str
    is_valid: bool
    was_blocked: bool
    was_redacted: bool
    warnings: List[str] = field(default_factory=list)
    validation_time_ms: float = 0.0


class PromptComposer:
    """
    Orchestrator for the Prompt Management system.

    Composes prompts by:
    1. Fetching base prompt from Langfuse (or YAML fallback)
    2. Evaluating and applying rules for dynamic injection
    3. Retrieving and formatting few-shot examples
    4. Building final template context

    Validates outputs by:
    1. Running all applicable guardrails
    2. Applying redactions if needed
    3. Returning validation result
    """

    def __init__(self):
        self._prompt_client = get_langfuse_prompt_client()
        self._rule_engine = get_rule_engine()
        self._guardrail_service = get_guardrail_service()

    def _build_template_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build comprehensive template context from RAG state.

        Extends the basic context with additional variables for Jinja2 templates.
        """
        metadata = state.get("metadata", {})
        retrieved_docs = state.get("retrieved_docs", [])
        # Sector is no longer used — knowledge graph provides dynamic context
        sector = ""

        # Extract detected domains
        domains = state.get("detected_domains", [])

        # Get document types from retrieved docs
        doc_types = list(set(
            d.get("document_type") or d.get("type", "unknown")
            for d in retrieved_docs
            if d
        ))

        # Get entity types from extracted entities
        entities = state.get("extracted_entities", [])
        entity_types = list(set(e.get("type") for e in entities if e.get("type")))

        return {
            # Basic context (from original PromptEngine)
            "action": metadata.get("action_intent", ""),
            "sector": sector,
            "domains": domains,
            "has_docs": bool(retrieved_docs),
            "doc_count": len(retrieved_docs),
            "query": state.get("query", ""),

            # Extended context (new)
            "document_type": doc_types[0] if doc_types else None,
            "document_types": doc_types,
            "user_role": metadata.get("user_role", "user"),
            "locale": metadata.get("locale", "es"),
            "conversation_turn": metadata.get("conversation_turn", 1),
            "has_public_knowledge": bool(state.get("public_knowledge_results")),
            "tenant_config": state.get("tenant_config", {}),
            "retrieved_doc_types": doc_types,
            "entity_types": entity_types,

            # Additional metadata
            "thread_id": state.get("thread_id"),
            "is_social_channel": metadata.get("social_channel_mode", False),
        }

    async def compose_agent_prompt(
        self,
        agent_name: str,
        state: Dict[str, Any],
        *,
        fallback_prompt: Optional[str] = None,
        include_sector: bool = True,
        tenant_id: Optional[UUID] = None,
    ) -> ComposedPrompt:
        """
        Compose a complete agent prompt with all enhancements.

        Args:
            agent_name: Name of the agent (e.g., "LaborAgent", "DocGenAgent")
            state: RAG pipeline state
            fallback_prompt: Fallback prompt if nothing else is found
            include_sector: Whether to include sector context
            tenant_id: Tenant ID for tenant-specific rules

        Returns:
            ComposedPrompt with fully assembled prompt and metadata
        """
        start_time = time.time()
        template_context = self._build_template_context(state)

        # Convert agent name to Langfuse prompt name
        # LaborAgent -> emma_agent_labor
        prompt_name = self._agent_to_prompt_name(agent_name)

        # 1. Fetch base prompt from Langfuse (or YAML fallback)
        cached_prompt = await self._prompt_client.get_prompt(
            prompt_name,
            variables=template_context,
            fallback=fallback_prompt,
        )

        if cached_prompt:
            base_prompt = cached_prompt.content
            prompt_version = cached_prompt.version
            is_fallback = cached_prompt.is_fallback
        else:
            base_prompt = fallback_prompt or ""
            prompt_version = None
            is_fallback = True

        result = ComposedPrompt(
            content=base_prompt,
            agent_name=agent_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            is_fallback=is_fallback,
        )

        # 2. Evaluate and apply rules
        if settings.rule_engine_enabled:
            rule_context = RuleContext.from_state(state)
            rule_result = await self._rule_engine.evaluate(rule_context, tenant_id)

            if rule_result.matched_rules:
                result.rules_applied = [r.rule_name for r in rule_result.matched_rules]
                result.context_modifications = rule_result.context_modifications

                # Convert to RuleAction objects for apply_actions
                actions = [
                    RuleAction(
                        rule_id=r.id,
                        rule_name=r.rule_name,
                        action_type=r.action_type,
                        config=r.action_config,
                        priority=r.priority,
                    )
                    for r in rule_result.matched_rules
                ]

                # Apply rule modifications
                result.content = await self._rule_engine.apply_actions(
                    result.content,
                    actions,
                    {**template_context, **rule_result.context_modifications},
                )

                # Update context with modifications
                template_context.update(rule_result.context_modifications)

        # 3. Add sector context if enabled
        if include_sector and template_context.get("sector"):
            sector_prompt = await self._get_sector_prompt(template_context["sector"], template_context)
            if sector_prompt:
                result.content = sector_prompt.strip() + "\n\n" + result.content

        result.composition_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"📝 Composed prompt for {agent_name}: "
            f"prompt={prompt_name}, version={prompt_version}, "
            f"rules={len(result.rules_applied)}, "
            f"time={result.composition_time_ms:.1f}ms"
        )

        return result

    async def compose_system_prompt(
        self,
        key: str,
        state: Dict[str, Any],
        *,
        fallback: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
    ) -> ComposedPrompt:
        """
        Compose a system prompt (synthesis, planning, etc.).

        Args:
            key: Prompt key (e.g., "synthesis", "planning")
            state: RAG pipeline state
            fallback: Fallback prompt if not found
            tenant_id: Tenant ID for tenant-specific rules

        Returns:
            ComposedPrompt with assembled prompt
        """
        start_time = time.time()
        template_context = self._build_template_context(state)

        # Map to Langfuse prompt name
        prompt_name = f"emma_{key}"

        cached_prompt = await self._prompt_client.get_prompt(
            prompt_name,
            variables=template_context,
            fallback=fallback,
        )

        content = cached_prompt.content if cached_prompt else fallback or ""

        result = ComposedPrompt(
            content=content,
            agent_name=key,
            prompt_name=prompt_name,
            prompt_version=cached_prompt.version if cached_prompt else None,
            is_fallback=cached_prompt.is_fallback if cached_prompt else True,
            composition_time_ms=(time.time() - start_time) * 1000,
        )

        return result

    async def compose_action_instruction(
        self,
        action: str,
        state: Dict[str, Any],
    ) -> Optional[str]:
        """
        Get action-specific instruction.

        Args:
            action: Action intent (retrieve, generate, analyze, etc.)
            state: RAG pipeline state

        Returns:
            Rendered action instruction or None
        """
        if not action:
            return None

        template_context = self._build_template_context(state)
        prompt_name = f"emma_action_{action}"

        cached_prompt = await self._prompt_client.get_prompt(
            prompt_name,
            variables=template_context,
        )

        return cached_prompt.content if cached_prompt else None

    async def validate_output(
        self,
        content: str,
        agent_name: str,
        *,
        tenant_id: Optional[UUID] = None,
    ) -> ValidatedOutput:
        """
        Validate LLM output against guardrails.

        Args:
            content: The LLM output to validate
            agent_name: The agent that produced the output
            tenant_id: Tenant ID for tenant-specific guardrails

        Returns:
            ValidatedOutput with validation result
        """
        start_time = time.time()

        if not settings.guardrails_enabled:
            return ValidatedOutput(
                content=content,
                original_content=content,
                is_valid=True,
                was_blocked=False,
                was_redacted=False,
                validation_time_ms=(time.time() - start_time) * 1000,
            )

        result = await self._guardrail_service.validate(
            content,
            agent_name=agent_name,
            tenant_id=tenant_id,
        )

        # Collect warnings
        warnings = [
            r.details for r in result.results
            if r.matched and r.details
        ]

        return ValidatedOutput(
            content=result.redacted_content or content,
            original_content=content,
            is_valid=not result.should_block,
            was_blocked=result.should_block,
            was_redacted=result.redacted_content is not None,
            warnings=warnings,
            validation_time_ms=result.processing_time_ms,
        )

    async def _get_sector_prompt(
        self,
        sector: str,
        template_context: Dict[str, Any],
    ) -> Optional[str]:
        """Get sector-specific system prompt."""
        prompt_name = f"emma_sector_{sector}"

        cached_prompt = await self._prompt_client.get_prompt(
            prompt_name,
            variables=template_context,
        )

        return cached_prompt.content if cached_prompt else None

    def _agent_to_prompt_name(self, agent_name: str) -> str:
        """Convert agent name to Langfuse prompt name format."""
        # LaborAgent -> emma_agent_labor
        # labor_agent -> emma_agent_labor
        # DocGenAgent -> emma_agent_doc_gen

        import re

        # Handle snake_case names (e.g., "labor_agent" → "labor")
        name = agent_name
        if "_agent" in name:
            name = name.replace("_agent", "")

        # Handle CamelCase names (e.g., "LaborAgent" → "Labor")
        name = name.replace("Agent", "")

        # Convert CamelCase to snake_case
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

        return f"emma_agent_{name}"

    def invalidate_cache(self, prompt_names: Optional[List[str]] = None) -> int:
        """Invalidate all caches."""
        count = self._prompt_client.invalidate_cache(prompt_names)
        self._rule_engine.invalidate_cache()
        self._guardrail_service.invalidate_cache()
        return count

    def reload_yaml(self) -> None:
        """Invalidate prompt cache (YAML no longer used — Langfuse is the single source)."""
        self._prompt_client.invalidate_cache()

    async def get_health(self) -> Dict[str, Any]:
        """Get health status of all components."""
        cache_stats = self._prompt_client.get_cache_stats()

        return {
            "langfuse_connected": cache_stats.get("langfuse_connected", False),
            "langfuse_host": settings.langfuse_host,
            "database_connected": True,  # Assume connected if we got here
            "use_langfuse_prompts": True,  # Langfuse is mandatory
            "cached_prompt_count": cache_stats.get("total_cached", 0),
            "rules_enabled": settings.rule_engine_enabled,
            "guardrails_enabled": settings.guardrails_enabled,
        }

    async def close(self) -> None:
        """Clean up resources."""
        await self._rule_engine.close()
        await self._guardrail_service.close()


# Singleton instance
_composer: Optional[PromptComposer] = None


def get_prompt_composer() -> PromptComposer:
    """Get the singleton PromptComposer instance."""
    global _composer
    if _composer is None:
        _composer = PromptComposer()
    return _composer

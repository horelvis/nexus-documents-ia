"""
Dynamic Prompt Engine — Jinja2 template rendering for Emma agents.

Replaces static prompt concatenation with context-aware templates.
Each agent can define a `system_template` (Jinja2) in emma_prompts.yaml;
if absent, the existing `system_message` is used as fallback.

Template context variables (extracted from RAGState):
    action   — generate/analyze/search/verify/compare (from ActionIntentClassifier)
    sector   — legal/medical/documental (from sector_config)
    domains  — list of detected domains (labor, fiscal, contract...)
    has_docs — whether retrieved_docs is non-empty
    doc_count — number of retrieved docs
    query    — the user's question

Usage:
    engine = get_prompt_engine()
    prompt = engine.render_agent_prompt("DocGenAgent", fallback, state)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from jinja2 import BaseLoader, Environment, TemplateSyntaxError, Undefined

from .state import RAGState

logger = logging.getLogger(__name__)


class PromptEngine:
    """Singleton engine that renders Jinja2 prompt templates."""

    _instance: Optional["PromptEngine"] = None

    def __init__(self) -> None:
        self._yaml_cache: Optional[Dict[str, Any]] = None
        self._env = Environment(
            loader=BaseLoader(),
            # Keep undefined variables as empty string (safe fallback)
            undefined=_SilentUndefined,
            autoescape=False,
        )

    # ── Public API ──────────────────────────────────────────────────────

    def render_agent_prompt(
        self,
        agent_name: str,
        fallback_prompt: str,
        state: RAGState,
    ) -> str:
        """Render a specialist agent's system prompt.

        The template **enriches** the existing system_message, it does not
        replace it.  Order: sector_prompt + rendered template + system_message.

        Args:
            agent_name: YAML key, e.g. "DocGenAgent" or "LaborAgent".
            fallback_prompt: The agent's full ``system_message`` (always used).
            state: Current RAG pipeline state.

        Returns:
            Fully assembled system prompt string.
        """
        ctx = self._build_context(state)
        template_str = self._find_template(agent_name)

        # Always keep the original system_message as the base
        rendered = fallback_prompt

        # Prepend context-aware instructions from template (if exists)
        if template_str:
            try:
                context_block = self._env.from_string(template_str).render(**ctx).strip()
                if context_block:
                    rendered = context_block + "\n\n" + rendered
                    logger.info(f"🎨 PromptEngine: Prepended template for {agent_name}")
            except TemplateSyntaxError as exc:
                logger.warning(
                    f"⚠️ PromptEngine: Template error for {agent_name}: {exc}"
                )

        # Prepend sector system prompt if available
        sector_prompt = self._get_sector_prompt(state)
        if sector_prompt:
            rendered = sector_prompt.strip() + "\n\n" + rendered
            logger.info(f"🏷️ PromptEngine: Injected sector prompt for {agent_name}")

        return rendered

    def render_system_prompt(
        self,
        key: str,
        state: RAGState,
    ) -> str:
        """Render a named system prompt from ``system_prompts`` YAML section.

        Used for synthesis and planning prompts that live in YAML rather than
        being hardcoded as Python constants.

        Args:
            key: Prompt key inside ``system_prompts`` section (e.g. "planning", "synthesis").
            state: Current RAG pipeline state.

        Returns:
            Rendered prompt string, or empty string if not found.
        """
        data = self._load_yaml()
        section = data.get("system_prompts", {})
        template_str = section.get(key)
        if not template_str:
            return ""

        ctx = self._build_context(state)
        try:
            return self._env.from_string(template_str).render(**ctx)
        except TemplateSyntaxError as exc:
            logger.warning(f"⚠️ PromptEngine: Error rendering system_prompt '{key}': {exc}")
            return ""

    # ── Private helpers ─────────────────────────────────────────────────

    def _build_context(self, state: RAGState) -> Dict[str, Any]:
        """Extract template variables from pipeline state."""
        metadata = state.get("metadata", {})
        retrieved_docs = state.get("retrieved_docs", [])
        sector_config = state.get("sector_config")

        # Action from ActionIntentClassifier (stored by plan_node)
        action = metadata.get("action_intent", "")

        # Sector name
        sector = ""
        if sector_config:
            prompt_key = sector_config.get("system_prompt_key", "")
            sector = prompt_key.replace("sectors.", "") if prompt_key else ""
            if not sector:
                sector = sector_config.get("sector", "")

        # Detected domains list
        domains: List[str] = state.get("detected_domains", [])

        return {
            "action": action,
            "sector": sector,
            "domains": domains,
            "has_docs": bool(retrieved_docs),
            "doc_count": len(retrieved_docs),
            "query": state.get("query", ""),
        }

    def _find_template(self, agent_name: str) -> Optional[str]:
        """Search for ``system_template`` across YAML agent sections."""
        data = self._load_yaml()

        for section_key in ("autogen_agents", "planning_agents"):
            section = data.get(section_key, {})
            agent_data = section.get(agent_name, {})
            template = agent_data.get("system_template")
            if template:
                return template

        return None

    def _get_sector_prompt(self, state: RAGState) -> str:
        """Get sector system prompt (same logic as base.py, centralised)."""
        sector_config = state.get("sector_config")
        if not sector_config:
            return ""

        prompt_key = sector_config.get("system_prompt_key", "")
        if not prompt_key:
            return ""

        sector_key = prompt_key.replace("sectors.", "")
        sectors = self._load_yaml().get("sectors", {})
        return sectors.get(sector_key, {}).get("system_prompt", "")

    def _load_yaml(self) -> Dict[str, Any]:
        """Load and cache emma_prompts.yaml."""
        if self._yaml_cache is not None:
            return self._yaml_cache

        candidates = [
            Path("/app/config/prompts/emma_prompts.yaml"),
            Path(__file__).parent.parent.parent.parent
            / "config"
            / "prompts"
            / "emma_prompts.yaml",
        ]
        for p in candidates:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        self._yaml_cache = yaml.safe_load(f) or {}
                    logger.info(f"📄 PromptEngine: Loaded prompts from {p}")
                    return self._yaml_cache
                except Exception as exc:
                    logger.warning(f"⚠️ PromptEngine: Failed to load {p}: {exc}")

        self._yaml_cache = {}
        return self._yaml_cache

    def reload(self) -> None:
        """Force reload of YAML (e.g. after POST /emma/prompts/reload)."""
        self._yaml_cache = None
        logger.info("🔄 PromptEngine: Cache cleared, will reload on next access")


class _SilentUndefined(Undefined):
    """Jinja2 undefined that renders as empty string instead of raising."""

    def __str__(self) -> str:
        return ""

    def __iter__(self):  # type: ignore[override]
        return iter([])

    def __bool__(self) -> bool:
        return False

    def __getattr__(self, _name: str) -> "_SilentUndefined":
        return _SilentUndefined()


def get_prompt_engine() -> PromptEngine:
    """Return the singleton PromptEngine instance."""
    if PromptEngine._instance is None:
        PromptEngine._instance = PromptEngine()
    return PromptEngine._instance

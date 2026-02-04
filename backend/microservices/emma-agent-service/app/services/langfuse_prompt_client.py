"""
Langfuse Prompt Client — Wrapper for Langfuse Prompt Management API.

Provides:
- Prompt fetching with local TTL cache (default 5 minutes)
- YAML fallback when Langfuse is unavailable or prompt doesn't exist
- Jinja2 template compilation
- Version tracking for observability

Usage:
    client = get_langfuse_prompt_client()
    prompt = await client.get_prompt("emma_agent_labor", variables={"action": "analyze"})
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from jinja2 import Environment, BaseLoader, TemplateSyntaxError, Undefined

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CachedPrompt:
    """A cached prompt with metadata."""
    name: str
    content: str
    version: Optional[int] = None
    labels: Optional[List[str]] = None
    cached_at: float = 0.0
    is_fallback: bool = False

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if cache entry has expired."""
        return (time.time() - self.cached_at) > ttl_seconds


class SilentUndefined(Undefined):
    """Jinja2 undefined that renders as empty string."""
    def __str__(self) -> str:
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self) -> bool:
        return False

    def __getattr__(self, _name: str) -> "SilentUndefined":
        return SilentUndefined()


class LangfusePromptClient:
    """
    Client for Langfuse Prompt Management with local caching and YAML fallback.

    Features:
    - Fetches prompts from Langfuse with TTL-based caching
    - Falls back to YAML when Langfuse is unavailable
    - Supports Jinja2 template rendering
    - Tracks prompt versions for observability
    """

    def __init__(self):
        self._cache: Dict[str, CachedPrompt] = {}
        self._yaml_cache: Optional[Dict[str, Any]] = None
        self._langfuse = None
        self._langfuse_checked = False
        self._jinja_env = Environment(
            loader=BaseLoader(),
            undefined=SilentUndefined,
            autoescape=False,
        )

    def _get_langfuse(self):
        """Get or create Langfuse client (lazy initialization)."""
        if self._langfuse_checked:
            return self._langfuse

        self._langfuse_checked = True

        if not settings.langfuse_enabled:
            logger.info("Langfuse disabled (LANGFUSE_ENABLED=false)")
            return None

        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            logger.warning("Langfuse keys not configured, prompts will use YAML fallback")
            return None

        try:
            from langfuse import Langfuse
            self._langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            logger.info(f"✅ Langfuse Prompt Client initialized (host={settings.langfuse_host})")
            return self._langfuse
        except ImportError:
            logger.warning("Langfuse SDK not installed, using YAML fallback")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize Langfuse: {e}")
            return None

    def _load_yaml(self) -> Dict[str, Any]:
        """Load and cache emma_prompts.yaml."""
        if self._yaml_cache is not None:
            return self._yaml_cache

        candidates = [
            Path("/app/config/prompts/emma_prompts.yaml"),
            Path(__file__).parent.parent.parent / "config" / "prompts" / "emma_prompts.yaml",
        ]

        for path in candidates:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self._yaml_cache = yaml.safe_load(f) or {}
                    logger.info(f"📄 Loaded YAML prompts from {path}")
                    return self._yaml_cache
                except Exception as e:
                    logger.warning(f"Failed to load {path}: {e}")

        self._yaml_cache = {}
        return self._yaml_cache

    def _get_yaml_prompt(self, name: str) -> Optional[str]:
        """
        Get prompt from YAML using dotted path notation.

        Examples:
            "emma_context_root" -> context_root section
            "emma_agent_labor" -> autogen_agents.LaborAgent.system_message
            "emma_sector_legal" -> sectors.legal.system_prompt
            "emma_synthesis" -> system_prompts.synthesis
        """
        yaml_data = self._load_yaml()

        # Map Langfuse prompt names to YAML paths
        name_mapping = {
            # Core prompts
            "emma_context_root": ("context_root",),
            "emma_synthesis": ("system_prompts", "synthesis"),
            "emma_planning": ("system_prompts", "planning"),

            # Action instructions
            "emma_action_generate": ("action_instructions", "generate"),
            "emma_action_retrieve": ("action_instructions", "retrieve"),
            "emma_action_analyze": ("action_instructions", "analyze"),
            "emma_action_search": ("action_instructions", "search"),
            "emma_action_compare": ("action_instructions", "compare"),

            # Sector prompts
            "emma_sector_legal": ("sectors", "legal", "system_prompt"),
            "emma_sector_medical": ("sectors", "medical", "system_prompt"),
            "emma_sector_documental": ("sectors", "documental", "system_prompt"),

            # Sector generation prompts
            "emma_sector_legal_generation": ("sectors", "legal", "generation_prompt"),
            "emma_sector_medical_generation": ("sectors", "medical", "generation_prompt"),
            "emma_sector_documental_generation": ("sectors", "documental", "generation_prompt"),

            # Chat prompts
            "emma_chat_base": ("chat_prompts", "base"),
            "emma_chat_analyze": ("chat_prompts", "analyze"),
            "emma_chat_compare": ("chat_prompts", "compare"),
            "emma_chat_summarize": ("chat_prompts", "summarize"),
            "emma_chat_search": ("chat_prompts", "search"),
            "emma_chat_extract": ("chat_prompts", "extract"),
            "emma_chat_explain": ("chat_prompts", "explain"),

            # Social channel
            "emma_social_system": ("social_channels", "system_prompt"),
            "emma_social_conversational": ("social_channels", "conversational_prompt"),
        }

        # Check explicit mapping first
        if name in name_mapping:
            path = name_mapping[name]
            value = yaml_data
            for key in path:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return None
            return value if isinstance(value, str) else None

        # Try agent prompts (emma_agent_<name>)
        if name.startswith("emma_agent_"):
            agent_suffix = name[11:]  # Remove "emma_agent_"
            # Try multiple agent name formats
            agent_names = [
                agent_suffix,
                f"{agent_suffix.title()}Agent",
                f"{agent_suffix.replace('_', ' ').title().replace(' ', '')}Agent",
            ]
            for agent_name in agent_names:
                for section in ("autogen_agents", "planning_agents"):
                    if section in yaml_data:
                        agent_data = yaml_data[section].get(agent_name, {})
                        if "system_message" in agent_data:
                            return agent_data["system_message"]
                        if "system_template" in agent_data:
                            return agent_data["system_template"]

        return None

    async def get_prompt(
        self,
        name: str,
        *,
        version: Optional[int] = None,
        label: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        fallback: Optional[str] = None,
    ) -> Optional[CachedPrompt]:
        """
        Get a prompt by name with caching and YAML fallback.

        Args:
            name: Prompt name in Langfuse (e.g., "emma_agent_labor")
            version: Specific version to fetch (default: latest)
            label: Label to fetch (e.g., "production", "staging")
            variables: Template variables for Jinja2 rendering
            fallback: Fallback content if prompt not found anywhere

        Returns:
            CachedPrompt with content and metadata, or None if not found
        """
        cache_key = f"{name}:{version or 'latest'}:{label or 'default'}"

        # Check cache first
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if not cached.is_expired(settings.langfuse_prompt_cache_ttl):
                logger.debug(f"🎯 Cache hit for prompt '{name}'")
                if variables:
                    cached.content = self._render_template(cached.content, variables)
                return cached

        # Try Langfuse if enabled
        prompt_content = None
        prompt_version = None
        prompt_labels = None
        is_fallback = False

        if settings.use_langfuse_prompts:
            langfuse = self._get_langfuse()
            if langfuse:
                try:
                    prompt = langfuse.get_prompt(
                        name=name,
                        version=version,
                        label=label,
                        fallback=fallback,
                    )
                    if prompt:
                        prompt_content = prompt.prompt if hasattr(prompt, 'prompt') else str(prompt)
                        prompt_version = getattr(prompt, 'version', None)
                        prompt_labels = getattr(prompt, 'labels', None)
                        logger.info(f"📥 Fetched prompt '{name}' v{prompt_version} from Langfuse")
                except Exception as e:
                    logger.warning(f"⚠️ Langfuse fetch failed for '{name}': {e}")

        # Fall back to YAML if Langfuse failed or disabled
        if prompt_content is None:
            prompt_content = self._get_yaml_prompt(name)
            is_fallback = True
            if prompt_content:
                logger.debug(f"📄 Using YAML fallback for prompt '{name}'")

        # Use provided fallback if nothing found
        if prompt_content is None and fallback:
            prompt_content = fallback
            is_fallback = True
            logger.debug(f"📄 Using provided fallback for prompt '{name}'")

        if prompt_content is None:
            logger.warning(f"❌ Prompt '{name}' not found in Langfuse or YAML")
            return None

        # Cache the result
        cached_prompt = CachedPrompt(
            name=name,
            content=prompt_content,
            version=prompt_version,
            labels=prompt_labels,
            cached_at=time.time(),
            is_fallback=is_fallback,
        )
        self._cache[cache_key] = cached_prompt

        # Render template if variables provided
        if variables:
            cached_prompt.content = self._render_template(cached_prompt.content, variables)

        return cached_prompt

    async def get_prompt_compiled(
        self,
        name: str,
        variables: Dict[str, Any],
        **kwargs,
    ) -> Optional[str]:
        """
        Get a prompt and compile it with variables.

        Convenience method that returns just the rendered content.
        """
        prompt = await self.get_prompt(name, variables=variables, **kwargs)
        return prompt.content if prompt else None

    def _render_template(self, template_str: str, variables: Dict[str, Any]) -> str:
        """Render a Jinja2 template with variables."""
        try:
            return self._jinja_env.from_string(template_str).render(**variables).strip()
        except TemplateSyntaxError as e:
            logger.warning(f"⚠️ Template syntax error: {e}")
            return template_str
        except Exception as e:
            logger.warning(f"⚠️ Template render error: {e}")
            return template_str

    def invalidate_cache(self, prompt_names: Optional[List[str]] = None) -> int:
        """
        Invalidate cached prompts.

        Args:
            prompt_names: Specific prompts to invalidate. None = invalidate all.

        Returns:
            Number of cache entries invalidated.
        """
        if prompt_names is None:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"🗑️ Invalidated all {count} cached prompts")
            return count

        count = 0
        for key in list(self._cache.keys()):
            if any(key.startswith(name) for name in prompt_names):
                del self._cache[key]
                count += 1

        logger.info(f"🗑️ Invalidated {count} cached prompts")
        return count

    def reload_yaml(self) -> None:
        """Force reload of YAML cache."""
        self._yaml_cache = None
        logger.info("🔄 YAML cache cleared, will reload on next access")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        now = time.time()
        ttl = settings.langfuse_prompt_cache_ttl

        valid_count = sum(
            1 for p in self._cache.values()
            if not p.is_expired(ttl)
        )
        fallback_count = sum(
            1 for p in self._cache.values()
            if p.is_fallback
        )

        # Trigger lazy initialization to check connection status
        langfuse_client = self._get_langfuse()

        return {
            "total_cached": len(self._cache),
            "valid_cached": valid_count,
            "expired_cached": len(self._cache) - valid_count,
            "fallback_count": fallback_count,
            "ttl_seconds": ttl,
            "langfuse_connected": langfuse_client is not None,
            "use_langfuse_prompts": settings.use_langfuse_prompts,
        }

    async def sync_from_langfuse(self, prompt_names: Optional[List[str]] = None) -> List[str]:
        """
        Force sync prompts from Langfuse, bypassing cache.

        Args:
            prompt_names: Specific prompts to sync. None = sync known prompts.

        Returns:
            List of successfully synced prompt names.
        """
        if not settings.use_langfuse_prompts:
            logger.warning("Langfuse prompts disabled, sync skipped")
            return []

        langfuse = self._get_langfuse()
        if not langfuse:
            logger.warning("Langfuse not available, sync skipped")
            return []

        # Default prompts to sync
        if prompt_names is None:
            prompt_names = [
                "emma_context_root",
                "emma_synthesis",
                "emma_planning",
                "emma_action_generate",
                "emma_action_retrieve",
                "emma_action_analyze",
                "emma_sector_legal",
                "emma_sector_medical",
                "emma_sector_documental",
                "emma_agent_labor",
                "emma_agent_fiscal",
                "emma_agent_contract",
                "emma_agent_compliance",
                "emma_agent_privacy",
                "emma_agent_docgen",
                "emma_social_system",
            ]

        synced = []
        for name in prompt_names:
            # Clear cache entry first
            for key in list(self._cache.keys()):
                if key.startswith(name):
                    del self._cache[key]

            # Fetch fresh from Langfuse
            prompt = await self.get_prompt(name)
            if prompt and not prompt.is_fallback:
                synced.append(name)

        logger.info(f"🔄 Synced {len(synced)}/{len(prompt_names)} prompts from Langfuse")
        return synced

    async def list_available_prompts(self) -> Dict[str, List[str]]:
        """List all available prompts from both Langfuse and YAML."""
        result = {
            "langfuse": [],
            "yaml": [],
        }

        # List YAML prompts
        yaml_data = self._load_yaml()
        yaml_prompts = set()

        # Scan known sections
        if "context_root" in yaml_data:
            yaml_prompts.add("emma_context_root")

        for key in yaml_data.get("action_instructions", {}).keys():
            yaml_prompts.add(f"emma_action_{key}")

        for key in yaml_data.get("sectors", {}).keys():
            yaml_prompts.add(f"emma_sector_{key}")

        for key in yaml_data.get("system_prompts", {}).keys():
            yaml_prompts.add(f"emma_{key}")

        for key in yaml_data.get("chat_prompts", {}).keys():
            yaml_prompts.add(f"emma_chat_{key}")

        for section in ("autogen_agents", "planning_agents"):
            for agent_name in yaml_data.get(section, {}).keys():
                # Convert AgentName to emma_agent_name format
                snake_name = "".join(
                    f"_{c.lower()}" if c.isupper() else c
                    for c in agent_name
                ).lstrip("_").replace("_agent", "")
                yaml_prompts.add(f"emma_agent_{snake_name}")

        result["yaml"] = sorted(yaml_prompts)

        # List Langfuse prompts (if available)
        # Note: Langfuse SDK doesn't have a list_prompts method,
        # so we report cached ones
        result["langfuse"] = sorted(
            set(p.name for p in self._cache.values() if not p.is_fallback)
        )

        return result


# Singleton instance
_client: Optional[LangfusePromptClient] = None


def get_langfuse_prompt_client() -> LangfusePromptClient:
    """Get the singleton LangfusePromptClient instance."""
    global _client
    if _client is None:
        _client = LangfusePromptClient()
    return _client

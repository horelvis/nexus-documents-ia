"""
Langfuse Prompt Client — Single source of truth for all prompts.

Langfuse is the ONLY prompt source. No YAML fallback. Missing prompts
raise PromptNotFoundError to fail fast.

Usage:
    client = get_langfuse_prompt_client()
    prompt = await client.get_prompt("emma_react_system", variables={"tools": "..."})
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from jinja2 import Environment, BaseLoader, TemplateSyntaxError, Undefined

from app.core.config import settings

logger = logging.getLogger(__name__)


class PromptNotFoundError(Exception):
    """Raised when a prompt is not found in Langfuse and no fallback is provided."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(
            f"Prompt '{name}' not found in Langfuse. "
            f"Create it via Langfuse UI or a migration script."
        )


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
    Client for Langfuse Prompt Management with local caching.

    Langfuse is the single source of truth. No YAML fallback.
    Missing prompts raise PromptNotFoundError.
    """

    def __init__(self):
        self._cache: Dict[str, CachedPrompt] = {}
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
            logger.warning("Langfuse disabled — prompts will only work from cache or fallback args")
            return None

        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            logger.warning("Langfuse keys not configured — prompts will only work from cache or fallback args")
            return None

        try:
            from langfuse import Langfuse
            self._langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            logger.info(f"Langfuse Prompt Client initialized (host={settings.langfuse_host})")
            return self._langfuse
        except ImportError:
            logger.error("Langfuse SDK not installed — prompt system unavailable")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize Langfuse: {e}")
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
        Get a prompt by name from Langfuse with caching.

        Args:
            name: Prompt name in Langfuse (e.g., "emma_react_system")
            version: Specific version to fetch (default: latest)
            label: Label to fetch (e.g., "production", "staging").
                   Defaults to settings.langfuse_prompt_label (typically "production").
            variables: Template variables for Jinja2 rendering
            fallback: Fallback content if prompt not found in Langfuse.
                      WARNING: Using fallback is deprecated and will be removed.
                      All prompts should exist in Langfuse.

        Returns:
            CachedPrompt with content and metadata

        Raises:
            PromptNotFoundError: If prompt not found and no fallback provided
        """
        # Pin to production label by default
        if label is None and settings.langfuse_prompt_label:
            label = settings.langfuse_prompt_label

        cache_key = f"{name}:{version or 'latest'}:{label or 'default'}"

        # Check cache first
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if not cached.is_expired(settings.langfuse_prompt_cache_ttl):
                if variables:
                    rendered = self._render_template(cached.content, variables)
                    return CachedPrompt(
                        name=cached.name,
                        content=rendered,
                        version=cached.version,
                        labels=cached.labels,
                        cached_at=cached.cached_at,
                        is_fallback=cached.is_fallback,
                    )
                return cached

        # Try Langfuse
        prompt_content = None
        prompt_version = None
        prompt_labels = None
        is_fallback = False

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
                    logger.info(f"Fetched prompt '{name}' v{prompt_version} from Langfuse")
            except Exception as e:
                logger.warning(f"Langfuse fetch failed for '{name}': {e}")

        # Use provided fallback if Langfuse failed (transitional — will be removed)
        if prompt_content is None and fallback:
            prompt_content = fallback
            is_fallback = True
            logger.warning(
                f"Using inline fallback for prompt '{name}' — "
                f"this should be in Langfuse. Create it via UI or migration script."
            )

        # No prompt found anywhere → fail fast
        if prompt_content is None:
            raise PromptNotFoundError(name)

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
            rendered = self._render_template(cached_prompt.content, variables)
            return CachedPrompt(
                name=cached_prompt.name,
                content=rendered,
                version=cached_prompt.version,
                labels=cached_prompt.labels,
                cached_at=cached_prompt.cached_at,
                is_fallback=cached_prompt.is_fallback,
            )

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
            logger.warning(f"Template syntax error: {e}")
            return template_str
        except Exception as e:
            logger.warning(f"Template render error: {e}")
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
            logger.info(f"Invalidated all {count} cached prompts")
            return count

        count = 0
        for key in list(self._cache.keys()):
            if any(key.startswith(name) for name in prompt_names):
                del self._cache[key]
                count += 1

        logger.info(f"Invalidated {count} cached prompts")
        return count

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        ttl = settings.langfuse_prompt_cache_ttl

        valid_count = sum(
            1 for p in self._cache.values()
            if not p.is_expired(ttl)
        )
        fallback_count = sum(
            1 for p in self._cache.values()
            if p.is_fallback
        )

        langfuse_client = self._get_langfuse()

        return {
            "total_cached": len(self._cache),
            "valid_cached": valid_count,
            "expired_cached": len(self._cache) - valid_count,
            "fallback_count": fallback_count,
            "ttl_seconds": ttl,
            "langfuse_connected": langfuse_client is not None,
        }

    async def sync_from_langfuse(self, prompt_names: Optional[List[str]] = None) -> List[str]:
        """
        Force sync prompts from Langfuse, bypassing cache.

        Args:
            prompt_names: Specific prompts to sync. None = sync all registered prompts.

        Returns:
            List of successfully synced prompt names.
        """
        from app.services.prompt_registry import PROMPT_REGISTRY

        langfuse = self._get_langfuse()
        if not langfuse:
            logger.warning("Langfuse not available, sync skipped")
            return []

        if prompt_names is None:
            prompt_names = list(PROMPT_REGISTRY.keys())

        synced = []
        for name in prompt_names:
            # Clear cache entry first
            for key in list(self._cache.keys()):
                if key.startswith(name):
                    del self._cache[key]

            # Fetch fresh from Langfuse (use empty fallback to avoid PromptNotFoundError during sync)
            try:
                prompt = await self.get_prompt(name, fallback="")
                if prompt and not prompt.is_fallback:
                    synced.append(name)
            except PromptNotFoundError:
                logger.warning(f"Prompt '{name}' not found in Langfuse during sync")

        logger.info(f"Synced {len(synced)}/{len(prompt_names)} prompts from Langfuse")
        return synced


# Singleton instance
_client: Optional[LangfusePromptClient] = None


def get_langfuse_prompt_client() -> LangfusePromptClient:
    """Get the singleton LangfusePromptClient instance."""
    global _client
    if _client is None:
        _client = LangfusePromptClient()
    return _client

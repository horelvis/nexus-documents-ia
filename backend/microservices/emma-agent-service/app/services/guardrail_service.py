"""
Guardrail Service — Post-processing validation for LLM outputs.

Validates LLM responses against configurable guardrails:
- regex: Pattern matching (e.g., block phone numbers, emails)
- keyword: Blocked/required word lists
- semantic: Embedding-based topic detection
- llm_validator: LLM-based content validation
- length: Character/word count limits
- format: Structural requirements (sources, language)

Usage:
    service = get_guardrail_service()
    result = await service.validate(content, agent_name="LaborAgent")
    if result.should_block:
        raise ContentBlockedException(result.details)
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx

from app.core.config import settings
from app.schemas.prompts import (
    GuardrailType,
    GuardrailAction,
    GuardrailResponse,
    GuardrailTestResult,
    GuardrailTestResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a single guardrail validation."""
    guardrail_id: UUID
    guardrail_name: str
    guardrail_type: GuardrailType
    matched: bool
    action: GuardrailAction
    details: Optional[str] = None
    matched_content: Optional[str] = None


@dataclass
class OverallValidationResult:
    """Overall validation result across all guardrails."""
    results: List[ValidationResult] = field(default_factory=list)
    should_block: bool = False
    should_warn: bool = False
    redacted_content: Optional[str] = None
    disclaimers: List[str] = field(default_factory=list)
    processing_time_ms: float = 0.0

    @property
    def overall_action(self) -> GuardrailAction:
        """Get the most severe action from all results."""
        if self.should_block:
            return GuardrailAction.BLOCK
        if any(r.action == GuardrailAction.REDACT for r in self.results if r.matched):
            return GuardrailAction.REDACT
        if self.should_warn:
            return GuardrailAction.WARN
        return GuardrailAction.WARN  # Default


class GuardrailService:
    """
    Service for validating LLM outputs against guardrails.

    Guardrails are loaded from the registry (baseline) and database (overrides),
    merged with DB winning on name collision.
    Each guardrail specifies a type, configuration, and action on match.
    """

    def __init__(self):
        self._guardrails_cache: Dict[tuple, List[Dict[str, Any]]] = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_time: Dict[tuple, float] = {}
        self._http_client: Optional[httpx.AsyncClient] = None
        self._db_session = None
        self._embedding_cache: Dict[str, List[float]] = {}

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def _load_guardrails(self, tenant_id: Optional[UUID] = None, sector: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load guardrails: registry baseline merged with DB overrides."""
        import time as time_module
        from app.services.guardrail_registry import get_guardrails_for_sector

        cache_key = (tenant_id, sector)
        now = time_module.time()

        if cache_key in self._guardrails_cache:
            if (now - self._cache_time.get(cache_key, 0)) < self._cache_ttl:
                return self._guardrails_cache[cache_key]

        # Step 1: Registry baseline (in-memory)
        registry_guardrails = get_guardrails_for_sector(sector)

        # Step 2: DB overrides (via Main API HTTP)
        db_guardrails = []
        try:
            client = await self._get_http_client()
            headers = {"X-API-Key": settings.MICROSERVICES_API_KEY, "Content-Type": "application/json"}
            if tenant_id:
                headers["X-Tenant-ID"] = str(tenant_id)
            url = f"{settings.api_url}/api/v1/prompts/guardrails"
            params = {"active_only": "true"}
            if sector:
                params["sector"] = sector
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            guardrails_data = response.json()
            items = guardrails_data if isinstance(guardrails_data, list) else guardrails_data.get("guardrails", [])
            for g in items:
                db_guardrails.append({
                    "id": g.get("id"), "tenant_id": g.get("tenant_id"),
                    "guardrail_name": g.get("guardrail_name"), "description": g.get("description"),
                    "guardrail_type": g.get("guardrail_type"), "config": g.get("config", {}),
                    "action_on_match": g.get("action_on_match"), "applies_to": g.get("applies_to", []),
                    "priority": g.get("priority", 100), "is_active": g.get("is_active", True),
                    "sector": g.get("sector"),
                })
        except Exception as e:
            logger.warning(f"Failed to load DB guardrails: {e}. Using registry only.")

        # Step 3: Merge — DB wins on name collision
        db_by_name = {g["guardrail_name"]: g for g in db_guardrails}
        merged = []
        for rg in registry_guardrails:
            name = rg["guardrail_name"]
            if name in db_by_name:
                db_entry = db_by_name.pop(name)
                if db_entry.get("is_active", True):
                    merged.append(db_entry)
            else:
                merged.append(rg)
        for db_entry in db_by_name.values():
            if db_entry.get("is_active", True):
                merged.append(db_entry)
        merged.sort(key=lambda g: g.get("priority", 100))

        self._guardrails_cache[cache_key] = merged
        self._cache_time[cache_key] = now
        logger.debug(f"Loaded {len(merged)} guardrails (registry={len(registry_guardrails)}, db={len(db_guardrails)}) for tenant={tenant_id}, sector={sector}")
        return merged

    def _applies_to_agent(self, guardrail: Dict[str, Any], agent_name: Optional[str]) -> bool:
        """Check if guardrail applies to the given agent."""
        applies_to = guardrail.get("applies_to")
        if not applies_to:
            return True  # Empty = applies to all
        if "*" in applies_to:
            return True
        if agent_name and agent_name in applies_to:
            return True
        return False

    async def _validate_regex(
        self,
        content: str,
        config: Dict[str, Any],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Validate content against regex pattern."""
        pattern = config.get("pattern")
        if not pattern:
            return False, None, None

        flags = 0
        flag_str = config.get("flags", "")
        if "i" in flag_str:
            flags |= re.IGNORECASE
        if "m" in flag_str:
            flags |= re.MULTILINE
        if "s" in flag_str:
            flags |= re.DOTALL

        try:
            matches = list(re.finditer(pattern, content, flags))
            if matches:
                return True, f"Regex pattern matched {len(matches)} time(s): {pattern}", pattern
            return False, None, None
        except re.error as e:
            logger.warning(f"Invalid regex pattern: {e}")
            return False, None, None

    def _validate_keyword(
        self,
        content: str,
        config: Dict[str, Any],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Validate content against keyword lists."""
        content_lower = content.lower()

        # Check blocked words
        blocked_words = config.get("blocked_words", [])
        for word in blocked_words:
            if word.lower() in content_lower:
                return True, f"Blocked word found: {word}", word

        # Check required words
        required_words = config.get("required_words", [])
        for word in required_words:
            if word.lower() not in content_lower:
                return True, f"Required word missing: {word}", None

        return False, None, None

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for text using weaviate-service."""
        cache_key = text[:100]
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        try:
            client = await self._get_http_client()
            response = await client.post(
                f"{settings.weaviate_service_url}/embed",
                json={"text": text},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )

            if response.status_code == 200:
                data = response.json()
                embedding = data.get("embedding")
                if embedding:
                    self._embedding_cache[cache_key] = embedding
                    return embedding

            return None
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            return None

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        import math
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    async def _validate_semantic(
        self,
        content: str,
        config: Dict[str, Any],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Validate content against forbidden/required topics using embeddings."""
        threshold = config.get("similarity_threshold", 0.8)

        # Get content embedding
        content_embedding = await self._get_embedding(content[:500])  # Truncate for embedding
        if not content_embedding:
            return False, None, None

        # Check forbidden topics
        forbidden_topics = config.get("forbidden_topics", [])
        for topic in forbidden_topics:
            topic_embedding = await self._get_embedding(topic)
            if topic_embedding:
                similarity = self._cosine_similarity(content_embedding, topic_embedding)
                if similarity >= threshold:
                    return True, f"Forbidden topic detected: {topic} (similarity: {similarity:.2f})", topic

        # Check required topics
        required_topics = config.get("required_topics", [])
        for topic in required_topics:
            topic_embedding = await self._get_embedding(topic)
            if topic_embedding:
                similarity = self._cosine_similarity(content_embedding, topic_embedding)
                if similarity < threshold:
                    return True, f"Required topic not covered: {topic} (similarity: {similarity:.2f})", None

        return False, None, None

    async def _validate_llm(
        self,
        content: str,
        config: Dict[str, Any],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Validate content using LLM via LLMRouter with Langfuse prompt support."""
        system_prompt = None
        user_prompt = None
        langfuse_key = config.get("langfuse_prompt_key")

        if langfuse_key:
            try:
                from app.services.langfuse_prompt_client import get_langfuse_prompt_client
                client = get_langfuse_prompt_client()
                system_prompt = await client.get_prompt(langfuse_key)
                user_key = langfuse_key.replace("_system", "_user")
                if user_key != langfuse_key:
                    user_prompt_template = await client.get_prompt(user_key)
                    if user_prompt_template:
                        user_prompt = user_prompt_template.replace("{content}", content[:2000])
            except Exception as e:
                logger.warning(f"Langfuse prompt '{langfuse_key}' not found, using fallback: {e}")

        if not system_prompt:
            system_prompt = "You are a content validator. Respond with only 'PASS' or 'FAIL: <reason>'."
        if not user_prompt:
            validation_prompt = config.get("validation_prompt", "Validate the following content:")
            user_prompt = f"{validation_prompt}\n\nContent to validate:\n{content[:2000]}"

        try:
            from app.agents.llm_router import get_llm_router
            from app.agents.llm_client import ModelRole
            router = await get_llm_router()
            response = await router.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                role=ModelRole.PLANNER,
                max_tokens=100,
                temperature=0.1,
            )
            reply = response.content or ""
            if reply.strip().upper().startswith("FAIL"):
                reason = reply.replace("FAIL:", "").replace("FAIL", "").strip()
                return True, f"LLM validation failed: {reason}", None
            return False, None, None
        except Exception as e:
            logger.error(f"LLM validation error: {e}")
            return False, None, None

    def _validate_length(
        self,
        content: str,
        config: Dict[str, Any],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Validate content length."""
        char_count = len(content)
        word_count = len(content.split())

        min_chars = config.get("min_chars")
        max_chars = config.get("max_chars")
        min_words = config.get("min_words")
        max_words = config.get("max_words")

        if min_chars and char_count < min_chars:
            return True, f"Content too short: {char_count} chars (min: {min_chars})", None

        if max_chars and char_count > max_chars:
            return True, f"Content too long: {char_count} chars (max: {max_chars})", None

        if min_words and word_count < min_words:
            return True, f"Content too short: {word_count} words (min: {min_words})", None

        if max_words and word_count > max_words:
            return True, f"Content too long: {word_count} words (max: {max_words})", None

        return False, None, None

    def _validate_format(
        self,
        content: str,
        config: Dict[str, Any],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Validate content format/structure."""
        issues = []

        # Check for source citations
        if config.get("must_contain_sources"):
            source_patterns = [
                r"\[.*?\]",  # [1], [source]
                r"Art\.\s*\d+",  # Art. 52
                r"artículo\s+\d+",  # artículo 52
                r"según\s+(el|la)",  # según el/la
                r"conforme\s+a",  # conforme a
            ]
            has_source = any(re.search(p, content, re.IGNORECASE) for p in source_patterns)
            if not has_source:
                issues.append("No source citations found")

        # Check for Spanish language
        if config.get("require_spanish"):
            spanish_indicators = ["el", "la", "los", "las", "de", "en", "que", "es", "un", "una"]
            words = content.lower().split()[:100]
            spanish_count = sum(1 for w in words if w in spanish_indicators)
            if spanish_count < 5:  # At least 5 Spanish indicators
                issues.append("Content may not be in Spanish")

        # Check required sections/headers
        required_structure = config.get("require_structure", [])
        for section in required_structure:
            if section.lower() not in content.lower():
                issues.append(f"Missing required section: {section}")

        # Check required regex pattern (e.g., legal citations)
        require_pattern = config.get("require_pattern")
        if require_pattern:
            try:
                if not re.search(require_pattern, content, re.IGNORECASE):
                    issues.append(f"Required pattern not found: {require_pattern}")
            except re.error:
                pass

        # Check inject_text — triggers if disclaimer text is absent
        inject_text = config.get("inject_text")
        check_absent = config.get("check_absent")
        if inject_text and check_absent:
            if check_absent.lower() not in content.lower():
                issues.append(f"Disclaimer missing (will inject): {check_absent}")

        if issues:
            return True, "; ".join(issues), None

        return False, None, None

    async def validate(
        self,
        content: str,
        *,
        agent_name: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        sector: Optional[str] = None,
    ) -> OverallValidationResult:
        """
        Validate content against all applicable guardrails.

        Args:
            content: The LLM output to validate
            agent_name: The agent that produced the content (for filtering)
            tenant_id: Tenant ID for tenant-specific guardrails
            sector: Active sector for sector-specific guardrails

        Returns:
            OverallValidationResult with all validation results
        """
        if not settings.guardrails_enabled:
            return OverallValidationResult()

        start_time = time.time()
        guardrails = await self._load_guardrails(tenant_id, sector)

        results = []
        should_block = False
        should_warn = False
        redacted_content = content
        disclaimers: List[str] = []

        for guardrail in guardrails:
            # Check if guardrail applies to this agent
            if not self._applies_to_agent(guardrail, agent_name):
                continue

            guardrail_type = GuardrailType(guardrail["guardrail_type"])
            config = guardrail["config"]
            action = GuardrailAction(guardrail["action_on_match"])

            matched = False
            details = None
            matched_content = None

            # Run validation based on type
            if guardrail_type == GuardrailType.REGEX:
                matched, details, matched_content = await self._validate_regex(content, config)

            elif guardrail_type == GuardrailType.KEYWORD:
                matched, details, matched_content = self._validate_keyword(content, config)

            elif guardrail_type == GuardrailType.SEMANTIC:
                matched, details, matched_content = await self._validate_semantic(content, config)

            elif guardrail_type == GuardrailType.LLM_VALIDATOR:
                matched, details, matched_content = await self._validate_llm(content, config)

            elif guardrail_type == GuardrailType.LENGTH:
                matched, details, matched_content = self._validate_length(content, config)

            elif guardrail_type == GuardrailType.FORMAT:
                matched, details, matched_content = self._validate_format(content, config)

            result = ValidationResult(
                guardrail_id=guardrail["id"],
                guardrail_name=guardrail["guardrail_name"],
                guardrail_type=guardrail_type,
                matched=matched,
                action=action,
                details=details,
                matched_content=matched_content,
            )
            results.append(result)

            if matched:
                logger.warning(
                    f"Guardrail '{guardrail['guardrail_name']}' triggered: {details}"
                )

                if action == GuardrailAction.BLOCK:
                    should_block = True
                elif action == GuardrailAction.WARN:
                    should_warn = True
                    # Check for inject_text disclaimer
                    inject_text = config.get("inject_text")
                    if inject_text:
                        disclaimers.append(inject_text)
                elif action == GuardrailAction.REDACT and matched_content:
                    # Redact the matched content using re.sub for regex patterns
                    if guardrail_type == GuardrailType.REGEX:
                        flags = 0
                        flag_str = config.get("flags", "")
                        if "i" in flag_str:
                            flags |= re.IGNORECASE
                        if "m" in flag_str:
                            flags |= re.MULTILINE
                        if "s" in flag_str:
                            flags |= re.DOTALL
                        try:
                            redacted_content = re.sub(matched_content, "[REDACTED]", redacted_content, flags=flags)
                        except re.error:
                            redacted_content = redacted_content.replace(matched_content, "[REDACTED]")
                    else:
                        redacted_content = redacted_content.replace(matched_content, "[REDACTED]")

        elapsed_ms = (time.time() - start_time) * 1000

        return OverallValidationResult(
            results=results,
            should_block=should_block,
            should_warn=should_warn,
            redacted_content=redacted_content if redacted_content != content else None,
            disclaimers=disclaimers,
            processing_time_ms=elapsed_ms,
        )

    async def test_guardrail(
        self,
        guardrail_id: UUID,
        content: str,
        tenant_id: Optional[UUID] = None,
    ) -> Optional[GuardrailTestResult]:
        """Test a specific guardrail against content."""
        guardrails = await self._load_guardrails(tenant_id)

        for guardrail in guardrails:
            if guardrail["id"] == guardrail_id:
                guardrail_type = GuardrailType(guardrail["guardrail_type"])
                config = guardrail["config"]
                action = GuardrailAction(guardrail["action_on_match"])

                matched = False
                details = None
                matched_content = None

                if guardrail_type == GuardrailType.REGEX:
                    matched, details, matched_content = await self._validate_regex(content, config)
                elif guardrail_type == GuardrailType.KEYWORD:
                    matched, details, matched_content = self._validate_keyword(content, config)
                elif guardrail_type == GuardrailType.SEMANTIC:
                    matched, details, matched_content = await self._validate_semantic(content, config)
                elif guardrail_type == GuardrailType.LENGTH:
                    matched, details, matched_content = self._validate_length(content, config)
                elif guardrail_type == GuardrailType.FORMAT:
                    matched, details, matched_content = self._validate_format(content, config)

                return GuardrailTestResult(
                    guardrail_id=guardrail_id,
                    guardrail_name=guardrail["guardrail_name"],
                    matched=matched,
                    action=action,
                    details=details,
                    matched_content=matched_content,
                )

        return None

    def invalidate_cache(self, tenant_id: Optional[UUID] = None, sector: Optional[str] = None) -> None:
        """Invalidate guardrails cache."""
        cache_key = (tenant_id, sector)
        if tenant_id is None and sector is None:
            self._guardrails_cache.clear()
            self._cache_time.clear()
            logger.info("Invalidated all guardrails cache")
        else:
            self._guardrails_cache.pop(cache_key, None)
            self._cache_time.pop(cache_key, None)
            logger.info(f"Invalidated guardrails cache for tenant={tenant_id}, sector={sector}")

    async def close(self) -> None:
        """Clean up resources."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        self._http_client = None
        self._db_session = None
        self._embedding_cache.clear()


# Singleton instance
_service: Optional[GuardrailService] = None


def get_guardrail_service() -> GuardrailService:
    """Get the singleton GuardrailService instance."""
    global _service
    if _service is None:
        _service = GuardrailService()
    return _service

"""
Rule Engine — Dynamic prompt injection based on context conditions.

Evaluates rules stored in emma_prompt_rules table and applies actions:
- inject_block: Add content to prompt
- skip_block: Remove/skip a section
- modify_context: Modify template context variables
- set_variable: Set a specific variable value

Usage:
    engine = get_rule_engine()
    actions = await engine.evaluate(context, tenant_id)
    modified_prompt = await engine.apply_actions(prompt, actions)
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from jinja2 import Environment, BaseLoader, TemplateSyntaxError

from app.core.config import settings
from app.schemas.prompts import (
    RuleActionType,
    PromptRuleResponse,
    RuleEvaluationResult,
)

logger = logging.getLogger(__name__)


@dataclass
class RuleContext:
    """Context for rule evaluation."""
    document_type: Optional[str] = None
    action: Optional[str] = None
    sector: Optional[str] = None
    domain: Optional[str] = None
    has_docs: Optional[bool] = None
    user_role: Optional[str] = None
    locale: Optional[str] = None
    custom: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_state(cls, state: Dict[str, Any]) -> "RuleContext":
        """Build RuleContext from RAGState or similar dict."""
        metadata = state.get("metadata", {})
        sector_config = state.get("sector_config", {})
        retrieved_docs = state.get("retrieved_docs", [])

        # Extract sector name
        sector = ""
        if sector_config:
            prompt_key = sector_config.get("system_prompt_key", "")
            sector = prompt_key.replace("sectors.", "") if prompt_key else ""
            if not sector:
                sector = sector_config.get("sector", "")

        # Detect document type from retrieved docs
        doc_type = None
        if retrieved_docs:
            types = [d.get("document_type") or d.get("type") for d in retrieved_docs if d]
            doc_type = types[0] if types else None

        return cls(
            document_type=doc_type,
            action=metadata.get("action_intent"),
            sector=sector,
            domain=metadata.get("domain") or (state.get("detected_domains", []) or [None])[0],
            has_docs=bool(retrieved_docs),
            user_role=metadata.get("user_role"),
            locale=metadata.get("locale", "es"),
            custom=metadata.get("custom_context", {}),
        )


@dataclass
class RuleAction:
    """An action to be applied from a matched rule."""
    rule_id: UUID
    rule_name: str
    action_type: RuleActionType
    config: Dict[str, Any]
    priority: int


class RuleEngine:
    """
    Engine for evaluating and applying prompt injection rules.

    Rules are evaluated in priority order (lower = higher priority).
    Multiple rules can match; their actions are applied in order.
    """

    def __init__(self):
        self._rules_cache: Dict[Optional[UUID], List[Dict[str, Any]]] = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_time: Dict[Optional[UUID], float] = {}
        self._jinja_env = Environment(loader=BaseLoader(), autoescape=False)
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def _load_rules(self, tenant_id: Optional[UUID] = None) -> List[Dict[str, Any]]:
        """Load active rules for tenant via Main API (HTTP proxy pattern)."""
        import time

        cache_key = tenant_id
        now = time.time()

        # Check cache
        if cache_key in self._rules_cache:
            if (now - self._cache_time.get(cache_key, 0)) < self._cache_ttl:
                return self._rules_cache[cache_key]

        try:
            client = await self._get_http_client()
            headers = {
                "X-API-Key": settings.MICROSERVICES_API_KEY,
                "Content-Type": "application/json",
            }
            if tenant_id:
                headers["X-Tenant-ID"] = str(tenant_id)

            # Call Main API to get rules
            url = f"{settings.api_url}/api/v1/prompts/rules"
            response = await client.get(url, headers=headers, params={"active_only": "true"})
            response.raise_for_status()

            rules_data = response.json()

            # Convert to internal format (handle both list and dict responses)
            rules = []
            items = rules_data if isinstance(rules_data, list) else rules_data.get("rules", [])

            for r in items:
                rules.append({
                    "id": r.get("id"),
                    "tenant_id": r.get("tenant_id"),
                    "rule_name": r.get("rule_name"),
                    "description": r.get("description"),
                    "conditions": r.get("conditions", {}),
                    "action_type": r.get("action_type"),
                    "action_config": r.get("action_config", {}),
                    "priority": r.get("priority", 100),
                    "is_active": r.get("is_active", True),
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                })

            # Cache results
            self._rules_cache[cache_key] = rules
            self._cache_time[cache_key] = now

            logger.debug(f"Loaded {len(rules)} rules for tenant {tenant_id} via Main API")
            return rules

        except httpx.HTTPStatusError as e:
            logger.error(f"Main API returned error loading rules: {e.response.status_code}")
            return self._rules_cache.get(cache_key, [])
        except Exception as e:
            logger.error(f"Failed to load rules via Main API: {e}")
            return self._rules_cache.get(cache_key, [])

    def _match_condition(self, condition_value: Any, context_value: Any) -> bool:
        """
        Match a single condition against context value.

        Supports:
        - Exact match: "labor" == "labor"
        - List membership: "labor" in ["labor", "fiscal"]
        - Regex pattern: "/contrato.*/" matches "contrato_laboral"
        - Wildcard: "*" matches anything
        - Negation: "!labor" doesn't match "labor"
        """
        if condition_value is None:
            return True  # No condition = always match

        if condition_value == "*":
            return True

        # Handle negation
        if isinstance(condition_value, str) and condition_value.startswith("!"):
            return not self._match_condition(condition_value[1:], context_value)

        # Handle regex
        if isinstance(condition_value, str) and condition_value.startswith("/") and condition_value.endswith("/"):
            pattern = condition_value[1:-1]
            try:
                return bool(re.match(pattern, str(context_value or ""), re.IGNORECASE))
            except re.error:
                return False

        # Handle list (OR logic)
        if isinstance(condition_value, list):
            return any(self._match_condition(v, context_value) for v in condition_value)

        # Handle boolean
        if isinstance(condition_value, bool):
            return condition_value == context_value

        # Exact match (case-insensitive for strings)
        if isinstance(condition_value, str) and isinstance(context_value, str):
            return condition_value.lower() == context_value.lower()

        return condition_value == context_value

    def _matches_rule(self, rule: Dict[str, Any], context: RuleContext) -> bool:
        """Check if all conditions in a rule match the context."""
        conditions = rule.get("conditions", {})
        if not conditions:
            return True  # Empty conditions = always match

        # Check each condition (AND logic)
        for key, expected in conditions.items():
            if key == "custom":
                # Handle custom conditions
                if isinstance(expected, dict):
                    for custom_key, custom_val in expected.items():
                        actual = context.custom.get(custom_key)
                        if not self._match_condition(custom_val, actual):
                            return False
            else:
                actual = getattr(context, key, None)
                if not self._match_condition(expected, actual):
                    return False

        return True

    async def evaluate(
        self,
        context: RuleContext,
        tenant_id: Optional[UUID] = None,
    ) -> RuleEvaluationResult:
        """
        Evaluate all rules against the given context.

        Returns matched rules and their actions in priority order.
        """
        if not settings.rule_engine_enabled:
            return RuleEvaluationResult(
                matched_rules=[],
                actions_to_apply=[],
                context_modifications={},
            )

        rules = await self._load_rules(tenant_id)
        matched_rules = []
        actions = []
        context_mods = {}

        for rule in rules:
            if self._matches_rule(rule, context):
                matched_rules.append(PromptRuleResponse(
                    id=rule["id"],
                    tenant_id=rule["tenant_id"],
                    rule_name=rule["rule_name"],
                    description=rule.get("description"),
                    conditions=rule["conditions"],
                    action_type=RuleActionType(rule["action_type"]),
                    action_config=rule["action_config"],
                    priority=rule["priority"],
                    is_active=rule["is_active"],
                    created_at=rule.get("created_at"),
                    updated_at=rule.get("updated_at"),
                ))

                action = RuleAction(
                    rule_id=rule["id"],
                    rule_name=rule["rule_name"],
                    action_type=RuleActionType(rule["action_type"]),
                    config=rule["action_config"],
                    priority=rule["priority"],
                )
                actions.append(action)

                # Collect context modifications
                if action.action_type in (RuleActionType.MODIFY_CONTEXT, RuleActionType.SET_VARIABLE):
                    var_name = action.config.get("variable_name")
                    var_value = action.config.get("variable_value")
                    if var_name:
                        context_mods[var_name] = var_value

                logger.debug(f"✅ Rule '{rule['rule_name']}' matched (priority={rule['priority']})")

        return RuleEvaluationResult(
            matched_rules=matched_rules,
            actions_to_apply=[
                {
                    "rule_id": str(a.rule_id),
                    "rule_name": a.rule_name,
                    "action_type": a.action_type.value,
                    "config": a.config,
                    "priority": a.priority,
                }
                for a in actions
            ],
            context_modifications=context_mods,
        )

    async def apply_actions(
        self,
        prompt: str,
        actions: List[RuleAction],
        template_vars: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Apply rule actions to a prompt.

        Args:
            prompt: The original prompt text
            actions: List of actions from evaluate()
            template_vars: Variables for Jinja2 rendering of injected content

        Returns:
            Modified prompt with actions applied
        """
        template_vars = template_vars or {}
        result = prompt
        skip_keys = set()

        for action in actions:
            if action.action_type == RuleActionType.INJECT_BLOCK:
                content = action.config.get("content", "")
                position = action.config.get("position", "prepend")

                # Render Jinja2 content
                try:
                    content = self._jinja_env.from_string(content).render(**template_vars)
                except TemplateSyntaxError:
                    pass

                if position == "prepend":
                    result = content.strip() + "\n\n" + result
                elif position == "append":
                    result = result + "\n\n" + content.strip()
                elif position == "replace":
                    result = content

                logger.debug(f"📝 Injected block from rule '{action.rule_name}' ({position})")

            elif action.action_type == RuleActionType.SKIP_BLOCK:
                skip_key = action.config.get("skip_key")
                if skip_key:
                    skip_keys.add(skip_key)
                    logger.debug(f"⏭️ Will skip block '{skip_key}' from rule '{action.rule_name}'")

        # Note: skip_block handling would require structured prompt format
        # For now, we return the modified prompt
        return result.strip()

    def invalidate_cache(self, tenant_id: Optional[UUID] = None) -> None:
        """Invalidate rules cache for a tenant (or all if None)."""
        if tenant_id is None:
            self._rules_cache.clear()
            self._cache_time.clear()
            logger.info("🗑️ Invalidated all rules cache")
        else:
            self._rules_cache.pop(tenant_id, None)
            self._cache_time.pop(tenant_id, None)
            logger.info(f"🗑️ Invalidated rules cache for tenant {tenant_id}")

    async def close(self) -> None:
        """Clean up resources."""
        if self._db_session:
            # Session factory doesn't need explicit closing
            self._db_session = None


# Singleton instance
_engine: Optional[RuleEngine] = None


def get_rule_engine() -> RuleEngine:
    """Get the singleton RuleEngine instance."""
    global _engine
    if _engine is None:
        _engine = RuleEngine()
    return _engine

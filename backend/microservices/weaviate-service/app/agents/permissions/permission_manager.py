"""
Permission Manager - OpenCode-style permission evaluation.

Evaluates tool calls against rules to determine:
- "allow": Execute immediately without user confirmation
- "ask": Pause and request user confirmation/selection
- "deny": Block the operation entirely

Rules can be:
- Global defaults per tool
- Pattern-based (e.g., "git *": "allow", "rm *": "deny")
- Result-based (e.g., if search returns multiple results → "ask")
"""

import fnmatch
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class PermissionDecision(str, Enum):
    """Permission decision types (matching OpenCode)."""
    ALLOW = "allow"      # Execute without confirmation
    ASK = "ask"          # Request user confirmation
    DENY = "deny"        # Block the operation


@dataclass
class PermissionRule:
    """
    A permission rule for a tool.

    Attributes:
        tool_name: Name of the tool this rule applies to
        pattern: Glob pattern to match against tool input (e.g., "git *")
        decision: What to do when pattern matches
        condition: Optional callable for dynamic evaluation (e.g., result count)
        description: Human-readable description of the rule
    """
    tool_name: str
    pattern: str = "*"
    decision: PermissionDecision = PermissionDecision.ALLOW
    condition: Optional[Callable[[Any], bool]] = None
    description: str = ""


@dataclass
class PermissionRequest:
    """
    A request for user permission/clarification.

    Created when a tool call triggers an "ask" decision.
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_result: Any = None
    decision: PermissionDecision = PermissionDecision.ASK

    # Clarification UI data
    question: str = ""
    header: str = "Confirmación"
    options: List[Dict[str, str]] = field(default_factory=list)
    multi_select: bool = False
    severity: str = "info"  # info, warning, critical

    # State
    resolved: bool = False
    user_response: Optional[List[str]] = None

    def to_sse_event(self) -> Dict[str, Any]:
        """Convert to SSE event data."""
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "question": self.question,
            "header": self.header,
            "options": self.options,
            "multi_select": self.multi_select,
            "severity": self.severity,
        }


class PermissionManager:
    """
    Manages permission rules and evaluates tool calls.

    Similar to OpenCode's permission system but adapted for Emma's
    document management context.

    Default rules for Emma:
    - search_agent: If returns multiple results → ask user to select
    - contract_agent: allow (analysis is safe)
    - bash-like tools: deny (Emma doesn't execute system commands)
    """

    def __init__(self):
        self._rules: List[PermissionRule] = []
        self._pending_requests: Dict[str, PermissionRequest] = {}
        self._setup_default_rules()

    def _setup_default_rules(self):
        """Setup default permission rules for Emma."""

        # Search agent: Ask when multiple results found
        self._rules.append(PermissionRule(
            tool_name="search_agent",
            pattern="*",
            decision=PermissionDecision.ASK,
            condition=lambda result: self._check_multiple_results(result),
            description="Ask user to select when multiple documents found"
        ))

        # Analysis agents: Allow by default (read-only, safe)
        for agent in ["contract_agent", "compliance_agent", "analyst_agent",
                      "summarizer_agent", "labor_agent", "fiscal_agent", "privacy_agent"]:
            self._rules.append(PermissionRule(
                tool_name=agent,
                pattern="*",
                decision=PermissionDecision.ALLOW,
                description=f"Allow {agent} analysis"
            ))

        # HITL tools: Always allow (they ARE the clarification mechanism)
        for tool in ["ask_user_clarification", "ask_confirmation", "suggest_follow_up"]:
            self._rules.append(PermissionRule(
                tool_name=tool,
                pattern="*",
                decision=PermissionDecision.ALLOW,
                description="Always allow HITL tools"
            ))

        logger.info(f"✅ PermissionManager initialized with {len(self._rules)} rules")

    def _check_multiple_results(self, result: Any) -> bool:
        """
        Check if a search result contains multiple documents.

        Returns True if user should be asked to select.
        """
        if result is None:
            return False

        # Handle different result formats
        if isinstance(result, str):
            try:
                import json
                data = json.loads(result)
                if isinstance(data, dict):
                    # Check for results/documents arrays
                    for key in ["results", "documents", "items", "matches"]:
                        if key in data and isinstance(data[key], list):
                            return len(data[key]) > 1
                elif isinstance(data, list):
                    return len(data) > 1
            except:
                pass
        elif isinstance(result, list):
            return len(result) > 1
        elif isinstance(result, dict):
            for key in ["results", "documents", "items", "matches"]:
                if key in result and isinstance(result[key], list):
                    return len(result[key]) > 1

        return False

    def evaluate(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_result: Any = None
    ) -> PermissionDecision:
        """
        Evaluate a tool call against permission rules.

        Args:
            tool_name: Name of the tool being called
            tool_input: Input parameters to the tool
            tool_result: Result of tool execution (for post-execution checks)

        Returns:
            PermissionDecision: allow, ask, or deny
        """
        # Find matching rules for this tool
        matching_rules = [r for r in self._rules if r.tool_name == tool_name]

        if not matching_rules:
            # No rules = allow by default
            return PermissionDecision.ALLOW

        # Evaluate rules in order (last match wins, like OpenCode)
        decision = PermissionDecision.ALLOW

        for rule in matching_rules:
            # Check pattern match
            input_str = str(tool_input.get("query", "") or tool_input.get("document_id", "") or "")
            if fnmatch.fnmatch(input_str, rule.pattern) or rule.pattern == "*":
                # Check condition if present
                if rule.condition is not None:
                    if rule.condition(tool_result):
                        decision = rule.decision
                        logger.debug(f"Rule matched (condition): {rule.description} → {decision}")
                else:
                    decision = rule.decision
                    logger.debug(f"Rule matched: {rule.description} → {decision}")

        return decision

    def create_clarification_request(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_result: Any,
        question: str,
        options: List[Dict[str, str]],
        header: str = "Selecciona una opción",
        multi_select: bool = False,
    ) -> PermissionRequest:
        """
        Create a permission request for user clarification.

        Args:
            tool_name: The tool that triggered the request
            tool_input: Original tool input
            tool_result: Result that requires clarification
            question: Question to show the user
            options: List of options [{label, value, description}]
            header: Short header for the UI
            multi_select: Allow multiple selections

        Returns:
            PermissionRequest that can be sent to frontend
        """
        request = PermissionRequest(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_result=tool_result,
            question=question,
            header=header,
            options=options,
            multi_select=multi_select,
        )

        self._pending_requests[request.request_id] = request
        logger.info(f"🤔 Created clarification request: {request.request_id} for {tool_name}")

        return request

    def resolve_request(self, request_id: str, user_response: List[str]) -> Optional[PermissionRequest]:
        """
        Resolve a pending permission request with user's response.

        Args:
            request_id: ID of the request
            user_response: User's selected values

        Returns:
            The resolved request, or None if not found
        """
        request = self._pending_requests.get(request_id)
        if request:
            request.resolved = True
            request.user_response = user_response
            logger.info(f"✅ Resolved request {request_id}: {user_response}")
            return request

        logger.warning(f"⚠️ Request not found: {request_id}")
        return None

    def get_pending_request(self, request_id: str) -> Optional[PermissionRequest]:
        """Get a pending request by ID."""
        return self._pending_requests.get(request_id)

    def add_rule(self, rule: PermissionRule):
        """Add a custom permission rule."""
        self._rules.append(rule)
        logger.info(f"Added rule: {rule.tool_name} / {rule.pattern} → {rule.decision}")


# Singleton instance
_manager: Optional[PermissionManager] = None


def get_permission_manager() -> PermissionManager:
    """Get or create the permission manager singleton."""
    global _manager
    if _manager is None:
        _manager = PermissionManager()
    return _manager

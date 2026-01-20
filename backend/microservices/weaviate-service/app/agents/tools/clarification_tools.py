"""
Human-in-the-Loop (HITL) Clarification Tools for Qwen-Agent Framework.

These tools allow Emma to ask users for clarification when:
- Multiple options are available (which document? which analysis type?)
- User intent is ambiguous
- Confirmation is needed before important actions
- User preferences need to be captured

Similar to Claude Code's AskUserQuestion tool, these enable
interactive decision-making with the user.

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework @ai_function pattern
- Uses class-based tools with @register_tool decorator
"""

import json
import logging
from typing import List, Optional, Union

from qwen_agent.tools.base import BaseTool, register_tool

logger = logging.getLogger(__name__)


# Global storage for pending clarifications (in production, use Redis)
_pending_clarifications: dict = {}


# =============================================================================
# Qwen-Agent Tool Classes
# =============================================================================

@register_tool('ask_user_clarification')
class AskUserClarificationTool(BaseTool):
    """
    Ask the user for clarification when multiple options are available or intent is unclear.

    Use this tool when:
    - Multiple documents match a search and you need to know which one to analyze
    - The user's request is ambiguous (e.g., "analyze" could mean legal, fiscal, or compliance)
    - You need confirmation before a potentially important action
    - User preferences would improve the response quality

    The tool returns a JSON response that will be processed by the streaming system
    to display options to the user.
    """

    description = '''Ask the user for clarification when multiple options are available or intent is unclear.

Use this when:
- Multiple documents match a search
- User's request is ambiguous
- Confirmation needed before important action
- User preferences would improve response

Returns JSON that triggers a clarification UI in the frontend.'''

    parameters = [
        {
            'name': 'question',
            'type': 'string',
            'description': 'The question to ask the user. Should be clear and specific.',
            'required': True
        },
        {
            'name': 'options',
            'type': 'string',
            'description': 'JSON array of options. Each option: {label: string, value: string, description?: string}',
            'required': True
        },
        {
            'name': 'header',
            'type': 'string',
            'description': "Short label for the question (max 15 chars), e.g., 'Documento', 'Tipo de analisis'",
            'required': False
        },
        {
            'name': 'multi_select',
            'type': 'boolean',
            'description': 'If true, user can select multiple options (default false)',
            'required': False
        },
        {
            'name': 'context_hint',
            'type': 'string',
            'description': 'Internal hint about what triggered this clarification',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute clarification request."""
        if isinstance(params, str):
            params = json.loads(params)

        question = params.get('question')
        options = params.get('options')
        header = params.get('header', 'Opcion')
        multi_select = params.get('multi_select', False)
        context_hint = params.get('context_hint', '')

        logger.info(f"CLARIFICATION REQUESTED: {question}")
        logger.info(f"Options: {options}")
        logger.info(f"Multi-select: {multi_select}, Header: {header}")

        try:
            parsed_options = json.loads(options)
            if not isinstance(parsed_options, list):
                raise ValueError("Options must be a JSON array")

            validated_options = []
            for i, opt in enumerate(parsed_options):
                if not isinstance(opt, dict):
                    raise ValueError(f"Option {i} must be an object")
                if "label" not in opt or "value" not in opt:
                    raise ValueError(f"Option {i} missing 'label' or 'value'")
                validated_options.append({
                    "label": str(opt["label"]),
                    "value": str(opt["value"]),
                    "description": str(opt.get("description", ""))
                })

            clarification = {
                "_type": "clarification_request",
                "question": question,
                "header": header[:15],
                "options": validated_options,
                "multi_select": multi_select,
                "context_hint": context_hint,
            }

            return json.dumps(clarification, ensure_ascii=False)

        except json.JSONDecodeError as e:
            logger.error(f"Invalid options JSON: {e}")
            return json.dumps({
                "error": f"Invalid options format: {e}",
                "fallback": "Proceeding with default behavior"
            })
        except Exception as e:
            logger.error(f"Clarification tool error: {e}")
            return json.dumps({
                "error": str(e),
                "fallback": "Proceeding with default behavior"
            })


@register_tool('ask_confirmation')
class AskConfirmationTool(BaseTool):
    """
    Ask the user for confirmation before performing an important action.

    Use this when:
    - About to modify or delete documents
    - Sending external communications
    - Making changes that can't be easily undone
    - The action has significant consequences
    """

    description = '''Ask the user for confirmation before performing an important action.

Use this when:
- About to modify or delete documents
- Sending external communications
- Making irreversible changes
- Action has significant consequences

Returns JSON with confirmation request.'''

    parameters = [
        {
            'name': 'action',
            'type': 'string',
            'description': 'Description of the action that needs confirmation',
            'required': True
        },
        {
            'name': 'details',
            'type': 'string',
            'description': 'Additional details about what will happen',
            'required': False
        },
        {
            'name': 'severity',
            'type': 'string',
            'description': 'Severity level: info, warning, or critical (default: info)',
            'required': False
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute confirmation request."""
        if isinstance(params, str):
            params = json.loads(params)

        action = params.get('action')
        details = params.get('details', '')
        severity = params.get('severity', 'info')

        logger.info(f"CONFIRMATION REQUESTED: {action} (severity: {severity})")

        severity_labels = {
            "info": "Confirmar accion",
            "warning": "Accion con precaucion",
            "critical": "Accion critica"
        }

        confirmation = {
            "_type": "confirmation_request",
            "question": f"Confirmas que deseas {action}?",
            "header": severity_labels.get(severity, "Confirmar"),
            "options": [
                {"label": "Si, continuar", "value": "confirm", "description": details or "Ejecutar la accion"},
                {"label": "No, cancelar", "value": "cancel", "description": "No realizar ningun cambio"}
            ],
            "multi_select": False,
            "severity": severity,
        }

        return json.dumps(confirmation, ensure_ascii=False)


@register_tool('suggest_follow_up')
class SuggestFollowUpTool(BaseTool):
    """
    Suggest follow-up actions after completing a task.

    Use this to proactively offer related actions the user might want to take.
    """

    description = '''Suggest follow-up actions after completing a task.

Use this to proactively offer related actions the user might want to take.

Returns JSON with suggestions for the UI.'''

    parameters = [
        {
            'name': 'context',
            'type': 'string',
            'description': 'Brief context of what was just completed',
            'required': True
        },
        {
            'name': 'suggestions',
            'type': 'string',
            'description': 'JSON array of follow-up suggestions: [{label, action, description}]',
            'required': True
        }
    ]

    def call(self, params: Union[str, dict], **kwargs) -> str:
        """Execute follow-up suggestion."""
        if isinstance(params, str):
            params = json.loads(params)

        context = params.get('context')
        suggestions = params.get('suggestions')

        logger.info(f"FOLLOW-UP SUGGESTIONS for: {context}")

        try:
            parsed = json.loads(suggestions)

            follow_up = {
                "_type": "follow_up_suggestions",
                "context": context,
                "suggestions": parsed,
            }

            return json.dumps(follow_up, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Follow-up suggestions error: {e}")
            return json.dumps({"error": str(e)})


# =============================================================================
# Helper Functions (unchanged from original)
# =============================================================================

def is_clarification_response(text: str) -> bool:
    """
    Check if a response contains a clarification request.

    Used by the streaming system to detect when Emma needs user input.

    Detects two formats:
    1. Direct clarification response (from HITL tools):
       {"_type": "clarification_request", ...}

    2. OpenCode-style embedded clarification (from search tools):
       {"results": [...], "_clarification_needed": true, "_clarification": {...}}
    """
    try:
        data = json.loads(text)

        if data.get("_type") in ("clarification_request", "confirmation_request", "follow_up_suggestions"):
            return True

        if data.get("_clarification_needed") and data.get("_clarification"):
            return True

        return False
    except:
        return False


def parse_clarification_response(text: str) -> Optional[dict]:
    """
    Parse a clarification response for the streaming system.

    Returns the structured data if valid, None otherwise.

    Handles two formats:
    1. Direct clarification response (from HITL tools)
    2. OpenCode-style embedded clarification (from search tools)
    """
    try:
        data = json.loads(text)

        if data.get("_type") in ("clarification_request", "confirmation_request", "follow_up_suggestions"):
            return data

        if data.get("_clarification_needed") and data.get("_clarification"):
            clarification = data.get("_clarification")
            clarification["_original_results"] = data.get("results", [])
            logger.info(f"OPENCODE-STYLE: Detected clarification needed for {len(data.get('results', []))} results")
            return clarification

        return None
    except:
        return None


def extract_selected_document(original_results: List[dict], selected_value: str) -> Optional[dict]:
    """
    Extract the selected document from original search results.

    Used after user makes a clarification selection to continue
    analysis with the chosen document.

    Args:
        original_results: List of documents from search results
        selected_value: The document ID the user selected

    Returns:
        The selected document dict, or None if not found
    """
    for doc in original_results:
        if str(doc.get("id")) == str(selected_value):
            return doc
    return None


# =============================================================================
# Tool Registration Exports
# =============================================================================

CLARIFICATION_TOOLS = [
    AskUserClarificationTool,
    AskConfirmationTool,
    SuggestFollowUpTool,
]

CLARIFICATION_TOOL_NAMES = [
    'ask_user_clarification',
    'ask_confirmation',
    'suggest_follow_up',
]


def get_clarification_tools() -> list:
    """
    Get list of clarification tool names for use in Qwen-Agent Assistant's function_list.
    """
    return CLARIFICATION_TOOL_NAMES

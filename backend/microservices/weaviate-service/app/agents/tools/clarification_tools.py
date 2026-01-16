"""
Human-in-the-Loop (HITL) Clarification Tools for Emma.

These tools allow Emma to ask users for clarification when:
- Multiple options are available (which document? which analysis type?)
- User intent is ambiguous
- Confirmation is needed before important actions
- User preferences need to be captured

Similar to Claude Code's AskUserQuestion tool, these enable
interactive decision-making with the user.

Usage in Emma:
    When Emma calls ask_user_clarification(), the system:
    1. Pauses execution
    2. Sends a SSE event "clarification_needed" to frontend
    3. Frontend displays options to user
    4. User selects option(s)
    5. Response is sent back to continue execution
"""

import json
import logging
from typing import Annotated, Dict, List, Optional
from pydantic import Field

from agent_framework import ai_function

logger = logging.getLogger(__name__)


# Global storage for pending clarifications (in production, use Redis)
# Key: session_id, Value: clarification request
_pending_clarifications: dict = {}


@ai_function
async def ask_user_clarification(
    question: Annotated[str, Field(description="The question to ask the user. Should be clear and specific.")],
    options: Annotated[str, Field(description="JSON array of options. Each option: {label: string, value: string, description?: string}")],
    header: Annotated[str, Field(description="Short label for the question (max 15 chars), e.g., 'Documento', 'Tipo de análisis'")] = "Opción",
    multi_select: Annotated[bool, Field(description="If true, user can select multiple options")] = False,
    context_hint: Annotated[str, Field(description="Internal hint about what triggered this clarification")] = "",
) -> str:
    """
    Ask the user for clarification when multiple options are available or intent is unclear.

    Use this tool when:
    - Multiple documents match a search and you need to know which one to analyze
    - The user's request is ambiguous (e.g., "analyze" could mean legal, fiscal, or compliance)
    - You need confirmation before a potentially important action
    - User preferences would improve the response quality

    The tool returns a JSON response that will be processed by the streaming system
    to display options to the user. The user's selection will be provided in the
    next message as context.

    Examples:
        # Single select - which document
        ask_user_clarification(
            question="He encontrado varios contratos. ¿Cuál te gustaría analizar?",
            options='[{"label": "Contrato NDA 2024", "value": "doc_123"}, {"label": "Contrato Servicios", "value": "doc_456"}, {"label": "Analizar todos", "value": "all"}]',
            header="Documento"
        )

        # Multi select - analysis types
        ask_user_clarification(
            question="¿Qué aspectos del contrato te gustaría analizar?",
            options='[{"label": "Riesgos legales", "value": "legal"}, {"label": "Aspectos fiscales", "value": "fiscal"}, {"label": "Cumplimiento RGPD", "value": "gdpr"}]',
            header="Análisis",
            multi_select=True
        )

    Args:
        question: Clear question for the user (in their language)
        options: JSON array of selectable options
        header: Short category label (e.g., "Documento", "Análisis")
        multi_select: Allow multiple selections if True
        context_hint: Internal context (not shown to user)

    Returns:
        JSON string with the clarification request that triggers UI display
    """
    logger.info(f"🤔 CLARIFICATION REQUESTED: {question}")
    logger.info(f"📋 Options: {options}")
    logger.info(f"📋 Multi-select: {multi_select}, Header: {header}")

    try:
        # Parse and validate options
        parsed_options = json.loads(options)
        if not isinstance(parsed_options, list):
            raise ValueError("Options must be a JSON array")

        # Validate each option has required fields
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

        # Build the clarification response
        # This JSON structure is recognized by the streaming system
        # and triggers a "clarification_needed" SSE event
        clarification = {
            "_type": "clarification_request",
            "question": question,
            "header": header[:15],  # Max 15 chars
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


@ai_function
async def ask_confirmation(
    action: Annotated[str, Field(description="Description of the action that needs confirmation")],
    details: Annotated[str, Field(description="Additional details about what will happen")] = "",
    severity: Annotated[str, Field(description="Severity level: info, warning, or critical")] = "info",
) -> str:
    """
    Ask the user for confirmation before performing an important action.

    Use this when:
    - About to modify or delete documents
    - Sending external communications
    - Making changes that can't be easily undone
    - The action has significant consequences

    Args:
        action: What action needs confirmation (e.g., "Eliminar 5 documentos")
        details: Additional context about the action
        severity: Impact level - info (normal), warning (caution), critical (high risk)

    Returns:
        JSON with confirmation request
    """
    logger.info(f"⚠️ CONFIRMATION REQUESTED: {action} (severity: {severity})")

    # Map severity to Spanish labels
    severity_labels = {
        "info": "Confirmar acción",
        "warning": "Acción con precaución",
        "critical": "Acción crítica"
    }

    confirmation = {
        "_type": "confirmation_request",
        "question": f"¿Confirmas que deseas {action}?",
        "header": severity_labels.get(severity, "Confirmar"),
        "options": [
            {"label": "Sí, continuar", "value": "confirm", "description": details or "Ejecutar la acción"},
            {"label": "No, cancelar", "value": "cancel", "description": "No realizar ningún cambio"}
        ],
        "multi_select": False,
        "severity": severity,
    }

    return json.dumps(confirmation, ensure_ascii=False)


@ai_function
async def suggest_follow_up(
    context: Annotated[str, Field(description="Brief context of what was just completed")],
    suggestions: Annotated[str, Field(description="JSON array of follow-up suggestions: [{label, action, description}]")],
) -> str:
    """
    Suggest follow-up actions after completing a task.

    Use this to proactively offer related actions the user might want to take.

    Args:
        context: What was just completed
        suggestions: JSON array of suggested next actions

    Returns:
        JSON with suggestions for the UI
    """
    logger.info(f"💡 FOLLOW-UP SUGGESTIONS for: {context}")

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

        # Direct clarification (from HITL tools)
        if data.get("_type") in ("clarification_request", "confirmation_request", "follow_up_suggestions"):
            return True

        # OpenCode-style embedded clarification (from search tools)
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

        # Direct clarification (from HITL tools)
        if data.get("_type") in ("clarification_request", "confirmation_request", "follow_up_suggestions"):
            return data

        # OpenCode-style embedded clarification (from search tools with multiple results)
        if data.get("_clarification_needed") and data.get("_clarification"):
            clarification = data.get("_clarification")
            # Add the original results so they can be used after selection
            clarification["_original_results"] = data.get("results", [])
            logger.info(f"🔒 OPENCODE-STYLE: Detected clarification needed for {len(data.get('results', []))} results")
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

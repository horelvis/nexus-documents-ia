"""LLM-powered field detection for documents."""

import logging
import os
import re
from pathlib import Path

import yaml

_SAFE_FIELD_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

from app.clients.llm_client import get_llm_client
from app.core.config import get_settings
from app.schemas.analyze import AnalyzeResponse, DetectedField, FieldType

logger = logging.getLogger(__name__)

_prompts: dict | None = None


def _load_prompts() -> dict:
    """Load YAML prompt fallbacks."""
    global _prompts
    if _prompts is None:
        prompt_path = Path(__file__).parent.parent.parent / "config" / "prompts" / "forge_prompts.yaml"
        if prompt_path.exists():
            with open(prompt_path) as f:
                _prompts = yaml.safe_load(f)
        else:
            _prompts = {}
    return _prompts


class ForgeAnalyzer:
    """Detects variable fields in a document using LLM analysis."""

    async def analyze(
        self,
        document_text: str,
        document_title: str,
        user_intent: str,
        max_fields: int = 30,
    ) -> dict:
        """Analyze document text and return detected fields.

        Returns dict with keys: document_type, fields, confidence.
        """
        settings = get_settings()

        # Truncate to max chars for LLM context budget
        text = document_text[: settings.max_source_chars]

        prompts = _load_prompts()
        system_prompt = prompts.get("forge", {}).get("analyze", {}).get(
            "system", "You are a document analysis expert. Return JSON."
        )
        user_template = prompts.get("forge", {}).get("analyze", {}).get(
            "user", "Analyze: {{text}}"
        )

        user_prompt = (
            user_template
            .replace("{{title}}", document_title)
            .replace("{{intent}}", user_intent)
            .replace("{{text}}", text)
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt + "\n\n/no_think"},
        ]

        llm = get_llm_client()

        try:
            result = await llm.chat_json(messages)
        except Exception as e:
            logger.error("LLM analysis failed: %s", e)
            # Return empty analysis on failure
            return {"document_type": "", "fields": [], "confidence": 0.0}

        # Validate and normalize fields
        raw_fields = result.get("fields", []) if isinstance(result, dict) else []
        fields = []
        for f in raw_fields[:max_fields]:
            try:
                # Sanitize field_name (prevent Jinja2 injection in downstream markers)
                raw_name = f.get("field_name", "unknown")
                if not _SAFE_FIELD_NAME.match(raw_name):
                    # Sanitize: replace invalid chars with underscore
                    raw_name = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name)
                    if not raw_name or raw_name[0].isdigit():
                        raw_name = f"field_{raw_name}"

                # Normalize field_type
                ft = f.get("field_type", "text")
                try:
                    ft = FieldType(ft)
                except ValueError:
                    ft = FieldType.TEXT

                fields.append(
                    DetectedField(
                        field_name=raw_name,
                        label=f.get("label", f.get("field_name", "")),
                        current_value=str(f.get("current_value", "")),
                        field_type=ft,
                        required=f.get("required", True),
                        context_hint=f.get("context_hint", ""),
                        suggested_value=f.get("suggested_value"),
                    ).model_dump()
                )
            except Exception as e:
                logger.warning("Skipping invalid field %s: %s", f, e)

        return {
            "document_type": result.get("document_type", "") if isinstance(result, dict) else "",
            "fields": fields,
            "confidence": float(result.get("confidence", 0.0)) if isinstance(result, dict) else 0.0,
        }


_analyzer = None


def get_analyzer() -> ForgeAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = ForgeAnalyzer()
    return _analyzer

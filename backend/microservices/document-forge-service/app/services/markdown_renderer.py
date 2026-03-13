"""Markdown output generation from analyzed/rendered documents."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MarkdownRenderer:
    """Generates a Markdown representation of a forge session result."""

    def render(
        self,
        document_title: str,
        fields: list[dict[str, Any]],
        field_values: dict[str, str],
    ) -> str:
        """Generate Markdown showing the field changes made.

        This is a summary view, not a full document render — useful for
        chat-based UX where the user wants to see what changed.
        """
        lines = [f"# {document_title}", ""]
        lines.append("## Campos modificados")
        lines.append("")
        lines.append("| Campo | Valor original | Nuevo valor |")
        lines.append("|-------|---------------|-------------|")

        for field in fields:
            name = field.get("field_name", "")
            label = field.get("label", name)
            original = field.get("current_value", "")
            new_val = field_values.get(name, original)
            changed = " *" if new_val != original else ""
            lines.append(f"| {label} | {original} | {new_val}{changed} |")

        lines.append("")
        lines.append("---")
        lines.append("*Generado por Document Forge Service*")

        return "\n".join(lines)


_renderer = None


def get_markdown_renderer() -> MarkdownRenderer:
    global _renderer
    if _renderer is None:
        _renderer = MarkdownRenderer()
    return _renderer

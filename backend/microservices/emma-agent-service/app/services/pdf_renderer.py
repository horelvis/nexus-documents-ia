"""
PDF renderer for verified generation reports.

Uses Jinja2 for HTML templating and WeasyPrint for PDF conversion.
"""

import logging
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader
import markdown

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "config" / "templates"


class PDFRenderer:
    """Render verified generation results as PDF."""

    def __init__(self):
        self.env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

    def render_verified_report(self, data: Dict[str, Any]) -> bytes:
        """
        Render a verified document report as PDF bytes.

        Args:
            data: Dict with keys: query, session_id, created_at, document_text,
                  claims, claims_verified, claims_corrected, claims_rejected,
                  average_confidence, execution_time_ms

        Returns:
            PDF file content as bytes.
        """
        import weasyprint

        template = self.env.get_template("verified_report.html")

        # Convert markdown document_text to HTML
        document_html = markdown.markdown(
            data.get("document_text", ""),
            extensions=["tables", "fenced_code"],
        )

        html_str = template.render(
            **data,
            document_html=document_html,
        )

        pdf_bytes = weasyprint.HTML(string=html_str).write_pdf()
        logger.info(f"PDF rendered: {len(pdf_bytes)} bytes for session {data.get('session_id', 'unknown')[:16]}")
        return pdf_bytes


_renderer = None


def get_pdf_renderer() -> PDFRenderer:
    """Get singleton PDFRenderer instance."""
    global _renderer
    if _renderer is None:
        _renderer = PDFRenderer()
    return _renderer

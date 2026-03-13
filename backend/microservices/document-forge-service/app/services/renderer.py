"""docxtpl-based DOCX rendering — fills Jinja2 markers with field values."""

import logging
from io import BytesIO

from docxtpl import DocxTemplate

logger = logging.getLogger(__name__)


class ForgeRenderer:
    """Renders a prepared DOCX template by filling {{markers}} with values."""

    def render(self, template_bytes: bytes, field_values: dict[str, str]) -> bytes:
        """Fill Jinja2 markers in a prepared DOCX template.

        Args:
            template_bytes: DOCX bytes with {{field_name}} markers.
            field_values: Map of field_name -> new value.

        Returns:
            Rendered DOCX bytes with all markers replaced.
        """
        tpl = DocxTemplate(BytesIO(template_bytes))
        tpl.render(field_values)
        buf = BytesIO()
        tpl.save(buf)
        return buf.getvalue()


_renderer = None


def get_renderer() -> ForgeRenderer:
    global _renderer
    if _renderer is None:
        _renderer = ForgeRenderer()
    return _renderer

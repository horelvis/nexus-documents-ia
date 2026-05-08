"""
TemplateExecutor — load and execute Cypher templates from YAML registry.

Templates are loaded from config/cypher_templates.yaml on first access.
Each template contains a Cypher pattern with $-prefixed parameters.
Collection scope ($collection) is injected automatically.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "cypher_templates.yaml"

_DEFAULT_QUERY_LIMIT = 100


class TemplateExecutor:
    """Load Cypher templates and prepare queries for execution."""

    def __init__(self) -> None:
        self._templates: Optional[Dict[str, Dict]] = None

    @property
    def templates(self) -> Dict[str, Dict]:
        if self._templates is None:
            self._load()
        return self._templates

    def _load(self) -> None:
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._templates = data.get("templates", {})
            logger.info("Loaded %d Cypher templates from %s", len(self._templates), _CONFIG_PATH)
        except FileNotFoundError:
            logger.warning("Cypher templates not found at %s", _CONFIG_PATH)
            self._templates = {}

    def get_template(self, name: str) -> Dict[str, Any]:
        """Get a template by name. Raises KeyError if not found."""
        if name not in self.templates:
            raise KeyError(f"Unknown Cypher template: {name!r}")
        return self.templates[name]

    def list_templates(self) -> List[Dict[str, Any]]:
        """List all templates with metadata."""
        return [
            {
                "name": name,
                "description": tmpl.get("description", ""),
                "hops": tmpl.get("hops", 0),
            }
            for name, tmpl in self.templates.items()
        ]

    def build_query(self, name: str, **kwargs) -> str:
        """Return the raw Cypher pattern for a template."""
        tmpl = self.get_template(name)
        return tmpl["pattern"].strip()

    def build_params(self, name: str, **kwargs) -> Dict[str, Any]:
        """Build parameter dict for a template query.

        Injects collection (nullable) and query_limit automatically.
        All extra kwargs are passed through as query parameters.
        """
        params = {
            "collection": kwargs.pop("collection", None),
            "query_limit": kwargs.pop("query_limit", _DEFAULT_QUERY_LIMIT),
        }
        params.update(kwargs)
        return params

    async def execute(
        self,
        name: str,
        client,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute a template and return results with metadata."""
        tmpl = self.get_template(name)
        query = tmpl["pattern"].strip()
        params = self.build_params(name, **kwargs)

        rows = await client.execute_cypher(query, params=params)

        return {
            "results": rows,
            "template": name,
            "hops": tmpl.get("hops", 0),
            "count": len(rows),
        }

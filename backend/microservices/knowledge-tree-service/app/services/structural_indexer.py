"""
Structural indexer for Apache AGE (Knowledge Graph).

Builds/updates structural_folder and structural_document nodes using
connector metadata and learned context.
"""

import logging
import re
from typing import Any, Dict, Optional

from app.core.config import settings
from app.services.age_client import age_client

logger = logging.getLogger(__name__)

_CAMEL_RE = re.compile(r"(?<!^)([A-Z])")

_GENERIC_TYPES = {
    "cm:folder",
    "cm:content",
    "folder",
    "document",
}

# Alfresco infrastructure path segments (not business-relevant)
_INFRA_PATH_SEGMENTS = {
    "company home", "sites", "documentlibrary", "document library",
    "app:company_home", "st:sites", "cm:documentlibrary",
}


def _escape(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.replace("'", "''")


def _normalize_type_name(value: str) -> str:
    """Normalize a type name to snake_case. Handles camelCase, ALL_CAPS, and mixed."""
    trimmed = value.strip().replace("-", "_").replace(" ", "_")
    # Only split camelCase if the string has mixed case (not ALL_CAPS)
    if not trimmed.isupper() and not trimmed.islower():
        trimmed = _CAMEL_RE.sub(r"_\1", trimmed)
    # Collapse multiple underscores
    result = re.sub(r"_+", "_", trimmed).strip("_").lower()
    return result


def _extract_node_type(connector_metadata: Dict[str, Any]) -> Optional[str]:
    for key in (
        "alfresco_node_type",
        "alfresco_content_type",
        "nodeType",
        "parent_folder_type",
    ):
        node_type = connector_metadata.get(key)
        if node_type:
            return str(node_type)
    return None


def _extract_business_path(path_parts: list) -> list:
    """
    Strip Alfresco infrastructure segments from a path, keeping only
    business-relevant segments.

    Example:
        ["Company Home", "Sites", "abc123", "documentLibrary", "CLIENTES", "DNI-001", "DOCS"]
        → ["CLIENTES", "DNI-001", "DOCS"]
    """
    # Find the index after the last infra segment
    last_infra = -1
    for i, part in enumerate(path_parts):
        if part.lower() in _INFRA_PATH_SEGMENTS:
            last_infra = i
        # Also skip the site ID segment right after "Sites"
        if i > 0 and path_parts[i - 1].lower() in ("sites", "st:sites"):
            last_infra = i
    return path_parts[last_infra + 1:]


def _infer_folder_type(
    connector_metadata: Dict[str, Any],
    learned_context: Dict[str, Any],
    path_parts: Optional[list] = None,
) -> Optional[str]:
    # 1. Explicit metadata
    explicit = connector_metadata.get("folder_type") or learned_context.get("folder_type")
    if isinstance(explicit, str) and explicit.strip():
        normalized = _normalize_type_name(explicit)
        if normalized not in _GENERIC_TYPES:
            return normalized

    # 2. Infer from path: use the first business-level segment as folder type
    if path_parts:
        business_parts = _extract_business_path(path_parts)
        if business_parts:
            # First business segment = top-level category (e.g. "CLIENTES")
            return _normalize_type_name(business_parts[0])

    return None


def _infer_document_semantic_type(
    connector_metadata: Dict[str, Any],
    learned_context: Dict[str, Any],
    folder_parts: Optional[list] = None,
) -> Optional[str]:
    # 1. Explicit metadata
    semantic_type = learned_context.get("semantic_type") or connector_metadata.get("semantic_type")
    if semantic_type:
        normalized = _normalize_type_name(str(semantic_type))
        if normalized not in _GENERIC_TYPES:
            return normalized

    # 2. Infer from path: use the deepest business folder that looks like
    #    a category name (alphabetic, not an ID like "09678350L")
    if folder_parts:
        business_parts = _extract_business_path(folder_parts)
        for part in reversed(business_parts):
            # Skip segments that look like IDs (contain digits mixed with few letters)
            cleaned = part.replace("_", "").replace("-", "").replace(" ", "")
            if cleaned.isalpha() and len(cleaned) >= 3:
                return _normalize_type_name(part)

    return None


def _is_folder(connector_metadata: Dict[str, Any], learned_context: Dict[str, Any]) -> bool:
    if connector_metadata.get("is_folder") is True:
        return True
    if learned_context.get("is_folder") is True:
        return True
    return False


def _split_path(file_path: Optional[str]) -> list:
    if not file_path:
        return []
    normalized = file_path.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]
    return parts


class StructuralIndexer:
    async def index(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not settings.rag_knowledge_graph_enabled:
            return {"success": False, "error": "Knowledge graph disabled"}

        await age_client.initialize()

        tenant_id = str(payload.get("tenant_id") or "").strip()
        document_id = str(payload.get("document_id") or "").strip()
        if not tenant_id or not document_id:
            return {"success": False, "error": "tenant_id and document_id are required"}

        connector_metadata = payload.get("connector_metadata") or {}
        learned_context = payload.get("learned_context") or {}
        file_path = payload.get("file_path") or ""
        connector_id = payload.get("connector_id")
        weaviate_document_id = payload.get("weaviate_document_id")

        is_folder = _is_folder(connector_metadata, learned_context)
        path_parts = _split_path(file_path)

        if is_folder:
            folder_name = path_parts[-1] if path_parts else connector_metadata.get("folder_name")
            folder_path = "/" + "/".join(path_parts) if path_parts else None
            folder_type = _infer_folder_type(connector_metadata, learned_context, path_parts)
            return await self._upsert_folder(
                tenant_id=tenant_id,
                folder_id=document_id,
                name=folder_name,
                path=folder_path,
                folder_type=folder_type,
                connector_id=connector_id,
                node_type=_extract_node_type(connector_metadata),
            )

        # Document
        doc_name = path_parts[-1] if path_parts else None
        folder_parts = path_parts[:-1]
        folder_path = "/" + "/".join(folder_parts) if folder_parts else None
        folder_name = folder_parts[-1] if folder_parts else None
        folder_type = _infer_folder_type(connector_metadata, learned_context, folder_parts)

        semantic_type = _infer_document_semantic_type(connector_metadata, learned_context, folder_parts)
        domain = learned_context.get("domain")
        document_type = _extract_node_type(connector_metadata)

        return await self._upsert_document(
            tenant_id=tenant_id,
            document_id=document_id,
            title=doc_name or payload.get("title"),
            file_path=file_path or None,
            folder_path=folder_path,
            semantic_type=semantic_type,
            domain=domain,
            document_type=document_type,
            connector_id=connector_id,
            weaviate_document_id=weaviate_document_id,
            folder_name=folder_name,
            folder_type=folder_type,
        )

    async def _upsert_folder(
        self,
        tenant_id: str,
        folder_id: str,
        name: Optional[str],
        path: Optional[str],
        folder_type: Optional[str],
        connector_id: Optional[str],
        node_type: Optional[str],
    ) -> Dict[str, Any]:
        graph = settings.age_graph_name
        if not path and not name:
            return {"success": False, "error": "Folder path or name required"}

        set_clauses = []
        if name:
            set_clauses.append(f"f.name = '{_escape(name)}'")
        if path:
            set_clauses.append(f"f.path = '{_escape(path)}'")
        if folder_type:
            set_clauses.append(f"f.folder_type = '{_escape(folder_type)}'")
        if connector_id:
            set_clauses.append(f"f.connector_id = '{_escape(str(connector_id))}'")
        if node_type:
            set_clauses.append(f"f.node_type = '{_escape(node_type)}'")
        if folder_id:
            set_clauses.append(f"f.folder_id = '{_escape(folder_id)}'")

        set_stmt = "SET " + ", ".join(set_clauses) if set_clauses else ""
        merge_key = f"tenant_id: '{_escape(tenant_id)}'"
        if path:
            merge_key += f", path: '{_escape(path)}'"
        else:
            merge_key += f", folder_id: '{_escape(folder_id)}'"

        cypher = f"""
        SELECT * FROM cypher('{graph}', $$
            MERGE (f:structural_folder {{{merge_key}}})
            {set_stmt}
            RETURN f.folder_type as folder_type
        $$) as (folder_type agtype)
        """
        try:
            await age_client.execute_cypher(cypher)
            return {
                "success": True,
                "indexed_to_graph": True,
                "node_type": "structural_folder",
                "folder_type": folder_type,
            }
        except Exception as e:
            logger.warning(f"Failed to upsert folder: {e}")
            return {"success": False, "error": str(e)}

    async def _upsert_document(
        self,
        tenant_id: str,
        document_id: str,
        title: Optional[str],
        file_path: Optional[str],
        folder_path: Optional[str],
        semantic_type: Optional[str],
        domain: Optional[str],
        document_type: Optional[str],
        connector_id: Optional[str],
        weaviate_document_id: Optional[str],
        folder_name: Optional[str],
        folder_type: Optional[str],
    ) -> Dict[str, Any]:
        graph = settings.age_graph_name

        doc_set = []
        if title:
            doc_set.append(f"d.title = '{_escape(title)}'")
        if file_path:
            doc_set.append(f"d.file_path = '{_escape(file_path)}'")
        if folder_path:
            doc_set.append(f"d.folder_path = '{_escape(folder_path)}'")
        if semantic_type:
            doc_set.append(f"d.semantic_type = '{_escape(semantic_type)}'")
        if domain:
            doc_set.append(f"d.domain = '{_escape(str(domain))}'")
        if document_type:
            doc_set.append(f"d.document_type = '{_escape(str(document_type))}'")
        if connector_id:
            doc_set.append(f"d.connector_id = '{_escape(str(connector_id))}'")
        if weaviate_document_id:
            doc_set.append(f"d.weaviate_id = '{_escape(str(weaviate_document_id))}'")

        doc_set_stmt = "SET " + ", ".join(doc_set) if doc_set else ""

        folder_merge = ""
        folder_set = ""
        folder_edge = ""
        if folder_path:
            folder_merge = (
                f"MERGE (f:structural_folder {{tenant_id: '{_escape(tenant_id)}', path: '{_escape(folder_path)}'}})"
            )
            folder_set_clauses = []
            if folder_name:
                folder_set_clauses.append(f"f.name = '{_escape(folder_name)}'")
            if folder_type:
                folder_set_clauses.append(f"f.folder_type = '{_escape(folder_type)}'")
            if folder_set_clauses:
                folder_set = "SET " + ", ".join(folder_set_clauses)
            folder_edge = "MERGE (f)-[:HAS_DOCUMENT]->(d)"

        cypher = f"""
        SELECT * FROM cypher('{graph}', $$
            MERGE (d:structural_document {{tenant_id: '{_escape(tenant_id)}', document_id: '{_escape(document_id)}'}})
            {doc_set_stmt}
            {folder_merge}
            {folder_set}
            {folder_edge}
            RETURN d.semantic_type as semantic_type
        $$) as (semantic_type agtype)
        """
        try:
            await age_client.execute_cypher(cypher)
            return {
                "success": True,
                "indexed_to_graph": True,
                "node_type": "structural_document",
                "semantic_type": semantic_type,
            }
        except Exception as e:
            logger.warning(f"Failed to upsert document: {e}")
            return {"success": False, "error": str(e)}


structural_indexer = StructuralIndexer()

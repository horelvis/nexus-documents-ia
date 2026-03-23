"""
Structural indexer for FalkorDB (Knowledge Graph).

Builds/updates :Folder and :Document nodes using connector metadata
and learned context. Detects person entities from folder hierarchy
and links them via :MENTIONED_IN edges.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.falkordb_client import falkordb_client

logger = logging.getLogger(__name__)

_CAMEL_RE = re.compile(r"(?<!^)([A-Z])")

_GENERIC_TYPES = {
    "cm:folder",
    "cm:content",
    "folder",
    "document",
}

# Infrastructure path segments (not business-relevant) -- per connector type
_INFRA_PATH_SEGMENTS = {
    # Alfresco
    "company home", "sites", "documentlibrary", "document library",
    "app:company_home", "st:sites", "cm:documentlibrary",
    # Google Drive
    "my drive",
    # OneDrive
    "documents",
}


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


def _extract_aspects(connector_metadata: Dict[str, Any]) -> Optional[List[str]]:
    """Extract aspect names from connector metadata."""
    aspects = connector_metadata.get("alfresco_aspects") or connector_metadata.get("aspectNames")
    if isinstance(aspects, list) and aspects:
        return aspects
    return None


def _extract_custom_properties(connector_metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract custom properties (exp:*, pmreg:*, etc.) from connector metadata."""
    props = connector_metadata.get("alfresco_properties") or connector_metadata.get("customProperties")
    if isinstance(props, dict) and props:
        return props
    return None


def _extract_business_path(path_parts: list) -> list:
    """
    Strip Alfresco infrastructure segments from a path, keeping only
    business-relevant segments.

    Example:
        ["Company Home", "Sites", "abc123", "documentLibrary", "CLIENTES", "DNI-001", "DOCS"]
        -> ["CLIENTES", "DNI-001", "DOCS"]
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


# Folder names that indicate the next segment is a person name
_PERSON_CONTAINER_KEYWORDS = {
    "empleados", "clientes", "personas", "staff", "employees",
    "contacts", "contactos", "socios", "usuarios", "users",
    "proveedores", "suppliers", "partners", "colaboradores",
    "autores", "authors", "firmantes", "signers",
}


def _detect_person_from_path(path_parts: list) -> Optional[str]:
    """
    Detect a person name from folder hierarchy.

    Looks for known "person container" folders (e.g., "Empleados") and
    extracts the next segment as a person name if it looks like one
    (has spaces, no digits, alphabetic).

    Example:
        ["Drive", "Empleados", "Javier Martinez", "Contratos"]
        -> "Javier Martinez"
    """
    business_parts = _extract_business_path(path_parts)

    for i, part in enumerate(business_parts[:-1]):
        if part.lower().strip() in _PERSON_CONTAINER_KEYWORDS:
            candidate = business_parts[i + 1]
            # Validate: person names have spaces, are alphabetic, no digits
            cleaned = candidate.replace(" ", "").replace("-", "")
            if (
                " " in candidate
                and cleaned.isalpha()
                and len(candidate) >= 3
            ):
                return candidate

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

        await falkordb_client.initialize()

        tenant_id = str(payload.get("tenant_id") or "").strip()
        document_id = str(payload.get("document_id") or "").strip()
        if not tenant_id or not document_id:
            return {"success": False, "error": "tenant_id and document_id are required"}

        connector_metadata = payload.get("connector_metadata") or {}
        learned_context = payload.get("learned_context") or {}
        file_path = payload.get("file_path") or ""
        connector_id = payload.get("connector_id")
        connector_type = payload.get("connector_type") or connector_metadata.get("connector_type")
        weaviate_document_id = payload.get("weaviate_document_id")

        is_folder = _is_folder(connector_metadata, learned_context)
        path_parts = _split_path(file_path)

        # Extract Alfresco metadata (aspects + custom properties)
        aspects = _extract_aspects(connector_metadata)
        custom_properties = _extract_custom_properties(connector_metadata)

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
                connector_type=connector_type,
                node_type=_extract_node_type(connector_metadata),
                aspects=aspects,
                custom_properties=custom_properties,
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

        # Detect person name from folder hierarchy (e.g., /Empleados/Javier Martinez/...)
        associated_person = _detect_person_from_path(path_parts)

        result = await self._upsert_document(
            tenant_id=tenant_id,
            document_id=document_id,
            title=doc_name or payload.get("title"),
            file_path=file_path or None,
            folder_path=folder_path,
            semantic_type=semantic_type,
            domain=domain,
            document_type=document_type,
            connector_id=connector_id,
            connector_type=connector_type,
            weaviate_document_id=weaviate_document_id,
            folder_name=folder_name,
            folder_type=folder_type,
            aspects=aspects,
            custom_properties=custom_properties,
            associated_person=associated_person,
        )

        # Extract claims from document text if provided
        document_text = payload.get("text") or payload.get("document_text") or ""
        if result.get("success") and document_text:
            try:
                from app.services.claim_extractor import claim_extractor
                claims = await claim_extractor.extract_claims(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text=document_text,
                    domain=str(domain or ""),
                    semantic_type=str(semantic_type or ""),
                )
                result["claims_extracted"] = len(claims)
            except Exception as e:
                logger.warning(f"Claim extraction failed for {document_id}: {e}")
                result["claims_extracted"] = 0

        return result

    async def _upsert_folder(
        self,
        tenant_id: str,
        folder_id: str,
        name: Optional[str],
        path: Optional[str],
        folder_type: Optional[str],
        connector_id: Optional[str],
        connector_type: Optional[str] = None,
        node_type: Optional[str] = None,
        aspects: Optional[List[str]] = None,
        custom_properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not path and not name:
            return {"success": False, "error": "Folder path or name required"}

        # Build SET clauses for properties
        props: Dict[str, Any] = {}
        if name:
            props["name"] = name
        if path:
            props["path"] = path
        if folder_type:
            props["folder_type"] = folder_type
        if connector_id:
            props["connector_id"] = str(connector_id)
        if connector_type:
            props["connector_type"] = connector_type
        if node_type:
            props["node_type"] = node_type
        if folder_id:
            props["folder_id"] = folder_id
        if aspects:
            props["aspects"] = ",".join(aspects)
        if custom_properties:
            props["custom_properties"] = json.dumps(custom_properties, ensure_ascii=False)

        # Build SET clause string from props
        set_parts = [f"f.{k} = ${k}" for k in props]
        set_stmt = "SET " + ", ".join(set_parts) if set_parts else ""

        # MERGE key: tenant_id + path (or folder_id)
        if path:
            merge_key = "tenant_id: $tenant_id, path: $path_key"
            props["tenant_id"] = tenant_id
            props["path_key"] = path
        else:
            merge_key = "tenant_id: $tenant_id, folder_id: $folder_id_key"
            props["tenant_id"] = tenant_id
            props["folder_id_key"] = folder_id

        cypher = f"""
            MERGE (f:Folder {{{merge_key}}})
            {set_stmt}
            RETURN f.folder_type AS folder_type
        """
        try:
            await falkordb_client.execute_cypher(cypher, props)
            return {
                "success": True,
                "indexed_to_graph": True,
                "node_type": "Folder",
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
        connector_type: Optional[str] = None,
        weaviate_document_id: Optional[str] = None,
        folder_name: Optional[str] = None,
        folder_type: Optional[str] = None,
        aspects: Optional[List[str]] = None,
        custom_properties: Optional[Dict[str, Any]] = None,
        associated_person: Optional[str] = None,
    ) -> Dict[str, Any]:
        # --- Query 1: MERGE Document node ---
        doc_props: Dict[str, Any] = {"tenant_id": tenant_id, "document_id": document_id}
        set_parts = []
        if title:
            doc_props["title"] = title
            set_parts.append("d.title = $title")
        if file_path:
            doc_props["file_path"] = file_path
            set_parts.append("d.file_path = $file_path")
        if folder_path:
            doc_props["folder_path"] = folder_path
            set_parts.append("d.folder_path = $folder_path")
        if semantic_type:
            doc_props["semantic_type"] = semantic_type
            set_parts.append("d.semantic_type = $semantic_type")
        if domain:
            doc_props["domain"] = str(domain)
            set_parts.append("d.domain = $domain")
        if document_type:
            doc_props["document_type"] = str(document_type)
            set_parts.append("d.document_type = $document_type")
        if connector_id:
            doc_props["connector_id"] = str(connector_id)
            set_parts.append("d.connector_id = $connector_id")
        if connector_type:
            doc_props["connector_type"] = connector_type
            set_parts.append("d.connector_type = $connector_type")
        if weaviate_document_id:
            doc_props["weaviate_id"] = str(weaviate_document_id)
            set_parts.append("d.weaviate_id = $weaviate_id")
        if aspects:
            doc_props["aspects"] = ",".join(aspects)
            set_parts.append("d.aspects = $aspects")
        if custom_properties:
            doc_props["custom_properties"] = json.dumps(custom_properties, ensure_ascii=False)
            set_parts.append("d.custom_properties = $custom_properties")
        if associated_person:
            doc_props["associated_person"] = associated_person
            set_parts.append("d.associated_person = $associated_person")

        set_parts.append("d.indexed_at = timestamp()")
        doc_set_stmt = "SET " + ", ".join(set_parts) if set_parts else ""

        doc_cypher = f"""
            MERGE (d:Document {{tenant_id: $tenant_id, document_id: $document_id}})
            {doc_set_stmt}
            RETURN d.semantic_type AS semantic_type
        """

        try:
            await falkordb_client.execute_cypher(doc_cypher, doc_props)
        except Exception as e:
            logger.warning(f"Failed to upsert document: {e}")
            return {"success": False, "error": str(e)}

        # --- Query 2: MERGE Folder + CONTAINED_IN edge (Document -> Folder) ---
        if folder_path:
            folder_props: Dict[str, Any] = {
                "tenant_id": tenant_id,
                "document_id": document_id,
                "folder_path": folder_path,
            }
            folder_set_parts = []
            if folder_name:
                folder_props["folder_name"] = folder_name
                folder_set_parts.append("f.name = $folder_name")
            if folder_type:
                folder_props["folder_type"] = folder_type
                folder_set_parts.append("f.folder_type = $folder_type")
            folder_set_stmt = "SET " + ", ".join(folder_set_parts) if folder_set_parts else ""

            folder_cypher = f"""
                MATCH (d:Document {{tenant_id: $tenant_id, document_id: $document_id}})
                MERGE (f:Folder {{tenant_id: $tenant_id, path: $folder_path}})
                {folder_set_stmt}
                MERGE (d)-[:CONTAINED_IN]->(f)
            """
            try:
                await falkordb_client.execute_cypher(folder_cypher, folder_props)
            except Exception as e:
                logger.warning(f"Failed to link document to folder: {e}")

        # --- Query 3: MERGE Person Entity + MENTIONED_IN edge ---
        if associated_person:
            person_props: Dict[str, Any] = {
                "tenant_id": tenant_id,
                "document_id": document_id,
                "person_name": associated_person,
                "normalized_name": associated_person.lower().strip(),
            }
            person_cypher = """
                MATCH (d:Document {tenant_id: $tenant_id, document_id: $document_id})
                MERGE (p:Entity {tenant_id: $tenant_id, entity_type: 'person', normalized_name: $normalized_name})
                SET p.name = $person_name, p.confidence = 0.8
                MERGE (p)-[:MENTIONED_IN]->(d)
            """
            try:
                await falkordb_client.execute_cypher(person_cypher, person_props)
                logger.info(f"Linked document {document_id} to Entity(person) '{associated_person}'")
            except Exception as e:
                logger.warning(f"Failed to link person entity: {e}")

        return {
            "success": True,
            "indexed_to_graph": True,
            "node_type": "Document",
            "semantic_type": semantic_type,
            "associated_person": associated_person,
        }


structural_indexer = StructuralIndexer()

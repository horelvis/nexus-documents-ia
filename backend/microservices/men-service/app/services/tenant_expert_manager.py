"""
Tenant Expert Manager - Expert Selection and Management.

Manages expert selection based on tenant ID, document type,
and query characteristics. Supports both tenant-specific and
generic experts.

Directory Structure:
trained_experts/
├── _generic_/              # Generic experts (fallback)
│   ├── legal/
│   │   └── adapter_model.bin
│   ├── contract/
│   └── ...
└── {tenant_id}/            # Tenant-specific experts
    ├── contract_expert/
    │   └── adapter_model.bin
    └── compliance_expert/
"""

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ExpertInfo:
    """Information about an available expert."""
    domain: str
    tenant_id: str
    path: str
    is_generic: bool
    document_types: List[str]


class TenantExpertManager:
    """
    Manages expert discovery and selection for tenants.

    Responsibilities:
    1. Discover available experts (generic and tenant-specific)
    2. Select appropriate expert based on query context
    3. Manage expert metadata and capabilities

    The manager maintains a registry of available experts
    and provides selection logic based on tenant and domain.
    """

    GENERIC_TENANT_ID = "_generic_"

    def __init__(self, experts_dir: str = "/app/trained_experts"):
        """
        Initialize the TenantExpertManager.

        Args:
            experts_dir: Root directory containing expert LoRA weights
        """
        self.experts_dir = experts_dir
        self._expert_registry: Dict[str, List[ExpertInfo]] = {}
        self._initialized = False

    def initialize(self) -> None:
        """
        Scan experts directory and build registry.

        Should be called once at service startup.
        """
        if self._initialized:
            return

        logger.info(f"Initializing TenantExpertManager from: {self.experts_dir}")

        if not os.path.exists(self.experts_dir):
            logger.warning(f"Experts directory not found: {self.experts_dir}")
            os.makedirs(self.experts_dir, exist_ok=True)
            os.makedirs(os.path.join(self.experts_dir, self.GENERIC_TENANT_ID), exist_ok=True)
            self._initialized = True
            return

        # Scan directory structure
        for tenant_dir in os.listdir(self.experts_dir):
            tenant_path = os.path.join(self.experts_dir, tenant_dir)
            if not os.path.isdir(tenant_path):
                continue

            tenant_id = tenant_dir
            is_generic = tenant_id == self.GENERIC_TENANT_ID

            # Scan expert directories within tenant
            for expert_dir in os.listdir(tenant_path):
                expert_path = os.path.join(tenant_path, expert_dir)
                if not os.path.isdir(expert_path):
                    continue

                # Check for adapter files (LoRA weights)
                has_adapter = any(
                    f.endswith(('.bin', '.safetensors', '.pt'))
                    for f in os.listdir(expert_path)
                ) or os.path.exists(os.path.join(expert_path, "adapter_config.json"))

                if not has_adapter:
                    logger.debug(f"Skipping {expert_path} - no adapter files found")
                    continue

                # Parse domain from directory name
                domain = self._parse_domain_from_name(expert_dir)

                # Read metadata if available
                doc_types = self._read_expert_metadata(expert_path)

                # Register expert
                expert_info = ExpertInfo(
                    domain=domain,
                    tenant_id=tenant_id if not is_generic else self.GENERIC_TENANT_ID,
                    path=expert_path,
                    is_generic=is_generic,
                    document_types=doc_types
                )

                if tenant_id not in self._expert_registry:
                    self._expert_registry[tenant_id] = []
                self._expert_registry[tenant_id].append(expert_info)

                logger.info(
                    f"Registered expert: {domain} for "
                    f"{'generic' if is_generic else tenant_id}"
                )

        self._initialized = True
        total = sum(len(experts) for experts in self._expert_registry.values())
        logger.info(f"TenantExpertManager initialized with {total} experts")

    def select_expert(
        self,
        tenant_id: str,
        query: str,
        document_type: Optional[str] = None,
        domain: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Select the best expert for a given query context.

        Selection priority:
        1. Tenant-specific expert matching domain/doc_type
        2. Tenant-specific expert for domain
        3. Generic expert for domain
        4. No expert (None)

        Args:
            tenant_id: Tenant identifier
            query: User's query (for keyword matching)
            document_type: Type of document (optional)
            domain: Domain classification (optional)

        Returns:
            Tuple of (expert_path, source) where source is
            "tenant:{domain}" or "generic:{domain}" or None
        """
        if not self._initialized:
            self.initialize()

        # Get tenant-specific experts
        tenant_experts = self._expert_registry.get(tenant_id, [])

        # Get generic experts
        generic_experts = self._expert_registry.get(self.GENERIC_TENANT_ID, [])

        # 1. Try tenant-specific expert with document type match
        if document_type:
            for expert in tenant_experts:
                if document_type.lower() in [dt.lower() for dt in expert.document_types]:
                    logger.debug(
                        f"Selected tenant expert by doc_type: {expert.domain} "
                        f"(doc_type={document_type})"
                    )
                    return expert.path, f"tenant:{expert.domain}"

        # 2. Try tenant-specific expert with domain match
        if domain:
            for expert in tenant_experts:
                if expert.domain == domain:
                    logger.debug(f"Selected tenant expert by domain: {expert.domain}")
                    return expert.path, f"tenant:{expert.domain}"

        # 3. Try generic expert with domain match
        if domain:
            for expert in generic_experts:
                if expert.domain == domain:
                    logger.debug(f"Selected generic expert by domain: {expert.domain}")
                    return expert.path, f"generic:{expert.domain}"

        # 4. Try keyword matching in query
        expert = self._keyword_match(query, tenant_experts + generic_experts)
        if expert:
            source = "tenant" if not expert.is_generic else "generic"
            logger.debug(f"Selected expert by keyword: {expert.domain}")
            return expert.path, f"{source}:{expert.domain}"

        logger.debug("No suitable expert found")
        return None, None

    def get_tenant_experts(self, tenant_id: str) -> List[ExpertInfo]:
        """Get all experts for a tenant."""
        if not self._initialized:
            self.initialize()
        return self._expert_registry.get(tenant_id, []).copy()

    def get_generic_experts(self) -> List[ExpertInfo]:
        """Get all generic experts."""
        if not self._initialized:
            self.initialize()
        return self._expert_registry.get(self.GENERIC_TENANT_ID, []).copy()

    def get_all_domains(self) -> List[str]:
        """Get all unique domains across all experts."""
        if not self._initialized:
            self.initialize()

        domains = set()
        for experts in self._expert_registry.values():
            for expert in experts:
                domains.add(expert.domain)
        return sorted(domains)

    def register_expert(
        self,
        tenant_id: str,
        domain: str,
        path: str,
        document_types: Optional[List[str]] = None
    ) -> ExpertInfo:
        """
        Manually register an expert.

        Useful for dynamic expert creation after training.
        """
        is_generic = tenant_id == self.GENERIC_TENANT_ID

        expert_info = ExpertInfo(
            domain=domain,
            tenant_id=tenant_id,
            path=path,
            is_generic=is_generic,
            document_types=document_types or []
        )

        if tenant_id not in self._expert_registry:
            self._expert_registry[tenant_id] = []
        self._expert_registry[tenant_id].append(expert_info)

        logger.info(f"Registered new expert: {domain} for {tenant_id}")
        return expert_info

    def _parse_domain_from_name(self, name: str) -> str:
        """Parse domain from directory name."""
        # Remove common suffixes
        name = name.lower()
        for suffix in ["_expert", "_lora", "_adapter", "-expert", "-lora", "-adapter"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break

        # Map common names to standard domains
        domain_map = {
            "legal": "legal",
            "juridico": "legal",
            "contract": "contract",
            "contrato": "contract",
            "contratos": "contract",
            "compliance": "compliance",
            "cumplimiento": "compliance",
            "finance": "finance",
            "finanzas": "finance",
            "financiero": "finance",
            "hr": "hr",
            "rrhh": "hr",
            "recursos_humanos": "hr",
            "technical": "technical",
            "tecnico": "technical",
            "técnico": "technical",
        }

        return domain_map.get(name, name)

    def _read_expert_metadata(self, expert_path: str) -> List[str]:
        """Read expert metadata from config file if available."""
        metadata_path = os.path.join(expert_path, "expert_metadata.json")
        if not os.path.exists(metadata_path):
            return []

        try:
            import json
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
            return metadata.get("document_types", [])
        except Exception as e:
            logger.warning(f"Failed to read expert metadata: {e}")
            return []

    def _keyword_match(
        self,
        query: str,
        experts: List[ExpertInfo]
    ) -> Optional[ExpertInfo]:
        """Simple keyword matching for expert selection."""
        query_lower = query.lower()

        # Domain keywords
        keywords = {
            "legal": ["ley", "legal", "normativa", "sentencia", "jurisprudencia"],
            "contract": ["contrato", "acuerdo", "cláusula", "renovación", "vencimiento"],
            "compliance": ["cumplimiento", "auditoría", "ISO", "certificación"],
            "finance": ["presupuesto", "factura", "pago", "financiero", "contable"],
            "hr": ["empleado", "nómina", "vacaciones", "personal", "contratación"],
            "technical": ["sistema", "API", "técnico", "manual", "configuración"],
        }

        for expert in experts:
            if expert.domain in keywords:
                for keyword in keywords[expert.domain]:
                    if keyword in query_lower:
                        return expert

        return None

"""
Tests for TenantExpertManager – expert discovery, selection, and registration.
"""

import json
import os

import pytest

from app.services.tenant_expert_manager import ExpertInfo, TenantExpertManager


class TestInitialization:
    """Test directory scanning and expert registry building."""

    def test_initialize_empty_dir(self, tmp_path):
        manager = TenantExpertManager(experts_dir=str(tmp_path / "empty"))
        manager.initialize()
        assert manager._initialized is True
        assert manager.get_all_domains() == []

    def test_initialize_with_generic_expert(self, experts_dir):
        manager = TenantExpertManager(experts_dir=experts_dir)
        manager.initialize()
        generic = manager.get_generic_experts()
        assert len(generic) == 1
        assert generic[0].domain == "legal"
        assert generic[0].is_generic is True

    def test_initialize_with_tenant_expert(self, experts_dir):
        manager = TenantExpertManager(experts_dir=experts_dir)
        manager.initialize()
        tenant = manager.get_tenant_experts("tenant-test")
        assert len(tenant) == 1
        assert tenant[0].domain == "contract"
        assert tenant[0].is_generic is False
        assert "contrato" in tenant[0].document_types

    def test_initialize_is_idempotent(self, experts_dir):
        manager = TenantExpertManager(experts_dir=experts_dir)
        manager.initialize()
        manager.initialize()  # second call should be no-op
        assert len(manager.get_generic_experts()) == 1

    def test_skips_dirs_without_adapter(self, tmp_path):
        base = tmp_path / "experts" / "_generic_" / "empty_domain"
        base.mkdir(parents=True)
        (base / "readme.txt").write_text("no adapter here")

        manager = TenantExpertManager(experts_dir=str(tmp_path / "experts"))
        manager.initialize()
        assert manager.get_all_domains() == []


class TestExpertSelection:
    """Test the priority-based expert selection logic."""

    @pytest.fixture(autouse=True)
    def _setup(self, experts_dir):
        self.manager = TenantExpertManager(experts_dir=experts_dir)
        self.manager.initialize()

    def test_select_tenant_expert_by_domain(self):
        path, source = self.manager.select_expert(
            tenant_id="tenant-test",
            query="Revisar el contrato",
            domain="contract",
        )
        assert path is not None
        assert source == "tenant:contract"

    def test_select_tenant_expert_by_document_type(self):
        path, source = self.manager.select_expert(
            tenant_id="tenant-test",
            query="Verificar acuerdo",
            document_type="contrato",
        )
        assert path is not None
        assert source == "tenant:contract"

    def test_fallback_to_generic_expert(self):
        path, source = self.manager.select_expert(
            tenant_id="unknown-tenant",
            query="Consulta legal",
            domain="legal",
        )
        assert path is not None
        assert source == "generic:legal"

    def test_no_expert_for_unknown_domain(self):
        path, source = self.manager.select_expert(
            tenant_id="tenant-test",
            query="Hola mundo",
            domain="nonexistent",
        )
        assert path is None
        assert source is None

    def test_keyword_match_fallback(self):
        path, source = self.manager.select_expert(
            tenant_id="unknown-tenant",
            query="Necesito revisar la ley de protección de datos",
        )
        assert path is not None
        assert "legal" in source


class TestDomainParsing:
    """Test directory name → domain resolution."""

    def test_standard_names(self):
        manager = TenantExpertManager()
        assert manager._parse_domain_from_name("legal_expert") == "legal"
        assert manager._parse_domain_from_name("contract-lora") == "contract"
        assert manager._parse_domain_from_name("finanzas_adapter") == "finance"
        assert manager._parse_domain_from_name("RRHH") == "hr"
        assert manager._parse_domain_from_name("cumplimiento") == "compliance"
        assert manager._parse_domain_from_name("técnico_expert") == "technical"

    def test_unknown_name_returns_itself(self):
        manager = TenantExpertManager()
        assert manager._parse_domain_from_name("custom_domain") == "custom_domain"


class TestRegistration:
    """Test manual expert registration."""

    def test_register_new_expert(self, experts_dir):
        manager = TenantExpertManager(experts_dir=experts_dir)
        manager.initialize()

        expert = manager.register_expert(
            tenant_id="tenant-new",
            domain="finance",
            path="/some/path",
            document_types=["factura", "presupuesto"],
        )

        assert expert.domain == "finance"
        assert expert.tenant_id == "tenant-new"
        assert expert.is_generic is False
        assert "factura" in expert.document_types

        # Should be discoverable
        experts = manager.get_tenant_experts("tenant-new")
        assert len(experts) == 1

    def test_register_generic_expert(self, experts_dir):
        manager = TenantExpertManager(experts_dir=experts_dir)
        manager.initialize()

        expert = manager.register_expert(
            tenant_id="_generic_",
            domain="hr",
            path="/generic/hr",
        )
        assert expert.is_generic is True

    def test_get_all_domains(self, experts_dir):
        manager = TenantExpertManager(experts_dir=experts_dir)
        manager.initialize()
        domains = manager.get_all_domains()
        assert "legal" in domains
        assert "contract" in domains


class TestMetadataReading:
    """Test expert_metadata.json parsing."""

    def test_reads_document_types(self, tmp_path):
        expert = tmp_path / "experts" / "_generic_" / "legal"
        expert.mkdir(parents=True)
        (expert / "adapter_config.json").write_text("{}")
        (expert / "expert_metadata.json").write_text(
            json.dumps({"document_types": ["sentencia", "ley"]})
        )

        manager = TenantExpertManager(experts_dir=str(tmp_path / "experts"))
        manager.initialize()
        generic = manager.get_generic_experts()
        assert "sentencia" in generic[0].document_types

    def test_handles_missing_metadata(self, experts_dir):
        manager = TenantExpertManager(experts_dir=experts_dir)
        manager.initialize()
        generic = manager.get_generic_experts()
        # generic/legal has no metadata file
        assert generic[0].document_types == []

    def test_handles_corrupt_metadata(self, tmp_path):
        expert = tmp_path / "experts" / "_generic_" / "legal"
        expert.mkdir(parents=True)
        (expert / "adapter_config.json").write_text("{}")
        (expert / "expert_metadata.json").write_text("not json {{{")

        manager = TenantExpertManager(experts_dir=str(tmp_path / "experts"))
        manager.initialize()
        generic = manager.get_generic_experts()
        assert generic[0].document_types == []

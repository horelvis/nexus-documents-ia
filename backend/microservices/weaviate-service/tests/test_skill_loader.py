"""
Tests for Agent Skills Framework

Tests skill loading, matching, and integration with Emma v2.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Test the skill loader
from app.agents.skill_loader import (
    Skill,
    SkillMatch,
    SkillLoader,
    skill_loader,
    get_skill,
    match_skills,
    get_skill_instructions,
    reload_skills,
)


class TestSkillDataClass:
    """Tests for Skill dataclass."""

    def test_skill_matches_query_exact(self):
        """Test that skill matches exact trigger."""
        skill = Skill(
            name="test-skill",
            description="Test skill",
            version="1.0.0",
            domain="test",
            triggers=["analiza.*contrato"],
            priority=10,
            instructions="Test instructions",
            path=Path("/test/SKILL.md"),
        )

        matches, confidence = skill.matches_query("analiza este contrato")
        assert matches is True
        assert confidence > 0.5

    def test_skill_matches_query_case_insensitive(self):
        """Test case-insensitive matching."""
        skill = Skill(
            name="test-skill",
            description="Test skill",
            version="1.0.0",
            domain="test",
            triggers=["RGPD"],
            priority=8,
            instructions="Test instructions",
            path=Path("/test/SKILL.md"),
        )

        matches, confidence = skill.matches_query("cumplimiento rgpd")
        assert matches is True

    def test_skill_no_match(self):
        """Test skill doesn't match unrelated query."""
        skill = Skill(
            name="test-skill",
            description="Test skill",
            version="1.0.0",
            domain="test",
            triggers=["contrato laboral"],
            priority=10,
            instructions="Test instructions",
            path=Path("/test/SKILL.md"),
        )

        matches, confidence = skill.matches_query("factura de enero")
        assert matches is False
        assert confidence == 0.0

    def test_skill_get_summary(self):
        """Test getting skill summary."""
        skill = Skill(
            name="test-skill",
            description="Test skill",
            version="1.0.0",
            domain="test",
            triggers=["test"],
            priority=5,
            instructions="First paragraph.\n\nSecond paragraph.",
            path=Path("/test/SKILL.md"),
        )

        summary = skill.get_summary()
        assert summary == "First paragraph."

    def test_skill_to_dict(self):
        """Test skill serialization."""
        skill = Skill(
            name="test-skill",
            description="Test skill",
            version="1.0.0",
            domain="test",
            triggers=["test"],
            priority=5,
            instructions="Instructions",
            path=Path("/test/SKILL.md"),
        )

        data = skill.to_dict()
        assert data["name"] == "test-skill"
        assert data["version"] == "1.0.0"
        assert data["domain"] == "test"
        assert data["instructions_length"] == len("Instructions")


class TestSkillLoader:
    """Tests for SkillLoader class."""

    def test_loader_init_default_path(self):
        """Test loader initializes with default path."""
        loader = SkillLoader()
        assert loader.skills_path.name == "skills"

    def test_loader_init_custom_path(self):
        """Test loader with custom path."""
        custom_path = Path("/custom/skills")
        loader = SkillLoader(skills_path=custom_path)
        assert loader.skills_path == custom_path

    def test_loader_reload_skills(self, tmp_path):
        """Test loading skills from directory."""
        # Create a test skill directory
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()

        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("""---
name: test-skill
description: Test skill for unit tests
version: 1.0.0
domain: test
triggers:
  - "test.*query"
  - "another pattern"
priority: 8
---

# Test Skill Instructions

This is the instruction content.

## Checklist
- [ ] Item 1
- [ ] Item 2
""")

        loader = SkillLoader(skills_path=tmp_path)
        count = loader.reload_skills()

        assert count == 1
        assert "test-skill" in loader.list_skills()

        skill = loader.get_skill("test-skill")
        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.domain == "test"
        assert skill.priority == 8
        assert len(skill.triggers) == 2
        assert "Test Skill Instructions" in skill.instructions

    def test_loader_get_skill_by_domain(self, tmp_path):
        """Test filtering skills by domain."""
        # Create skills for different domains
        for domain in ["labor", "fiscal", "labor"]:
            skill_dir = tmp_path / f"{domain}-skill-{hash(domain) % 1000}"
            skill_dir.mkdir()
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(f"""---
name: {skill_dir.name}
description: {domain} skill
version: 1.0.0
domain: {domain}
triggers:
  - "{domain}"
priority: 5
---

# {domain} Instructions
""")

        loader = SkillLoader(skills_path=tmp_path)
        loader.reload_skills()

        labor_skills = loader.get_skill_by_domain("labor")
        assert len(labor_skills) == 2

        fiscal_skills = loader.get_skill_by_domain("fiscal")
        assert len(fiscal_skills) == 1

    def test_loader_match_skills(self, tmp_path):
        """Test skill matching."""
        # Create test skills
        skill_configs = [
            ("labor-analysis", "labor", ["contrato laboral", "despido"], 10),
            ("fiscal-analysis", "fiscal", ["factura", "IVA"], 10),
            ("general-review", "general", ["revisar", "analizar"], 5),
        ]

        for name, domain, triggers, priority in skill_configs:
            skill_dir = tmp_path / name
            skill_dir.mkdir()
            skill_file = skill_dir / "SKILL.md"
            triggers_yaml = "\n  - ".join([f'"{t}"' for t in triggers])
            skill_file.write_text(f"""---
name: {name}
description: {name} skill
version: 1.0.0
domain: {domain}
triggers:
  - {triggers_yaml}
priority: {priority}
---

# {name} Instructions
""")

        loader = SkillLoader(skills_path=tmp_path)
        loader.reload_skills()

        # Test labor query
        matches = loader.match_skills("analiza este contrato laboral")
        assert len(matches) >= 1
        assert any(m.skill.name == "labor-analysis" for m in matches)

        # Test fiscal query
        matches = loader.match_skills("verifica esta factura")
        assert len(matches) >= 1
        assert any(m.skill.name == "fiscal-analysis" for m in matches)

    def test_loader_get_skill_instructions(self, tmp_path):
        """Test getting combined skill instructions."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("""---
name: test-skill
description: Test skill
version: 1.0.0
domain: test
triggers:
  - "test query"
priority: 10
---

# Test Instructions

Content for testing.
""")

        loader = SkillLoader(skills_path=tmp_path)
        loader.reload_skills()

        instructions = loader.get_skill_instructions("test query")
        assert "test-skill" in instructions
        assert "Test Instructions" in instructions

    def test_loader_empty_directory(self, tmp_path):
        """Test with empty skills directory."""
        loader = SkillLoader(skills_path=tmp_path)
        count = loader.reload_skills()

        assert count == 0
        assert loader.list_skills() == []

    def test_loader_nonexistent_directory(self, tmp_path):
        """Test with non-existent directory."""
        loader = SkillLoader(skills_path=tmp_path / "nonexistent")
        count = loader.reload_skills()

        assert count == 0

    def test_loader_invalid_yaml(self, tmp_path):
        """Test handling of invalid YAML."""
        skill_dir = tmp_path / "invalid-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("""---
name: invalid
description: [unclosed list
---

Content
""")

        loader = SkillLoader(skills_path=tmp_path)
        count = loader.reload_skills()

        assert count == 0  # Invalid skill should not be loaded


class TestGlobalSkillLoader:
    """Tests for global skill_loader instance."""

    def test_global_instance_exists(self):
        """Test global skill_loader exists."""
        assert skill_loader is not None
        assert isinstance(skill_loader, SkillLoader)

    def test_convenience_functions(self):
        """Test convenience functions work."""
        # These may return None/empty if no skills are loaded, but shouldn't crash
        result = get_skill("nonexistent")
        assert result is None

        matches = match_skills("test query")
        assert isinstance(matches, list)

        instructions = get_skill_instructions("test query")
        assert isinstance(instructions, str)


class TestSkillLoaderIntegration:
    """Integration tests for skill loader with actual skills."""

    @pytest.fixture
    def skills_path(self):
        """Path to actual skills directory."""
        return Path(__file__).parent.parent / "skills"

    def test_load_actual_skills(self, skills_path):
        """Test loading actual skills from filesystem."""
        if not skills_path.exists():
            pytest.skip("Skills directory not found")

        loader = SkillLoader(skills_path=skills_path)
        count = loader.reload_skills()

        # We should have at least the 5 skills we created
        assert count >= 5

    def test_labor_skill_exists(self, skills_path):
        """Test labor-analysis skill exists."""
        if not skills_path.exists():
            pytest.skip("Skills directory not found")

        loader = SkillLoader(skills_path=skills_path)
        loader.reload_skills()

        skill = loader.get_skill("labor-analysis")
        assert skill is not None
        assert skill.domain == "labor"
        assert "ET" in skill.instructions or "Estatuto" in skill.instructions

    def test_fiscal_skill_exists(self, skills_path):
        """Test fiscal-analysis skill exists."""
        if not skills_path.exists():
            pytest.skip("Skills directory not found")

        loader = SkillLoader(skills_path=skills_path)
        loader.reload_skills()

        skill = loader.get_skill("fiscal-analysis")
        assert skill is not None
        assert skill.domain == "fiscal"
        assert "IVA" in skill.instructions or "factura" in skill.instructions.lower()

    def test_privacy_skill_exists(self, skills_path):
        """Test privacy-compliance skill exists."""
        if not skills_path.exists():
            pytest.skip("Skills directory not found")

        loader = SkillLoader(skills_path=skills_path)
        loader.reload_skills()

        skill = loader.get_skill("privacy-compliance")
        assert skill is not None
        assert skill.domain == "privacy"
        assert "RGPD" in skill.instructions or "LOPDGDD" in skill.instructions

    def test_match_labor_query(self, skills_path):
        """Test matching labor-related query."""
        if not skills_path.exists():
            pytest.skip("Skills directory not found")

        loader = SkillLoader(skills_path=skills_path)
        loader.reload_skills()

        matches = loader.match_skills("analiza este contrato laboral")
        assert len(matches) > 0
        assert any(m.skill.name == "labor-analysis" for m in matches)

    def test_match_fiscal_query(self, skills_path):
        """Test matching fiscal-related query."""
        if not skills_path.exists():
            pytest.skip("Skills directory not found")

        loader = SkillLoader(skills_path=skills_path)
        loader.reload_skills()

        matches = loader.match_skills("verifica el IVA de esta factura")
        assert len(matches) > 0
        assert any(m.skill.name == "fiscal-analysis" for m in matches)

    def test_match_privacy_query(self, skills_path):
        """Test matching privacy-related query."""
        if not skills_path.exists():
            pytest.skip("Skills directory not found")

        loader = SkillLoader(skills_path=skills_path)
        loader.reload_skills()

        matches = loader.match_skills("cumplimiento RGPD de esta política de privacidad")
        assert len(matches) > 0
        assert any(m.skill.name == "privacy-compliance" for m in matches)


class TestEmmaV2SkillIntegration:
    """Tests for Emma v2 integration with skills."""

    @pytest.mark.asyncio
    async def test_emma_v2_config_has_skills(self):
        """Test EmmaV2Config has skill options."""
        from app.agents.emma_v2 import EmmaV2Config

        config = EmmaV2Config()
        assert hasattr(config, 'enable_skills')
        assert config.enable_skills is True
        assert hasattr(config, 'max_skill_tokens')
        assert config.max_skill_tokens == 2000

    @pytest.mark.asyncio
    async def test_emma_v2_result_has_skills_used(self):
        """Test EmmaV2Result includes skills_used."""
        from app.agents.emma_v2 import EmmaV2Result, DomainType

        result = EmmaV2Result(
            success=True,
            answer="Test answer",
            domain=DomainType.LABOR,
            skills_used=["labor-analysis", "contract-review"],
        )

        assert result.skills_used == ["labor-analysis", "contract-review"]

        data = result.to_dict()
        assert "skills_used" in data
        assert data["skills_used"] == ["labor-analysis", "contract-review"]

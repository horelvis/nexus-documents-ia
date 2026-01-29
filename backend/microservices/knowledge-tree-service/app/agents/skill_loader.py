"""
Agent Skills Framework

Based on Anthropic's Agent Skills pattern for discoverable, modular knowledge.
Skills are stored in filesystem as markdown files with YAML frontmatter.

Benefits over hardcoded prompts:
- Progressive disclosure: Only load skills when needed
- Versionable: Skills can be tracked in git
- Extensible: Add new skills without code changes
- Maintainable: Domain experts can update skills directly

Directory Structure:
    skills/
    ├── labor-analysis/
    │   └── SKILL.md      # YAML frontmatter + instructions
    ├── fiscal-analysis/
    │   └── SKILL.md
    ├── privacy-compliance/
    │   └── SKILL.md
    └── contract-review/
        └── SKILL.md

SKILL.md Format:
    ---
    name: labor-analysis
    description: Análisis de cumplimiento laboral
    version: 1.0.0
    triggers:
      - "analiza.*contrato laboral"
      - "cumplimiento.*laboral"
    domain: labor
    priority: 10
    ---

    # Instructions for the agent...

Usage:
    from app.agents.skill_loader import skill_loader

    # Discover matching skills for a query
    skills = skill_loader.match_skills("Analiza este contrato laboral")

    # Load a specific skill
    skill = skill_loader.get_skill("labor-analysis")

    # Get skill instructions for prompt
    instructions = skill.get_instructions()

References:
    - https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

# Default skills directory (relative to weaviate-service)
DEFAULT_SKILLS_PATH = Path(__file__).parent.parent.parent / "skills"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Skill:
    """
    Represents a loaded agent skill.

    A skill contains:
    - Metadata (name, description, version, triggers)
    - Instructions (markdown content after frontmatter)
    - Checklists, procedures, legal references
    """
    name: str
    description: str
    version: str
    domain: str
    triggers: List[str]
    priority: int
    instructions: str
    path: Path
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Compiled regex patterns (lazy loaded)
    _compiled_patterns: List[re.Pattern] = field(default_factory=list, repr=False)

    def matches_query(self, query: str) -> Tuple[bool, float]:
        """
        Check if this skill matches a query.

        Returns:
            Tuple of (matches: bool, confidence: float)
        """
        if not self._compiled_patterns:
            self._compile_patterns()

        query_lower = query.lower()

        for pattern in self._compiled_patterns:
            if pattern.search(query_lower):
                # Higher priority = higher confidence
                confidence = 0.5 + (self.priority / 20)  # Max ~1.0 for priority 10
                return True, min(confidence, 1.0)

        return False, 0.0

    def _compile_patterns(self):
        """Compile trigger patterns to regex."""
        self._compiled_patterns = []
        for trigger in self.triggers:
            try:
                # Treat triggers as regex patterns
                pattern = re.compile(trigger, re.IGNORECASE)
                self._compiled_patterns.append(pattern)
            except re.error:
                # If invalid regex, treat as literal string
                escaped = re.escape(trigger)
                self._compiled_patterns.append(re.compile(escaped, re.IGNORECASE))

    def get_instructions(self) -> str:
        """Get the full instructions for this skill."""
        return self.instructions

    def get_summary(self) -> str:
        """Get a short summary of the skill for context."""
        # Return first paragraph of instructions
        paragraphs = self.instructions.split('\n\n')
        if paragraphs:
            return paragraphs[0].strip()
        return self.description

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "domain": self.domain,
            "triggers": self.triggers,
            "priority": self.priority,
            "instructions_length": len(self.instructions),
            "path": str(self.path),
        }


@dataclass
class SkillMatch:
    """Result of skill matching."""
    skill: Skill
    confidence: float
    matched_trigger: Optional[str] = None


# =============================================================================
# Skill Loader
# =============================================================================

class SkillLoader:
    """
    Discovers and loads agent skills from filesystem.

    Features:
    - Lazy loading: Skills loaded on first access
    - Caching: Skill content cached in memory
    - Hot reload: Can reload skills without restart
    - Pattern matching: Match queries to skills via triggers
    """

    def __init__(self, skills_path: Optional[Path] = None):
        self.skills_path = skills_path or DEFAULT_SKILLS_PATH
        self._skills: Dict[str, Skill] = {}
        self._loaded = False

    def _ensure_loaded(self):
        """Ensure skills are loaded."""
        if not self._loaded:
            self.reload_skills()

    def reload_skills(self) -> int:
        """
        Reload all skills from filesystem.

        Returns:
            Number of skills loaded
        """
        self._skills = {}

        if not self.skills_path.exists():
            logger.warning(f"Skills directory not found: {self.skills_path}")
            self._loaded = True
            return 0

        # Discover all SKILL.md files
        skill_files = list(self.skills_path.glob("*/SKILL.md"))

        for skill_file in skill_files:
            try:
                skill = self._load_skill_file(skill_file)
                if skill:
                    self._skills[skill.name] = skill
                    logger.debug(f"Loaded skill: {skill.name} ({len(skill.triggers)} triggers)")
            except Exception as e:
                logger.error(f"Failed to load skill from {skill_file}: {e}")

        self._loaded = True
        logger.info(f"Loaded {len(self._skills)} skills from {self.skills_path}")

        return len(self._skills)

    def _load_skill_file(self, path: Path) -> Optional[Skill]:
        """
        Load a skill from a SKILL.md file.

        File format:
            ---
            name: skill-name
            description: Description
            version: 1.0.0
            triggers:
              - "pattern1"
              - "pattern2"
            domain: labor
            priority: 10
            ---

            # Markdown instructions...
        """
        content = path.read_text(encoding='utf-8')

        # Parse YAML frontmatter
        if not content.startswith('---'):
            logger.warning(f"Skill file missing frontmatter: {path}")
            return None

        # Find end of frontmatter
        end_marker = content.find('---', 3)
        if end_marker == -1:
            logger.warning(f"Skill file has unclosed frontmatter: {path}")
            return None

        frontmatter_str = content[3:end_marker].strip()
        instructions = content[end_marker + 3:].strip()

        try:
            frontmatter = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in skill {path}: {e}")
            return None

        if not isinstance(frontmatter, dict):
            logger.warning(f"Skill frontmatter is not a dict: {path}")
            return None

        # Extract required fields
        name = frontmatter.get('name', path.parent.name)
        description = frontmatter.get('description', '')
        version = frontmatter.get('version', '1.0.0')
        domain = frontmatter.get('domain', 'general')
        triggers = frontmatter.get('triggers', [])
        priority = frontmatter.get('priority', 5)

        # Ensure triggers is a list
        if isinstance(triggers, str):
            triggers = [triggers]

        return Skill(
            name=name,
            description=description,
            version=version,
            domain=domain,
            triggers=triggers,
            priority=priority,
            instructions=instructions,
            path=path,
            metadata=frontmatter,
        )

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        self._ensure_loaded()
        return self._skills.get(name)

    def get_skill_by_domain(self, domain: str) -> List[Skill]:
        """Get all skills for a domain."""
        self._ensure_loaded()
        return [s for s in self._skills.values() if s.domain == domain]

    def list_skills(self) -> List[str]:
        """List all available skill names."""
        self._ensure_loaded()
        return list(self._skills.keys())

    def match_skills(
        self,
        query: str,
        domain: Optional[str] = None,
        max_skills: int = 3
    ) -> List[SkillMatch]:
        """
        Find skills that match a query.

        Args:
            query: User query to match against
            domain: Optional domain filter
            max_skills: Maximum skills to return

        Returns:
            List of SkillMatch sorted by confidence
        """
        self._ensure_loaded()

        matches = []

        for skill in self._skills.values():
            # Filter by domain if specified
            if domain and skill.domain != domain:
                continue

            matched, confidence = skill.matches_query(query)
            if matched:
                matches.append(SkillMatch(
                    skill=skill,
                    confidence=confidence,
                ))

        # Sort by confidence (descending) then priority (descending)
        matches.sort(key=lambda m: (m.confidence, m.skill.priority), reverse=True)

        return matches[:max_skills]

    def get_skill_instructions(
        self,
        query: str,
        domain: Optional[str] = None,
        max_tokens: int = 2000
    ) -> str:
        """
        Get combined instructions from matching skills.

        This is the main method for integrating skills into prompts.
        It returns relevant skill instructions that fit within token budget.

        Args:
            query: User query
            domain: Optional domain filter
            max_tokens: Maximum tokens (~4 chars per token)

        Returns:
            Combined skill instructions string
        """
        matches = self.match_skills(query, domain)

        if not matches:
            return ""

        max_chars = max_tokens * 4  # Rough estimate
        result_parts = []
        total_chars = 0

        for match in matches:
            instructions = match.skill.get_instructions()

            # Check if we have room
            if total_chars + len(instructions) > max_chars:
                # Try to include at least the summary
                summary = match.skill.get_summary()
                if total_chars + len(summary) <= max_chars:
                    result_parts.append(f"## {match.skill.name}\n{summary}")
                    total_chars += len(summary) + len(match.skill.name) + 10
                break

            result_parts.append(f"## {match.skill.name}\n{instructions}")
            total_chars += len(instructions) + len(match.skill.name) + 10

        return "\n\n".join(result_parts)

    def get_all_domains(self) -> List[str]:
        """Get list of all domains with skills."""
        self._ensure_loaded()
        return list(set(s.domain for s in self._skills.values()))

    def get_skill_stats(self) -> Dict[str, Any]:
        """Get statistics about loaded skills."""
        self._ensure_loaded()

        domains = {}
        for skill in self._skills.values():
            if skill.domain not in domains:
                domains[skill.domain] = 0
            domains[skill.domain] += 1

        return {
            "total_skills": len(self._skills),
            "skills_by_domain": domains,
            "skills_path": str(self.skills_path),
            "loaded": self._loaded,
        }


# =============================================================================
# Global Instance
# =============================================================================

skill_loader = SkillLoader()


# =============================================================================
# Convenience Functions
# =============================================================================

def get_skill(name: str) -> Optional[Skill]:
    """Get a skill by name."""
    return skill_loader.get_skill(name)


def match_skills(query: str, domain: Optional[str] = None) -> List[SkillMatch]:
    """Find skills matching a query."""
    return skill_loader.match_skills(query, domain)


def get_skill_instructions(
    query: str,
    domain: Optional[str] = None,
    max_tokens: int = 2000
) -> str:
    """Get instructions from matching skills."""
    return skill_loader.get_skill_instructions(query, domain, max_tokens)


def reload_skills() -> int:
    """Reload skills from filesystem."""
    return skill_loader.reload_skills()

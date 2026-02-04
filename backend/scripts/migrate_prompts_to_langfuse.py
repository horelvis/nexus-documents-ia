#!/usr/bin/env python3
"""
Migrate Emma prompts from YAML to Langfuse.

This script imports all prompts from emma_prompts.yaml into Langfuse Prompt Management,
enabling versioning, web UI editing, A/B testing, and rollback capabilities.

Usage:
    # Dry run (preview what will be created)
    python scripts/migrate_prompts_to_langfuse.py --dry-run

    # Full migration
    python scripts/migrate_prompts_to_langfuse.py

    # Migrate specific sections only
    python scripts/migrate_prompts_to_langfuse.py --sections agents,sectors

    # Force update existing prompts
    python scripts/migrate_prompts_to_langfuse.py --force
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_yaml_prompts(yaml_path: Path) -> Dict[str, Any]:
    """Load emma_prompts.yaml file."""
    if not yaml_path.exists():
        print(f"❌ YAML file not found: {yaml_path}")
        sys.exit(1)

    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def extract_prompts_to_migrate(yaml_data: Dict[str, Any], sections: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Extract prompts from YAML in Langfuse-compatible format.

    Returns list of dicts with:
    - name: Langfuse prompt name (e.g., "emma_agent_labor")
    - prompt: The prompt content
    - config: Optional configuration
    - labels: Labels for categorization
    """
    prompts = []

    # Mapping of YAML sections to Langfuse prompts
    all_sections = ["context_root", "actions", "system_prompts", "sectors", "chat", "agents", "social"]
    if sections:
        all_sections = [s for s in all_sections if s in sections]

    # 1. Context Root
    if "context_root" in all_sections and "context_root" in yaml_data:
        prompts.append({
            "name": "emma_context_root",
            "prompt": yaml_data["context_root"],
            "labels": ["core", "system"],
            "description": "Global context prepended to all Emma prompts",
        })

    # 2. Action Instructions
    if "actions" in all_sections and "action_instructions" in yaml_data:
        for action_name, content in yaml_data["action_instructions"].items():
            prompts.append({
                "name": f"emma_action_{action_name}",
                "prompt": content,
                "labels": ["action", action_name],
                "description": f"Action instruction for '{action_name}' intent",
            })

    # 3. System Prompts (synthesis, planning)
    if "system_prompts" in all_sections and "system_prompts" in yaml_data:
        for prompt_name, content in yaml_data["system_prompts"].items():
            prompts.append({
                "name": f"emma_{prompt_name}",
                "prompt": content,
                "labels": ["system", prompt_name],
                "description": f"System prompt for '{prompt_name}'",
            })

    # 4. Sector Prompts
    if "sectors" in all_sections and "sectors" in yaml_data:
        for sector_name, sector_data in yaml_data["sectors"].items():
            if isinstance(sector_data, dict):
                # System prompt
                if "system_prompt" in sector_data:
                    prompts.append({
                        "name": f"emma_sector_{sector_name}",
                        "prompt": sector_data["system_prompt"],
                        "labels": ["sector", sector_name],
                        "description": f"Sector system prompt for '{sector_name}'",
                    })
                # Generation prompt
                if "generation_prompt" in sector_data:
                    prompts.append({
                        "name": f"emma_sector_{sector_name}_generation",
                        "prompt": sector_data["generation_prompt"],
                        "labels": ["sector", sector_name, "generation"],
                        "description": f"Sector generation prompt for '{sector_name}'",
                    })

    # 5. Chat Prompts
    if "chat" in all_sections and "chat_prompts" in yaml_data:
        for chat_type, content in yaml_data["chat_prompts"].items():
            prompts.append({
                "name": f"emma_chat_{chat_type}",
                "prompt": content,
                "labels": ["chat", chat_type],
                "description": f"Chat prompt for '{chat_type}' mode",
            })

    # 6. Agent Prompts (autogen_agents + planning_agents)
    if "agents" in all_sections:
        for section in ("autogen_agents", "planning_agents"):
            if section in yaml_data:
                for agent_name, agent_data in yaml_data[section].items():
                    if not isinstance(agent_data, dict):
                        continue

                    # Convert AgentName to snake_case
                    snake_name = _to_snake_case(agent_name).replace("_agent", "")

                    # System message
                    if "system_message" in agent_data:
                        prompts.append({
                            "name": f"emma_agent_{snake_name}",
                            "prompt": agent_data["system_message"],
                            "labels": ["agent", snake_name],
                            "description": f"System message for {agent_name}",
                        })

                    # System template (Jinja2)
                    if "system_template" in agent_data:
                        prompts.append({
                            "name": f"emma_agent_{snake_name}_template",
                            "prompt": agent_data["system_template"],
                            "labels": ["agent", snake_name, "template"],
                            "description": f"Jinja2 template for {agent_name}",
                            "config": {"is_template": True},
                        })

    # 7. Social Channel Prompts
    if "social" in all_sections and "social_channels" in yaml_data:
        for key, content in yaml_data["social_channels"].items():
            if isinstance(content, str):
                prompts.append({
                    "name": f"emma_social_{key}",
                    "prompt": content,
                    "labels": ["social", key],
                    "description": f"Social channel prompt for '{key}'",
                })

    return prompts


def _to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def migrate_to_langfuse(
    prompts: List[Dict[str, Any]],
    dry_run: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Migrate prompts to Langfuse.

    Args:
        prompts: List of prompt dicts to migrate
        dry_run: If True, only print what would be done
        force: If True, update existing prompts

    Returns:
        Summary of migration results
    """
    results = {
        "created": [],
        "updated": [],
        "skipped": [],
        "errors": [],
    }

    if dry_run:
        print("\n🔍 DRY RUN - No changes will be made\n")
        print("=" * 60)
        for prompt in prompts:
            print(f"📝 {prompt['name']}")
            print(f"   Labels: {', '.join(prompt.get('labels', []))}")
            print(f"   Description: {prompt.get('description', 'N/A')}")
            print(f"   Content length: {len(prompt['prompt'])} chars")
            print()
        print("=" * 60)
        print(f"\nTotal: {len(prompts)} prompts would be migrated")
        return results

    # Initialize Langfuse client
    try:
        from langfuse import Langfuse

        langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
        )
    except ImportError:
        print("❌ Langfuse SDK not installed. Run: pip install langfuse")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to initialize Langfuse: {e}")
        sys.exit(1)

    print(f"\n🚀 Migrating {len(prompts)} prompts to Langfuse...\n")

    for prompt in prompts:
        name = prompt["name"]
        content = prompt["prompt"]
        labels = prompt.get("labels", [])

        try:
            # Check if prompt exists
            existing = None
            try:
                existing = langfuse.get_prompt(name)
            except Exception:
                pass

            if existing and not force:
                results["skipped"].append(name)
                print(f"⏭️  Skipped (exists): {name}")
                continue

            # Create or update prompt (always include 'production' label)
            if "production" not in labels:
                labels.append("production")
            langfuse.create_prompt(
                name=name,
                prompt=content,
                labels=labels,
            )

            if existing:
                results["updated"].append(name)
                print(f"✅ Updated: {name}")
            else:
                results["created"].append(name)
                print(f"✅ Created: {name}")

        except Exception as e:
            results["errors"].append({"name": name, "error": str(e)})
            print(f"❌ Error for {name}: {e}")

    # Flush to ensure all events are sent
    langfuse.flush()

    print("\n" + "=" * 60)
    print("Migration Summary:")
    print(f"  Created: {len(results['created'])}")
    print(f"  Updated: {len(results['updated'])}")
    print(f"  Skipped: {len(results['skipped'])}")
    print(f"  Errors:  {len(results['errors'])}")
    print("=" * 60)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Emma prompts from YAML to Langfuse"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without making changes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Update existing prompts (creates new version)",
    )
    parser.add_argument(
        "--sections",
        type=str,
        help="Comma-separated sections to migrate (e.g., 'agents,sectors')",
    )
    parser.add_argument(
        "--yaml-path",
        type=str,
        default=None,
        help="Path to emma_prompts.yaml",
    )

    args = parser.parse_args()

    # Find YAML file
    if args.yaml_path:
        yaml_path = Path(args.yaml_path)
    else:
        # Try common locations
        candidates = [
            Path(__file__).parent.parent / "microservices" / "emma-agent-service" / "config" / "prompts" / "emma_prompts.yaml",
            Path("/app/config/prompts/emma_prompts.yaml"),
        ]
        yaml_path = None
        for candidate in candidates:
            if candidate.exists():
                yaml_path = candidate
                break

        if not yaml_path:
            print("❌ Could not find emma_prompts.yaml. Use --yaml-path to specify location.")
            sys.exit(1)

    print(f"📄 Loading prompts from: {yaml_path}")

    # Load YAML
    yaml_data = load_yaml_prompts(yaml_path)

    # Parse sections
    sections = None
    if args.sections:
        sections = [s.strip() for s in args.sections.split(",")]

    # Extract prompts
    prompts = extract_prompts_to_migrate(yaml_data, sections)
    print(f"📊 Found {len(prompts)} prompts to migrate")

    # Migrate
    migrate_to_langfuse(prompts, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()

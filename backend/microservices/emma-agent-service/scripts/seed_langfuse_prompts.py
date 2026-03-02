#!/usr/bin/env python3
"""
Seed Langfuse prompts from emma_prompts.yaml.

Creates/updates prompts in Langfuse for all sections registered in the
LangfusePromptClient name_mapping. Each prompt is created with:
- type="text"
- label="production"
- config with metadata (section, block, role)

If a prompt already exists, Langfuse auto-creates a new version.

Usage:
    # Inside Docker container (recommended):
    docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py

    # With specific section filter:
    docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py --section verified_generation

    # Dry run (show what would be created):
    docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py --dry-run

    # With custom Langfuse credentials:
    LANGFUSE_HOST=http://localhost:3002 \
    LANGFUSE_PUBLIC_KEY=pk-lf-xxx \
    LANGFUSE_SECRET_KEY=sk-lf-xxx \
    python scripts/seed_langfuse_prompts.py

Environment variables:
    LANGFUSE_HOST         Langfuse server URL (default: http://langfuse:3000)
    LANGFUSE_PUBLIC_KEY   Langfuse public key
    LANGFUSE_SECRET_KEY   Langfuse secret key
"""

import argparse
import os
import sys
from pathlib import Path

import yaml


# ── YAML path → Langfuse name mapping ──────────────────────────────────────
# Same mapping as LangfusePromptClient.name_mapping, inverted for seeding.
# Format: langfuse_name → (yaml_path_tuple, section_name)

PROMPT_REGISTRY = {
    # Core prompts
    "emma_context_root": (("context_root",), "core"),
    "emma_synthesis": (("system_prompts", "synthesis"), "core"),
    "emma_planning": (("system_prompts", "planning"), "core"),

    # Action instructions
    "emma_action_generate": (("action_instructions", "generate"), "actions"),
    "emma_action_retrieve": (("action_instructions", "retrieve"), "actions"),

    # Sector prompts
    "emma_sector_legal": (("sectors", "legal", "system_prompt"), "sectors"),
    "emma_sector_medical": (("sectors", "medical", "system_prompt"), "sectors"),
    "emma_sector_documental": (("sectors", "documental", "system_prompt"), "sectors"),

    # Chat prompts
    "emma_chat_base": (("chat_prompts", "base"), "chat"),
    "emma_chat_analyze": (("chat_prompts", "analyze"), "chat"),
    "emma_chat_compare": (("chat_prompts", "compare"), "chat"),
    "emma_chat_summarize": (("chat_prompts", "summarize"), "chat"),
    "emma_chat_search": (("chat_prompts", "search"), "chat"),
    "emma_chat_extract": (("chat_prompts", "extract"), "chat"),
    "emma_chat_explain": (("chat_prompts", "explain"), "chat"),

    # Social channel
    "emma_social_system": (("social_channels", "system_prompt"), "social"),
    "emma_social_conversational": (("social_channels", "conversational_prompt"), "social"),

    # Heartbeat
    "emma_heartbeat_evaluator": (("heartbeat", "evaluation_system"), "heartbeat"),

    # Predictive Analysis
    "emma_predictive_factor_system": (("predictive", "factor_extraction", "system"), "predictive"),
    "emma_predictive_factor_user_first": (("predictive", "factor_extraction", "user_first"), "predictive"),
    "emma_predictive_factor_user_next": (("predictive", "factor_extraction", "user_next"), "predictive"),
    "emma_predictive_completion_system": (("predictive", "completion_check", "system"), "predictive"),
    "emma_predictive_completion_user": (("predictive", "completion_check", "user"), "predictive"),
    "emma_predictive_outcome_system": (("predictive", "outcome_evaluation", "system"), "predictive"),
    "emma_predictive_outcome_user": (("predictive", "outcome_evaluation", "user"), "predictive"),
    "emma_predictive_weight_system": (("predictive", "factor_weighting", "system"), "predictive"),
    "emma_predictive_weight_user": (("predictive", "factor_weighting", "user"), "predictive"),
    "emma_predictive_recommendation_system": (("predictive", "recommendation", "system"), "predictive"),
    "emma_predictive_recommendation_user": (("predictive", "recommendation", "user"), "predictive"),

    # ReAct Agent (main reasoning loop)
    "emma_react_system": (("react_agent", "system"), "react"),
    "emma_react_next_step": (("react_agent", "next_step"), "react"),

    # Verified Generation
    "emma_verified_claim_system": (("verified_generation", "claim_generation", "system"), "verified_generation"),
    "emma_verified_claim_user_first": (("verified_generation", "claim_generation", "user_first"), "verified_generation"),
    "emma_verified_claim_user_next": (("verified_generation", "claim_generation", "user_next"), "verified_generation"),
    "emma_verified_completion_system": (("verified_generation", "completion_check", "system"), "verified_generation"),
    "emma_verified_completion_user": (("verified_generation", "completion_check", "user"), "verified_generation"),
    "emma_verified_factcheck_system": (("verified_generation", "fact_checking", "system"), "verified_generation"),
    "emma_verified_factcheck_user": (("verified_generation", "fact_checking", "user"), "verified_generation"),
}


def load_yaml(yaml_path: Path) -> dict:
    """Load emma_prompts.yaml."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_yaml_path(data: dict, path: tuple) -> str | None:
    """Navigate nested dict by tuple path, return string content or None."""
    value = data
    for key in path:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    return value if isinstance(value, str) else None


def diff_prompts(section_filter: str | None = None) -> tuple[list[str], list[str], list[str]]:
    """
    Compare PROMPT_REGISTRY against prompts that exist in Langfuse.

    Returns:
        (missing, present, extra) — missing from Langfuse, present in both,
        extra in Langfuse (not in registry)
    """
    from langfuse import Langfuse

    host = os.getenv("LANGFUSE_HOST", "http://langfuse:3000")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")

    if not public_key or not secret_key:
        print("ERROR: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")
        sys.exit(1)

    langfuse = Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
    )
    print(f"Connected to Langfuse at {host}\n")

    # Fetch all prompts from Langfuse via API
    remote_names: set[str] = set()
    try:
        import httpx

        url = f"{host}/api/public/v2/prompts"
        auth = (public_key, secret_key)
        page = 1
        while True:
            resp = httpx.get(url, params={"page": page, "limit": 100}, auth=auth, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            prompts = data.get("data", [])
            if not prompts:
                break
            for p in prompts:
                remote_names.add(p["name"])
            # Check pagination
            meta = data.get("meta", {})
            total_pages = meta.get("totalPages", 1)
            if page >= total_pages:
                break
            page += 1
    except ImportError:
        # Fallback: try fetching each prompt individually
        print("httpx not available, checking prompts one by one (slower)...\n")
        for name in PROMPT_REGISTRY:
            try:
                langfuse.get_prompt(name=name)
                remote_names.add(name)
            except Exception:
                pass
    except Exception as e:
        print(f"Warning: Could not list prompts via API ({e}), checking one by one...\n")
        for name in PROMPT_REGISTRY:
            try:
                langfuse.get_prompt(name=name)
                remote_names.add(name)
            except Exception:
                pass

    # Filter registry by section
    registry_names = {
        name
        for name, (_, section) in PROMPT_REGISTRY.items()
        if section_filter is None or section == section_filter
    }

    missing = sorted(registry_names - remote_names)
    present = sorted(registry_names & remote_names)
    extra = sorted(remote_names - set(PROMPT_REGISTRY.keys()))

    return missing, present, extra


def seed_prompts(
    yaml_path: Path,
    section_filter: str | None = None,
    dry_run: bool = False,
    label: str = "production",
) -> tuple[int, int, int]:
    """
    Seed prompts from YAML into Langfuse.

    Returns:
        (created, skipped, errors) counts
    """
    # Load YAML
    data = load_yaml(yaml_path)

    # Filter prompts by section
    prompts_to_seed = {
        name: (path, section)
        for name, (path, section) in PROMPT_REGISTRY.items()
        if section_filter is None or section == section_filter
    }

    if not prompts_to_seed:
        print(f"No prompts found for section filter: {section_filter}")
        return 0, 0, 0

    print(f"Found {len(prompts_to_seed)} prompts to seed")
    if section_filter:
        print(f"  Section filter: {section_filter}")
    print()

    if dry_run:
        print("DRY RUN — no changes will be made\n")

    # Initialize Langfuse client
    langfuse = None
    if not dry_run:
        try:
            from langfuse import Langfuse

            host = os.getenv("LANGFUSE_HOST", "http://langfuse:3000")
            public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
            secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")

            if not public_key or not secret_key:
                print("ERROR: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")
                sys.exit(1)

            langfuse = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            print(f"Connected to Langfuse at {host}\n")

        except ImportError:
            print("ERROR: langfuse package not installed. Run: pip install langfuse")
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: Failed to connect to Langfuse: {e}")
            sys.exit(1)

    created = 0
    skipped = 0
    errors = 0

    for name, (path, section) in sorted(prompts_to_seed.items()):
        content = resolve_yaml_path(data, path)

        if content is None:
            print(f"  SKIP  {name} — not found in YAML at {'.'.join(path)}")
            skipped += 1
            continue

        # Determine role from the last path component
        role = path[-1] if len(path) > 1 else "system"

        if dry_run:
            print(f"  WOULD CREATE  {name}")
            print(f"                section={section}, role={role}, {len(content)} chars")
            created += 1
            continue

        try:
            langfuse.create_prompt(
                name=name,
                type="text",
                prompt=content,
                labels=[label],
                config={
                    "section": section,
                    "yaml_path": ".".join(path),
                    "role": role,
                },
            )
            print(f"  OK  {name} ({len(content)} chars) [{label}]")
            created += 1

        except Exception as e:
            print(f"  ERR  {name} — {e}")
            errors += 1

    # Flush pending events
    if langfuse:
        try:
            langfuse.flush()
        except Exception:
            pass

    return created, skipped, errors


def main():
    parser = argparse.ArgumentParser(
        description="Seed Langfuse prompts from emma_prompts.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Sections available:
  core                 Context root, synthesis, planning
  actions              Action instructions (generate, retrieve)
  sectors              Sector system prompts (legal, medical, documental)
  chat                 Chat prompts (base, analyze, compare, etc.)
  social               Social channel prompts
  heartbeat            Heartbeat evaluator
  predictive           Predictive analysis (10 prompts)
  verified_generation  Verified generation (7 prompts)

Examples:
  # Check which prompts are missing from Langfuse
  python scripts/seed_langfuse_prompts.py --diff

  # Check only heartbeat section
  python scripts/seed_langfuse_prompts.py --diff --section heartbeat

  # Seed ONLY the missing prompts (safe — won't touch existing ones)
  python scripts/seed_langfuse_prompts.py --seed-missing

  # Seed all prompts (creates new versions for existing ones)
  python scripts/seed_langfuse_prompts.py

  # Seed only verified generation
  python scripts/seed_langfuse_prompts.py --section verified_generation

  # Dry run to preview
  python scripts/seed_langfuse_prompts.py --dry-run
        """,
    )
    parser.add_argument(
        "--section",
        choices=[
            "core", "actions", "sectors", "chat", "social",
            "heartbeat", "predictive", "react", "verified_generation",
        ],
        help="Only seed prompts from this section",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show which prompts are missing, present, or extra in Langfuse",
    )
    parser.add_argument(
        "--seed-missing",
        action="store_true",
        help="Only seed prompts that are missing from Langfuse (use with --diff)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without making changes",
    )
    parser.add_argument(
        "--label",
        default="production",
        help="Label to assign to created prompts (default: production)",
    )
    parser.add_argument(
        "--yaml-path",
        type=Path,
        default=None,
        help="Path to emma_prompts.yaml (auto-detected if not specified)",
    )

    args = parser.parse_args()

    # Resolve YAML path
    if args.yaml_path:
        yaml_path = args.yaml_path
    else:
        candidates = [
            Path("/app/config/prompts/emma_prompts.yaml"),  # Docker
            Path(__file__).parent.parent / "config" / "prompts" / "emma_prompts.yaml",  # Local
        ]
        yaml_path = next((p for p in candidates if p.exists()), None)

    if not yaml_path or not yaml_path.exists():
        print(f"ERROR: emma_prompts.yaml not found. Tried: {candidates}")
        sys.exit(1)

    # ── Diff mode ──────────────────────────────────────────────
    if args.diff or args.seed_missing:
        print("Comparing PROMPT_REGISTRY against Langfuse...")
        print("=" * 60)

        missing, present, extra = diff_prompts(section_filter=args.section)

        print(f"  PRESENT in Langfuse ({len(present)}):")
        for name in present:
            section = PROMPT_REGISTRY[name][1]
            print(f"    ✅ {name}  [{section}]")

        print(f"\n  MISSING from Langfuse ({len(missing)}):")
        for name in missing:
            section = PROMPT_REGISTRY[name][1]
            print(f"    ❌ {name}  [{section}]")

        if extra:
            print(f"\n  EXTRA in Langfuse (not in registry) ({len(extra)}):")
            for name in extra:
                print(f"    ⚠️  {name}")

        print()
        print("=" * 60)
        print(f"Summary: {len(present)} present, {len(missing)} missing, {len(extra)} extra")

        if not missing:
            print("\nAll prompts are synced! Nothing to do.")
            return

        if args.seed_missing and missing:
            print(f"\nSeeding {len(missing)} missing prompts...")
            print("-" * 60)

            if not yaml_path or not yaml_path.exists():
                print(f"ERROR: emma_prompts.yaml not found")
                sys.exit(1)

            data = load_yaml(yaml_path)

            from langfuse import Langfuse
            langfuse = Langfuse(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
                host=os.getenv("LANGFUSE_HOST", "http://langfuse:3000"),
            )

            created = 0
            errors = 0
            for name in missing:
                path, section = PROMPT_REGISTRY[name]
                content = resolve_yaml_path(data, path)
                if content is None:
                    print(f"  SKIP  {name} — not found in YAML")
                    continue

                role = path[-1] if len(path) > 1 else "system"
                try:
                    langfuse.create_prompt(
                        name=name,
                        type="text",
                        prompt=content,
                        labels=[args.label],
                        config={
                            "section": section,
                            "yaml_path": ".".join(path),
                            "role": role,
                        },
                    )
                    print(f"  OK  {name} ({len(content)} chars) [{args.label}]")
                    created += 1
                except Exception as e:
                    print(f"  ERR  {name} — {e}")
                    errors += 1

            langfuse.flush()
            print(f"\nSeeded: {created} created, {errors} errors")

        return

    # ── Normal seed mode ──────────────────────────────────────
    print(f"YAML source: {yaml_path}")
    print(f"Label: {args.label}")
    print("=" * 60)

    created, skipped, errors = seed_prompts(
        yaml_path=yaml_path,
        section_filter=args.section,
        dry_run=args.dry_run,
        label=args.label,
    )

    print()
    print("=" * 60)
    print(f"Results: {created} created, {skipped} skipped, {errors} errors")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

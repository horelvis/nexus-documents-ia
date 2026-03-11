#!/usr/bin/env python3
"""
Seed Langfuse prompts from emma_prompts.yaml.

SAFE BY DEFAULT: Only creates prompts that don't exist in Langfuse yet.
Use --force to overwrite existing prompts (creates new versions).

Each prompt is created with:
- type="text"
- label="production"
- config with metadata (section, yaml_path, role)

Usage:
    # Inside Docker container (recommended):
    # Default: seed only MISSING prompts (safe — won't touch existing ones)
    docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py

    # Force overwrite ALL prompts (creates new versions):
    docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py --force

    # Dry run (show what would be created/skipped):
    docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py --dry-run

    # With specific section filter:
    docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py --section verified_generation

    # Show diff between registry and Langfuse:
    docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py --diff

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

# Allow imports from app when running inside the container
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.prompt_registry import PROMPT_REGISTRY, get_all_sections


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


def _get_langfuse_client():
    """Create and return a Langfuse client from environment variables."""
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
    return langfuse, host, public_key, secret_key


def _fetch_remote_prompt_names(host: str, public_key: str, secret_key: str, langfuse) -> set[str]:
    """Fetch all prompt names from Langfuse. Falls back to one-by-one check."""
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
            meta = data.get("meta", {})
            total_pages = meta.get("totalPages", 1)
            if page >= total_pages:
                break
            page += 1
    except ImportError:
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

    return remote_names


def diff_prompts(section_filter: str | None = None) -> tuple[list[str], list[str], list[str]]:
    """
    Compare PROMPT_REGISTRY against prompts that exist in Langfuse.

    Returns:
        (missing, present, extra) — missing from Langfuse, present in both,
        extra in Langfuse (not in registry)
    """
    langfuse, host, public_key, secret_key = _get_langfuse_client()
    remote_names = _fetch_remote_prompt_names(host, public_key, secret_key, langfuse)

    # Filter registry by section
    registry_names = {
        name
        for name, entry in PROMPT_REGISTRY.items()
        if section_filter is None or entry.section == section_filter
    }

    missing = sorted(registry_names - remote_names)
    present = sorted(registry_names & remote_names)
    extra = sorted(remote_names - set(PROMPT_REGISTRY.keys()))

    return missing, present, extra


def seed_prompts(
    yaml_path: Path,
    section_filter: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    label: str = "production",
) -> tuple[int, int, int]:
    """
    Seed prompts from YAML into Langfuse.

    By default (force=False), only creates prompts that don't exist yet.
    With force=True, creates new versions for all prompts.

    Returns:
        (created, skipped, errors) counts
    """
    # Load YAML
    data = load_yaml(yaml_path)

    # Filter prompts by section
    prompts_to_seed = {
        name: entry
        for name, entry in PROMPT_REGISTRY.items()
        if section_filter is None or entry.section == section_filter
    }

    if not prompts_to_seed:
        print(f"No prompts found for section filter: {section_filter}")
        return 0, 0, 0

    print(f"Found {len(prompts_to_seed)} prompts in registry")
    if section_filter:
        print(f"  Section filter: {section_filter}")
    if not force:
        print(f"  Mode: safe (skip existing) — use --force to overwrite")
    else:
        print(f"  Mode: FORCE (will create new versions for existing prompts)")
    print()

    if dry_run:
        print("DRY RUN — no changes will be made\n")

    # Initialize Langfuse client and check existing prompts
    langfuse = None
    existing_names: set[str] = set()

    if not dry_run:
        try:
            langfuse, host, public_key, secret_key = _get_langfuse_client()

            # When not forcing, check which prompts already exist
            if not force:
                print("Checking existing prompts in Langfuse...")
                existing_names = _fetch_remote_prompt_names(host, public_key, secret_key, langfuse)
                print(f"  Found {len(existing_names)} existing prompts\n")

        except ImportError:
            print("ERROR: langfuse package not installed. Run: pip install langfuse")
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: Failed to connect to Langfuse: {e}")
            sys.exit(1)

    created = 0
    skipped = 0
    errors = 0

    for name, entry in sorted(prompts_to_seed.items()):
        content = resolve_yaml_path(data, entry.yaml_path)

        if content is None:
            print(f"  SKIP  {name} — not found in YAML at {'.'.join(entry.yaml_path)}")
            skipped += 1
            continue

        # Determine role from the last path component
        role = entry.yaml_path[-1] if len(entry.yaml_path) > 1 else "system"

        # Skip existing prompts unless --force
        if not force and name in existing_names:
            print(f"  EXIST {name} — skipping (use --force to overwrite)")
            skipped += 1
            continue

        if dry_run:
            action = "WOULD CREATE" if name not in existing_names else "WOULD OVERWRITE"
            print(f"  {action}  {name}")
            print(f"              section={entry.section}, role={role}, {len(content)} chars")
            created += 1
            continue

        try:
            langfuse.create_prompt(
                name=name,
                type=entry.prompt_type,
                prompt=content,
                labels=[label],
                config={
                    "section": entry.section,
                    "yaml_path": ".".join(entry.yaml_path),
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
    all_sections = get_all_sections()

    parser = argparse.ArgumentParser(
        description="Seed Langfuse prompts from emma_prompts.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Sections available:
{chr(10).join(f'  {s}' for s in all_sections)}

Examples:
  # Default: seed ONLY missing prompts (safe — won't touch existing ones)
  python scripts/seed_langfuse_prompts.py

  # Force overwrite all prompts (creates new Langfuse versions)
  python scripts/seed_langfuse_prompts.py --force

  # Dry run to preview what would happen
  python scripts/seed_langfuse_prompts.py --dry-run

  # Check which prompts are missing from Langfuse
  python scripts/seed_langfuse_prompts.py --diff

  # Seed only verified generation section
  python scripts/seed_langfuse_prompts.py --section verified_generation

  # Force overwrite only heartbeat section
  python scripts/seed_langfuse_prompts.py --force --section heartbeat
        """,
    )
    parser.add_argument(
        "--section",
        choices=all_sections,
        help="Only seed prompts from this section",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show which prompts are missing, present, or extra in Langfuse",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing prompts (creates new versions)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created/skipped without making changes",
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
    # Keep --seed-missing for backwards compatibility (now the default behavior)
    parser.add_argument(
        "--seed-missing",
        action="store_true",
        help=argparse.SUPPRESS,  # Hidden — this is now the default
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
    if args.diff:
        print("Comparing PROMPT_REGISTRY against Langfuse...")
        print("=" * 60)

        missing, present, extra = diff_prompts(section_filter=args.section)

        print(f"  PRESENT in Langfuse ({len(present)}):")
        for name in present:
            entry = PROMPT_REGISTRY[name]
            print(f"    ✅ {name}  [{entry.section}]")

        print(f"\n  MISSING from Langfuse ({len(missing)}):")
        for name in missing:
            entry = PROMPT_REGISTRY[name]
            print(f"    ❌ {name}  [{entry.section}]")

        if extra:
            print(f"\n  EXTRA in Langfuse (not in registry) ({len(extra)}):")
            for name in extra:
                print(f"    ⚠️  {name}")

        print()
        print("=" * 60)
        print(f"Summary: {len(present)} present, {len(missing)} missing, {len(extra)} extra")

        if not missing:
            print("\nAll prompts are synced! Nothing to do.")
        else:
            print(f"\nRun without --diff to seed the {len(missing)} missing prompts.")

        return

    # ── Seed mode (default: safe / --force: overwrite) ────────
    print(f"YAML source: {yaml_path}")
    print(f"Label: {args.label}")
    print("=" * 60)

    created, skipped, errors = seed_prompts(
        yaml_path=yaml_path,
        section_filter=args.section,
        dry_run=args.dry_run,
        force=args.force,
        label=args.label,
    )

    print()
    print("=" * 60)
    print(f"Results: {created} created, {skipped} skipped, {errors} errors")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

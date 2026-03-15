#!/usr/bin/env python3
"""
Seed guardrails from guardrail_registry into Main API (PostgreSQL).

SAFE BY DEFAULT: Only creates guardrails that don't exist in the DB yet.
Use --force to create even if exists (the API will handle upsert or error).

Usage:
    # Inside Docker container (recommended):
    # Default: seed only MISSING guardrails (safe — won't touch existing ones)
    docker compose exec emma-agent-service python scripts/seed_guardrails.py

    # Force create all guardrails (API handles upsert or error):
    docker compose exec emma-agent-service python scripts/seed_guardrails.py --force

    # Dry run (show what would be created/skipped):
    docker compose exec emma-agent-service python scripts/seed_guardrails.py --dry-run

    # Show diff between registry and DB:
    docker compose exec emma-agent-service python scripts/seed_guardrails.py --diff

    # Only seed medical sector guardrails:
    docker compose exec emma-agent-service python scripts/seed_guardrails.py --sector medical

Environment variables:
    API_URL               Main API URL (default: http://main-api:8000)
    MICROSERVICES_API_KEY  API key for inter-service auth
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple

import httpx

# Allow imports from app when running inside the container
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.guardrail_registry import GUARDRAIL_ENTRIES, GuardrailEntry

# ── ANSI colors ────────────────────────────────────────────────────────────────
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _get_api_config() -> Tuple[str, str]:
    """Return (api_url, api_key) from environment or defaults."""
    api_url = os.getenv("API_URL", "http://main-api:8000")
    api_key = os.getenv("MICROSERVICES_API_KEY", "")

    if not api_key:
        # Try loading from app settings as fallback
        try:
            from app.core.config import settings
            api_key = settings.MICROSERVICES_API_KEY
        except Exception:
            pass

    if not api_key:
        print(f"{RED}ERROR: MICROSERVICES_API_KEY must be set{RESET}")
        sys.exit(1)

    return api_url, api_key


def _filter_entries(sector: Optional[str] = None) -> List[GuardrailEntry]:
    """Filter entries by sector. None sector matches global + that sector."""
    if sector is None:
        return list(GUARDRAIL_ENTRIES)
    return [e for e in GUARDRAIL_ENTRIES if e.sector == sector or e.sector is None]


def _fetch_existing_names(api_url: str, api_key: str) -> Set[str]:
    """Fetch existing guardrail names from Main API."""
    existing: Set[str] = set()
    try:
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        resp = httpx.get(
            f"{api_url}/api/v1/prompts/guardrails",
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        guardrails = data if isinstance(data, list) else data.get("guardrails", data.get("data", []))
        for g in guardrails:
            name = g.get("guardrail_name") or g.get("name", "")
            if name:
                existing.add(name)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"{YELLOW}  Warning: Guardrails endpoint not found (404) — assuming empty DB{RESET}")
        else:
            print(f"{YELLOW}  Warning: Could not list existing guardrails ({e}) — assuming empty DB{RESET}")
    except Exception as e:
        print(f"{YELLOW}  Warning: Could not connect to API ({e}) — assuming empty DB{RESET}")

    return existing


def diff_guardrails(sector: Optional[str] = None) -> Tuple[List[str], List[str], List[str]]:
    """
    Compare registry against DB guardrails.

    Returns:
        (missing, present, extra) — missing from DB, present in both,
        extra in DB (not in registry)
    """
    api_url, api_key = _get_api_config()
    print(f"Connected to API at {api_url}\n")

    existing_names = _fetch_existing_names(api_url, api_key)
    entries = _filter_entries(sector)
    registry_names = {e.name for e in entries}

    missing = sorted(registry_names - existing_names)
    present = sorted(registry_names & existing_names)
    extra = sorted(existing_names - {e.name for e in GUARDRAIL_ENTRIES})

    return missing, present, extra


def seed_guardrails(
    sector: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
) -> Tuple[int, int, int]:
    """
    Seed guardrails from registry into Main API.

    By default (force=False), only creates guardrails that don't exist yet.
    With force=True, creates even if exists (the API handles upsert or error).

    Returns:
        (created, skipped, errors) counts
    """
    entries = _filter_entries(sector)

    if not entries:
        print(f"No guardrails found for sector filter: {sector}")
        return 0, 0, 0

    print(f"Found {len(entries)} guardrails in registry")
    if sector:
        print(f"  Sector filter: {sector}")
    if not force:
        print(f"  Mode: safe (skip existing) — use --force to overwrite")
    else:
        print(f"  Mode: FORCE (will create even if exists — API handles upsert)")
    print()

    if dry_run:
        print("DRY RUN — no changes will be made\n")

    api_url, api_key = _get_api_config()
    existing_names: Set[str] = set()

    if not dry_run:
        print(f"API: {api_url}")
        if not force:
            print("Checking existing guardrails in DB...")
            existing_names = _fetch_existing_names(api_url, api_key)
            print(f"  Found {len(existing_names)} existing guardrails\n")
    else:
        # For dry-run, still check existing to show accurate actions
        existing_names = _fetch_existing_names(api_url, api_key)

    created = 0
    skipped = 0
    errors = 0

    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    for entry in sorted(entries, key=lambda e: (e.priority, e.name)):
        # Skip existing guardrails unless --force
        if not force and entry.name in existing_names:
            print(f"  {YELLOW}⏭️  SKIP{RESET}  {entry.name} — already exists (use --force to overwrite)")
            skipped += 1
            continue

        if dry_run:
            action = "WOULD CREATE" if entry.name not in existing_names else "WOULD OVERWRITE"
            print(f"  {action}  {entry.name}")
            print(f"              type={entry.guardrail_type}, action={entry.action}, "
                  f"sector={entry.sector or 'global'}, priority={entry.priority}")
            created += 1
            continue

        body = {
            "guardrail_name": entry.name,
            "description": entry.description,
            "guardrail_type": entry.guardrail_type,
            "config": entry.config,
            "action_on_match": entry.action,
            "applies_to": entry.applies_to,
            "priority": entry.priority,
            "sector": entry.sector,
        }

        try:
            resp = httpx.post(
                f"{api_url}/api/v1/prompts/guardrails",
                headers=headers,
                json=body,
                timeout=15.0,
            )
            resp.raise_for_status()
            print(f"  {GREEN}✅ Created{RESET}  {entry.name} "
                  f"[{entry.guardrail_type}/{entry.action}, "
                  f"sector={entry.sector or 'global'}]")
            created += 1

        except httpx.HTTPStatusError as e:
            print(f"  {RED}❌ Error{RESET}   {entry.name} — HTTP {e.response.status_code}: "
                  f"{e.response.text[:200]}")
            errors += 1

        except Exception as e:
            print(f"  {RED}❌ Error{RESET}   {entry.name} — {e}")
            errors += 1

    return created, skipped, errors


def _get_all_sectors() -> List[str]:
    """Return sorted list of unique sector names from registry."""
    return sorted({e.sector for e in GUARDRAIL_ENTRIES if e.sector})


def main():
    all_sectors = _get_all_sectors()

    parser = argparse.ArgumentParser(
        description="Seed guardrails from guardrail_registry into Main API (PostgreSQL)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Sectors available:
{chr(10).join(f'  {s}' for s in all_sectors)}

Examples:
  # Default: seed ONLY missing guardrails (safe — won't touch existing ones)
  python scripts/seed_guardrails.py

  # Force create all guardrails (API handles upsert or error)
  python scripts/seed_guardrails.py --force

  # Dry run to preview what would happen
  python scripts/seed_guardrails.py --dry-run

  # Check which guardrails are missing from DB
  python scripts/seed_guardrails.py --diff

  # Seed only medical sector guardrails
  python scripts/seed_guardrails.py --sector medical

  # Force overwrite only legal sector
  python scripts/seed_guardrails.py --force --sector legal
        """,
    )
    parser.add_argument(
        "--sector",
        choices=all_sectors,
        help="Only seed guardrails for this sector (also includes global guardrails)",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show which guardrails are missing, present, or extra in DB",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force create even if exists (API handles upsert or error)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created/skipped without making changes",
    )

    args = parser.parse_args()

    # ── Diff mode ──────────────────────────────────────────────
    if args.diff:
        print("Comparing guardrail_registry against DB...")
        print("=" * 60)

        missing, present, extra = diff_guardrails(sector=args.sector)

        print(f"  PRESENT in DB ({len(present)}):")
        for name in present:
            entry = next(e for e in GUARDRAIL_ENTRIES if e.name == name)
            print(f"    {GREEN}✅{RESET} {name}  [{entry.sector or 'global'}]")

        print(f"\n  MISSING from DB ({len(missing)}):")
        for name in missing:
            entry = next(e for e in GUARDRAIL_ENTRIES if e.name == name)
            print(f"    {RED}❌{RESET} {name}  [{entry.sector or 'global'}]")

        if extra:
            print(f"\n  EXTRA in DB (not in registry) ({len(extra)}):")
            for name in extra:
                print(f"    {YELLOW}⚠️{RESET}  {name}")

        print()
        print("=" * 60)
        print(f"Summary: {len(present)} present, {len(missing)} missing, {len(extra)} extra")

        if not missing:
            print("\nAll guardrails are synced! Nothing to do.")
        else:
            print(f"\nRun without --diff to seed the {len(missing)} missing guardrails.")

        return

    # ── Seed mode (default: safe / --force: overwrite) ────────
    print("=" * 60)

    created, skipped, errors = seed_guardrails(
        sector=args.sector,
        dry_run=args.dry_run,
        force=args.force,
    )

    print()
    print("=" * 60)
    print(f"Results: {created} created, {skipped} skipped, {errors} errors")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

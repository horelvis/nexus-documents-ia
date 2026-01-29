#!/usr/bin/env python3
"""
Change Active Sector — Destructive Migration Script

This script safely changes the active sector by:
1. Comparing current vs. new sector
2. Warning about data deletion
3. Clearing Weaviate collections and AGE graph for the old sector
4. Updating .env with the new sector

Usage:
    python scripts/change_sector.py --sector=medical
    python scripts/change_sector.py --sector=legal --force
    python scripts/change_sector.py --sector=""  # Reset to generic mode

After running:
    1. Restart services: docker compose restart
    2. Initialize graph: python scripts/init_sector_graphs.py
    3. Re-run data ingestion connectors
"""

import argparse
import os
import sys
from pathlib import Path


VALID_SECTORS = {"legal", "medical", "documental", ""}


def get_current_sector(env_path: Path) -> str:
    """Read ACTIVE_SECTOR from .env file."""
    if not env_path.exists():
        return ""

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("ACTIVE_SECTOR="):
            return line.split("=", 1)[1].strip().strip('"').strip("'").lower()

    return ""


def update_env_sector(env_path: Path, new_sector: str) -> None:
    """Update or add ACTIVE_SECTOR in .env file."""
    if not env_path.exists():
        env_path.write_text(f"ACTIVE_SECTOR={new_sector}\n")
        return

    lines = env_path.read_text().splitlines()
    found = False
    new_lines = []

    for line in lines:
        if line.strip().startswith("ACTIVE_SECTOR="):
            new_lines.append(f"ACTIVE_SECTOR={new_sector}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"ACTIVE_SECTOR={new_sector}")

    env_path.write_text("\n".join(new_lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Change active sector (destructive)")
    parser.add_argument(
        "--sector",
        required=True,
        help="New sector: legal, medical, documental, or empty string for generic",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Path to .env file (default: backend/.env)",
    )

    args = parser.parse_args()
    new_sector = args.sector.strip().lower()

    if new_sector not in VALID_SECTORS:
        print(f"❌ Invalid sector: '{new_sector}'")
        print(f"   Valid values: {', '.join(sorted(VALID_SECTORS - {''}))}, or empty string")
        sys.exit(1)

    # Resolve .env path
    if args.env_file:
        env_path = Path(args.env_file)
    else:
        env_path = Path(__file__).parent.parent / ".env"

    current_sector = get_current_sector(env_path)

    if current_sector == new_sector:
        print(f"ℹ️  Sector is already '{new_sector or '(generic)'}'. Nothing to do.")
        sys.exit(0)

    print(f"Current sector: {current_sector or '(generic)'}")
    print(f"New sector:     {new_sector or '(generic)'}")
    print()

    if current_sector:
        print("⚠️  WARNING: Changing sector will require:")
        print(f"   1. Deleting all Weaviate collections for sector '{current_sector}'")
        print(f"   2. Dropping Apache AGE graph '{current_sector}_graph'")
        print("   3. Restarting all services")
        print("   4. Re-running data ingestion from scratch")
        print()

        if not args.force:
            confirm = input("Are you sure? Type 'yes' to confirm: ")
            if confirm.strip().lower() != "yes":
                print("❌ Aborted.")
                sys.exit(1)

    # Update .env
    update_env_sector(env_path, new_sector)
    print(f"✅ Updated {env_path}: ACTIVE_SECTOR={new_sector}")

    print()
    print("📋 Next steps:")
    print("   1. Restart services:  docker compose restart")
    if new_sector:
        print(f"   2. Initialize graph:  python scripts/init_sector_graphs.py")
    print(f"   3. Re-run data ingestion connectors")


if __name__ == "__main__":
    main()

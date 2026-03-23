#!/usr/bin/env python3
"""DEPRECATED: MemoRAG backfill is no longer needed.

Documents are indexed directly into Weaviate by the standard indexing
pipeline.  MemoRAG recall now delegates to Weaviate hybrid search.

This script is kept as a no-op stub so that existing automation does
not break.
"""

import sys


def main() -> None:
    print(
        "memorag_backfill.py is deprecated. "
        "Documents are already indexed in Weaviate by the indexing pipeline. "
        "MemoRAG recall now uses Weaviate hybrid search directly."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()

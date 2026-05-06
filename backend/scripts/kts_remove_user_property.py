"""
kts_remove_user_property.py — FalkorDB REMOVE n.user / r.user cleanup.

Removes the vestigial `user` property from all :Node/:Chunk/:Literal nodes
and :Rel edges in the `knowledge_graph` FalkorDB graph. After the role-based
ACL removal, the `user` property is no longer read or written; this script
physically removes it from existing data so the schema stays clean.

Idempotent: safe to run multiple times. Nodes/edges without a `user`
property are unaffected.

Usage:
  python kts_remove_user_property.py [--host localhost] [--port 6380] [--graph knowledge_graph]

Requires:
  pip install falkordb
"""

import argparse
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def remove_user_property(host: str, port: int, graph_name: str) -> None:
    try:
        import falkordb
    except ImportError:
        logger.error("falkordb not installed. Run: pip install falkordb")
        sys.exit(1)

    logger.info("Connecting to FalkorDB at %s:%d, graph=%r", host, port, graph_name)
    client = falkordb.FalkorDB(host=host, port=port)
    graph = client.select_graph(graph_name)

    # Remove user from all nodes (Node, Literal, Chunk labels)
    node_query = (
        "MATCH (n) WHERE n.user IS NOT NULL "
        "REMOVE n.user "
        "RETURN count(n) AS removed_nodes"
    )
    try:
        result = graph.query(node_query)
        rows = result.result_set
        count = rows[0][0] if rows else 0
        logger.info("Removed `user` from %d nodes", count)
    except Exception as exc:
        logger.error("Node REMOVE failed: %s", exc)

    # Remove user from all relationships (Rel edges)
    rel_query = (
        "MATCH ()-[r]-() WHERE r.user IS NOT NULL "
        "REMOVE r.user "
        "RETURN count(r) AS removed_rels"
    )
    try:
        result = graph.query(rel_query)
        rows = result.result_set
        count = rows[0][0] if rows else 0
        logger.info("Removed `user` from %d relationships", count)
    except Exception as exc:
        logger.error("Rel REMOVE failed: %s", exc)

    logger.info("FalkorDB user property cleanup complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove vestigial `user` property from FalkorDB")
    parser.add_argument("--host", default="localhost", help="FalkorDB host")
    parser.add_argument("--port", type=int, default=6380, help="FalkorDB port")
    parser.add_argument("--graph", default="knowledge_graph", help="Graph name")
    args = parser.parse_args()

    asyncio.run(remove_user_property(args.host, args.port, args.graph))


if __name__ == "__main__":
    main()

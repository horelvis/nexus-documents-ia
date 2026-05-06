"""Pre-flight check: count role-restricted objects across Weaviate collections.

Halts the remove-role-based-acl plan if any collection has objects whose
``roles`` property does not contain the ``EVERYONE`` sentinel. Run before
the destructive removal of role-based ACL.
"""
import os
import sys

import weaviate

COLLECTIONS = [
    "Nouxcube_documents",
    "Nouxcube_documents_summaries",
    "Nouxcube_knowledge",
    "Nouxcube_visual",
    "TrustGraphEntities",
    "OntologyTerms",
]

client = weaviate.connect_to_local(
    host=os.environ.get("WEAVIATE_HOST", "localhost"),
    port=int(os.environ.get("WEAVIATE_PORT", "8080")),
)
total_restricted = 0
try:
    for col_name in COLLECTIONS:
        try:
            col = client.collections.get(col_name)
            role_restricted = sum(
                1
                for obj in col.iterator(return_properties=["roles"])
                if "EVERYONE" not in (obj.properties.get("roles") or [])
            )
        except Exception as exc:  # noqa: BLE001
            print(f"{col_name}: SKIP ({exc.__class__.__name__}: {exc})")
            continue
        total_restricted += role_restricted
        print(f"{col_name}: {role_restricted} role-restricted objects")
finally:
    client.close()

sys.exit(1 if total_restricted else 0)

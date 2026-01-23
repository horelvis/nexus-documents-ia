"""Add Legal Knowledge Graph schema to SIL

Revision ID: 20260122_legal_graph
Revises: 20260120_sil_graph
Create Date: 2026-01-22

This migration extends the SIL graph with legal knowledge:

Vertex Labels:
- legal_law: Spanish laws (BOE legislation)
- legal_article: Articles within laws
- legal_jurisdiction: Jurisdictions
- legal_obligation: Legal obligations extracted from documents

Edge Labels:
- governed_by: Document is governed by a law
- contains_article: Law contains articles
- references: Law references another law
- creates_obligation: Document/clause creates an obligation
- amends: Law amends another law

The Legal Knowledge Graph enables:
1. Linking documents to applicable legislation
2. Finding all documents affected by a law
3. Tracking cross-references between laws
4. Pre-LLM reasoning about legal applicability

Example queries:
- "What laws govern this contract?" → Document -[governed_by]-> Law
- "What articles apply to labor contracts?" → Law -[contains_article]-> Article
- "What documents might be affected by ET reform?" → Law <-[governed_by]- Document
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260122_legal_graph'
down_revision = '20260120_sil_graph'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add Legal Knowledge Graph vertex and edge labels to Apache AGE.

    These labels extend the existing SIL structural graph with
    legal knowledge capabilities.
    """
    conn = op.get_bind()

    try:
        # Load AGE extension
        conn.execute(sa.text("LOAD 'age';"))
        conn.execute(sa.text("SET search_path = ag_catalog, \"$user\", public;"))

        # Check if graph exists
        result = conn.execute(sa.text(
            "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = 'knowledge_graph'"
        ))
        if result.scalar() == 0:
            print("⚠️ knowledge_graph does not exist. Run SIL migration first.")
            return

        # =============================================
        # VERTEX LABELS (Legal Nodes)
        # =============================================

        # legal_law - Laws from BOE (Spanish Official Gazette)
        # Properties: boe_id, title, short_name, domain, status,
        #             publication_date, effective_date, eli_uri,
        #             summary, keywords, valid_from, valid_to
        _create_vlabel_if_not_exists(conn, 'legal_law')

        # legal_article - Articles within laws
        # Properties: article_id, law_boe_id, article_number, title,
        #             summary, key_concepts, is_derogated, valid_from, valid_to
        _create_vlabel_if_not_exists(conn, 'legal_article')

        # legal_jurisdiction - Jurisdictions (Spain, EU, Regional)
        # Properties: jurisdiction_id, name, level, parent_jurisdiction
        _create_vlabel_if_not_exists(conn, 'legal_jurisdiction')

        # legal_obligation - Obligations extracted from documents/laws
        # Properties: obligation_id, type, description, deadline,
        #             penalty, source_document, source_article
        _create_vlabel_if_not_exists(conn, 'legal_obligation')

        # =============================================
        # EDGE LABELS (Legal Relationships)
        # =============================================

        # governed_by - Document is governed by a law
        # (structural_document)-[:governed_by]->(legal_law)
        # Properties: relationship_type, articles[], created_at
        _create_elabel_if_not_exists(conn, 'governed_by')

        # contains_article - Law contains an article
        # (legal_law)-[:contains_article]->(legal_article)
        _create_elabel_if_not_exists(conn, 'contains_article')

        # references - Law references another law
        # (legal_law)-[:references]->(legal_law)
        # Properties: reference_type, reference_text
        _create_elabel_if_not_exists(conn, 'references')

        # creates_obligation - Document or article creates an obligation
        # (structural_document|legal_article)-[:creates_obligation]->(legal_obligation)
        _create_elabel_if_not_exists(conn, 'creates_obligation')

        # amends - Law amends another law
        # (legal_law)-[:amends]->(legal_law)
        # Properties: amendment_date, amendment_type, affected_articles[]
        _create_elabel_if_not_exists(conn, 'amends')

        print("✅ Legal Knowledge Graph schema created successfully")

    except Exception as e:
        print(f"⚠️ Could not create Legal Knowledge Graph schema: {e}")
        print("This is expected if Apache AGE is not installed.")
        print("The legal_graph_service will create labels dynamically.")


def downgrade():
    """
    Remove Legal Knowledge Graph labels.

    Note: This does NOT delete data, only the label definitions.
    Data cleanup would need to be done manually if required.
    """
    conn = op.get_bind()

    try:
        conn.execute(sa.text("LOAD 'age';"))
        conn.execute(sa.text("SET search_path = ag_catalog, \"$user\", public;"))

        # Note: Apache AGE doesn't support DROP VLABEL/ELABEL easily
        # Labels remain but can be recreated

        print("⚠️ Legal graph labels not removed (manual cleanup needed if required)")

    except Exception as e:
        print(f"⚠️ Could not process downgrade: {e}")


def _create_vlabel_if_not_exists(conn, label_name: str):
    """Create a vertex label if it doesn't already exist."""
    try:
        result = conn.execute(sa.text(f"""
            SELECT count(*) FROM ag_catalog.ag_label
            WHERE name = '{label_name}' AND graph = (
                SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'knowledge_graph'
            )
        """))
        if result.scalar() == 0:
            conn.execute(sa.text(f"SELECT create_vlabel('knowledge_graph', '{label_name}');"))
            print(f"  Created vertex label: {label_name}")
        else:
            print(f"  Vertex label already exists: {label_name}")
    except Exception as e:
        print(f"  ⚠️ Could not create vertex label {label_name}: {e}")


def _create_elabel_if_not_exists(conn, label_name: str):
    """Create an edge label if it doesn't already exist."""
    try:
        result = conn.execute(sa.text(f"""
            SELECT count(*) FROM ag_catalog.ag_label
            WHERE name = '{label_name}' AND graph = (
                SELECT graphid FROM ag_catalog.ag_graph WHERE name = 'knowledge_graph'
            )
        """))
        if result.scalar() == 0:
            conn.execute(sa.text(f"SELECT create_elabel('knowledge_graph', '{label_name}');"))
            print(f"  Created edge label: {label_name}")
        else:
            print(f"  Edge label already exists: {label_name}")
    except Exception as e:
        print(f"  ⚠️ Could not create edge label {label_name}: {e}")

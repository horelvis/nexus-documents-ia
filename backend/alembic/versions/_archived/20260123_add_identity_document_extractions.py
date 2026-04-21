"""Add identity document extractions table

Revision ID: 20260123_identity_docs
Revises: 20260122_legal_graph
Create Date: 2026-01-23

This migration adds support for identity document processing:
- DNI, NIE, Passport, Driver's License extraction
- GDPR-compliant storage with retention policies
- Audit logging for PII access
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260123_identity_docs'
down_revision = '20260122_legal_graph'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Check if table already exists
    table_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'identity_document_extractions'")
    ).fetchone()

    if table_exists:
        print("Table identity_document_extractions already exists, skipping creation")
        return

    # Create enum type if not exists
    enum_exists = conn.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'identity_document_type'")
    ).fetchone()

    if not enum_exists:
        op.execute("""
            CREATE TYPE identity_document_type AS ENUM (
                'dni', 'nie', 'passport', 'driver_license', 'residence_card', 'unknown'
            )
        """)

    # Create identity_document_extractions table using raw SQL to avoid SQLAlchemy enum auto-creation
    op.execute("""
        CREATE TABLE identity_document_extractions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id UUID,
            tenant_id UUID NOT NULL,
            document_type identity_document_type NOT NULL,
            issuing_country VARCHAR(3),
            extracted_data JSONB NOT NULL,
            confidence_score FLOAT NOT NULL,
            ocr_engine VARCHAR(50),
            retention_until TIMESTAMP WITH TIME ZONE NOT NULL,
            consent_purpose VARCHAR(255) NOT NULL,
            access_log JSONB DEFAULT '[]' NOT NULL,
            created_by UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
        )
    """)

    # Create indexes
    op.execute("CREATE INDEX ix_identity_document_extractions_document_id ON identity_document_extractions(document_id)")
    op.execute("CREATE INDEX ix_identity_document_extractions_tenant_id ON identity_document_extractions(tenant_id)")
    op.execute("CREATE INDEX ix_identity_document_extractions_retention ON identity_document_extractions(retention_until)")

    # Check if audit table exists
    audit_exists = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'identity_extraction_audit_log'")
    ).fetchone()

    if not audit_exists:
        # Create audit log table
        op.execute("""
            CREATE TABLE identity_extraction_audit_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                extraction_id UUID REFERENCES identity_document_extractions(id) ON DELETE CASCADE,
                tenant_id UUID NOT NULL,
                user_id UUID NOT NULL,
                action VARCHAR(50) NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                ip_address VARCHAR(45),
                user_agent VARCHAR(500),
                purpose VARCHAR(255) NOT NULL,
                fields_accessed JSONB DEFAULT '[]' NOT NULL,
                metadata JSONB DEFAULT '{}' NOT NULL
            )
        """)

        # Create indexes for audit table
        op.execute("CREATE INDEX ix_identity_audit_extraction_id ON identity_extraction_audit_log(extraction_id)")
        op.execute("CREATE INDEX ix_identity_audit_tenant_id ON identity_extraction_audit_log(tenant_id)")
        op.execute("CREATE INDEX ix_identity_audit_user_id ON identity_extraction_audit_log(user_id)")
        op.execute("CREATE INDEX ix_identity_audit_timestamp ON identity_extraction_audit_log(timestamp)")

    print("Identity document extractions tables created successfully")


def downgrade():
    op.execute("DROP TABLE IF EXISTS identity_extraction_audit_log")
    op.execute("DROP TABLE IF EXISTS identity_document_extractions")
    op.execute("DROP TYPE IF EXISTS identity_document_type")

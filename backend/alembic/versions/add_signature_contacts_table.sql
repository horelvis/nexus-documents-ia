-- Create signature_contacts table
CREATE TABLE IF NOT EXISTS signature_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    created_by UUID NOT NULL REFERENCES users(id),
    
    -- Contact information
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    role VARCHAR(100),
    company VARCHAR(200),
    
    -- Usage tracking
    is_favorite BOOLEAN DEFAULT FALSE NOT NULL,
    usage_count INTEGER DEFAULT 0 NOT NULL,
    last_used_at TIMESTAMP WITH TIME ZONE,
    
    -- Additional metadata
    notes TEXT,
    contact_metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    
    -- Constraints
    CONSTRAINT uq_signature_contact_tenant_email UNIQUE (tenant_id, email)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_signature_contacts_tenant_favorite ON signature_contacts(tenant_id, is_favorite);
CREATE INDEX IF NOT EXISTS idx_signature_contacts_tenant_usage ON signature_contacts(tenant_id, usage_count);
CREATE INDEX IF NOT EXISTS idx_signature_contacts_email ON signature_contacts(email);
CREATE INDEX IF NOT EXISTS idx_signature_contacts_name ON signature_contacts(name);

-- Create update trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_signature_contacts_updated_at 
    BEFORE UPDATE ON signature_contacts 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
-- Create document routing analysis table
CREATE TABLE IF NOT EXISTS document_routing_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    
    -- Analysis results
    document_type VARCHAR(100) NOT NULL,
    document_subtype VARCHAR(100),
    confidence_score FLOAT NOT NULL DEFAULT 0.0,
    language VARCHAR(10),
    
    -- Detected characteristics
    is_signable BOOLEAN DEFAULT FALSE,
    requires_approval BOOLEAN DEFAULT FALSE,
    is_confidential BOOLEAN DEFAULT FALSE,
    has_financial_data BOOLEAN DEFAULT FALSE,
    has_personal_data BOOLEAN DEFAULT FALSE,
    has_legal_clauses BOOLEAN DEFAULT FALSE,
    
    -- Assigned agents
    assigned_agents JSONB DEFAULT '[]'::jsonb,
    routing_strategy VARCHAR(50) DEFAULT 'parallel', -- parallel, sequential, conditional
    priority_level VARCHAR(20) DEFAULT 'normal', -- low, normal, high, urgent
    
    -- Extracted metadata
    extracted_entities JSONB DEFAULT '{}'::jsonb,
    key_dates JSONB DEFAULT '[]'::jsonb,
    monetary_amounts JSONB DEFAULT '[]'::jsonb,
    parties_involved JSONB DEFAULT '[]'::jsonb,
    
    -- Workflow status
    routing_status VARCHAR(50) DEFAULT 'pending', -- pending, routed, processing, completed, failed
    agents_completed JSONB DEFAULT '[]'::jsonb,
    agents_in_progress JSONB DEFAULT '[]'::jsonb,
    agents_failed JSONB DEFAULT '[]'::jsonb,
    
    -- Timestamps
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    routing_started_at TIMESTAMP WITH TIME ZONE,
    routing_completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_routing_document_id ON document_routing_analysis(document_id);
CREATE INDEX idx_routing_tenant_id ON document_routing_analysis(tenant_id);
CREATE INDEX idx_routing_status ON document_routing_analysis(routing_status);
CREATE INDEX idx_routing_document_type ON document_routing_analysis(document_type);
CREATE INDEX idx_routing_priority ON document_routing_analysis(priority_level);

-- Create agent assignments table
CREATE TABLE IF NOT EXISTS document_agent_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    routing_analysis_id UUID NOT NULL REFERENCES document_routing_analysis(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    agent_type VARCHAR(100) NOT NULL,
    agent_name VARCHAR(255) NOT NULL,
    
    -- Assignment details
    assignment_reason TEXT,
    execution_order INTEGER DEFAULT 0,
    dependencies JSONB DEFAULT '[]'::jsonb, -- Other agents that must complete first
    
    -- Execution status
    status VARCHAR(50) DEFAULT 'pending', -- pending, running, completed, failed, skipped
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Results
    result JSONB DEFAULT '{}'::jsonb,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_agent_assignment_routing ON document_agent_assignments(routing_analysis_id);
CREATE INDEX idx_agent_assignment_document ON document_agent_assignments(document_id);
CREATE INDEX idx_agent_assignment_status ON document_agent_assignments(status);
CREATE INDEX idx_agent_assignment_type ON document_agent_assignments(agent_type);
-- =============================================================================
-- Documental Sector Graph Schema for Apache AGE
-- =============================================================================
-- Creates the documental_graph with node labels and edge types for
-- general enterprise document/records management (EDMS).
--
-- Node types:
--   - Expediente (file/case/folder)
--   - Documento (document)
--   - Persona (person — author, recipient, signee)
--   - Organizacion (organization/company)
--   - Categoria (document category/taxonomy)
--   - Flujo (workflow instance)
--   - Ubicacion (physical/digital location)
--
-- Edge types:
--   - CONTIENE (folder contains document)
--   - CREADO_POR (document created by person)
--   - PERTENECE_A (document belongs to organization)
--   - CLASIFICADO_COMO (document classified in category)
--   - VERSION_DE (document is version of another)
--   - RELACIONADO (document related to another)
--   - EN_FLUJO (document in workflow)
--   - ALMACENADO_EN (document stored at location)
--   - FIRMADO_POR (document signed by person)
--   - ASOCIADO_A (document associated with person — inferred from folder path)
-- =============================================================================

-- Create the graph
SELECT create_graph('documental_graph');

-- Create node labels
SELECT create_vlabel('documental_graph', 'Expediente');
SELECT create_vlabel('documental_graph', 'Documento');
SELECT create_vlabel('documental_graph', 'Persona');
SELECT create_vlabel('documental_graph', 'Organizacion');
SELECT create_vlabel('documental_graph', 'Categoria');
SELECT create_vlabel('documental_graph', 'Flujo');
SELECT create_vlabel('documental_graph', 'Ubicacion');

-- Legal proxy nodes (synced from knowledge_graph_public, shared=true)
SELECT create_vlabel('documental_graph', 'LegalLaw');
SELECT create_elabel('documental_graph', 'APLICA');
SELECT create_elabel('documental_graph', 'MODIFIES');
SELECT create_elabel('documental_graph', 'DEROGATES');
SELECT create_elabel('documental_graph', 'REFERENCES');

-- Ontology proxy (for INSTANCE_OF edges to shared EntityType nodes)
SELECT create_vlabel('documental_graph', 'EntityType');

-- Memory Bank (MemoRAG-inspired document summaries for planner clue generation)
SELECT create_vlabel('documental_graph', 'DocumentMemory');

-- Create edge labels
SELECT create_elabel('documental_graph', 'CONTIENE');
SELECT create_elabel('documental_graph', 'CREADO_POR');
SELECT create_elabel('documental_graph', 'PERTENECE_A');
SELECT create_elabel('documental_graph', 'CLASIFICADO_COMO');
SELECT create_elabel('documental_graph', 'VERSION_DE');
SELECT create_elabel('documental_graph', 'RELACIONADO');
SELECT create_elabel('documental_graph', 'EN_FLUJO');
SELECT create_elabel('documental_graph', 'ALMACENADO_EN');
SELECT create_elabel('documental_graph', 'FIRMADO_POR');
SELECT create_elabel('documental_graph', 'ASOCIADO_A');
SELECT create_elabel('documental_graph', 'INSTANCE_OF');
SELECT create_elabel('documental_graph', 'EXTRACTED_FROM');
SELECT create_elabel('documental_graph', 'DEFINE');
SELECT create_elabel('documental_graph', 'REFERENCIA');
SELECT create_elabel('documental_graph', 'HAS_MEMORY');

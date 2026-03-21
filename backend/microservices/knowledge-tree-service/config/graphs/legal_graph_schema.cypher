-- =============================================================================
-- Legal Sector Graph Schema for Apache AGE
-- =============================================================================
-- Creates the legal_graph with node labels and edge types for
-- Spanish legal document management.
--
-- Node types:
--   - Ley (law/regulation)
--   - Articulo (article within a law)
--   - Sentencia (court decision)
--   - Contrato (contract)
--   - Clausula (contract clause)
--   - Parte (party to a contract)
--   - Organismo (regulatory body)
--   - Documento (indexed document reference)
--
-- Edge types:
--   - CONTIENE (law contains articles)
--   - REFERENCIA (article references another)
--   - INTERPRETA (ruling interprets a law/article)
--   - FIRMADO_POR (contract signed by party)
--   - REGULA (law regulates a domain)
--   - DEROGA (law repeals another)
--   - MODIFICA (law modifies another)
--   - APLICA (document applies a law/article)
--   - PARTE_DE (clause is part of contract)
-- =============================================================================

-- Create the graph
SELECT create_graph('legal_graph');

-- Create node labels
SELECT create_vlabel('legal_graph', 'Ley');
SELECT create_vlabel('legal_graph', 'Articulo');
SELECT create_vlabel('legal_graph', 'Sentencia');
SELECT create_vlabel('legal_graph', 'Contrato');
SELECT create_vlabel('legal_graph', 'Clausula');
SELECT create_vlabel('legal_graph', 'Parte');
SELECT create_vlabel('legal_graph', 'Organismo');
SELECT create_vlabel('legal_graph', 'Documento');

-- Create edge labels
SELECT create_elabel('legal_graph', 'CONTIENE');
SELECT create_elabel('legal_graph', 'REFERENCIA');
SELECT create_elabel('legal_graph', 'INTERPRETA');
SELECT create_elabel('legal_graph', 'FIRMADO_POR');
SELECT create_elabel('legal_graph', 'REGULA');
SELECT create_elabel('legal_graph', 'DEROGA');
SELECT create_elabel('legal_graph', 'MODIFICA');
SELECT create_elabel('legal_graph', 'APLICA');
SELECT create_elabel('legal_graph', 'PARTE_DE');

-- Legal proxy nodes (synced from knowledge_graph_public, shared=true)
SELECT create_vlabel('legal_graph', 'LegalLaw');
SELECT create_elabel('legal_graph', 'MODIFIES');
SELECT create_elabel('legal_graph', 'DEROGATES');
SELECT create_elabel('legal_graph', 'REFERENCES');

-- Ontology proxy (for INSTANCE_OF edges to shared EntityType nodes)
SELECT create_vlabel('legal_graph', 'EntityType');

-- Memory Bank (MemoRAG-inspired document summaries for planner clue generation)
SELECT create_vlabel('legal_graph', 'DocumentMemory');

SELECT create_elabel('legal_graph', 'INSTANCE_OF');
SELECT create_elabel('legal_graph', 'EXTRACTED_FROM');
SELECT create_elabel('legal_graph', 'HAS_MEMORY');

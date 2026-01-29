-- =============================================================================
-- Medical Sector Graph Schema for Apache AGE
-- =============================================================================
-- Creates the medical_graph with node labels and edge types for
-- healthcare document management.
--
-- Node types:
--   - Paciente (patient — anonymized reference)
--   - HistoriaClinica (clinical record)
--   - Diagnostico (diagnosis with CIE-10 code)
--   - Procedimiento (medical procedure)
--   - Farmaco (medication/drug)
--   - Profesional (healthcare professional)
--   - Centro (healthcare facility)
--   - Documento (indexed document reference)
--
-- Edge types:
--   - TIENE_HISTORIA (patient has clinical record)
--   - DIAGNOSTICADO (record contains diagnosis)
--   - PRESCRITO (diagnosis leads to prescription)
--   - REALIZADO_POR (procedure performed by professional)
--   - TRATADO_CON (diagnosis treated with medication)
--   - DERIVADO_A (patient referred to facility/professional)
--   - ADJUNTO (document attached to record)
--   - CONTRAINDICADO (drug contraindicated with another)
-- =============================================================================

-- Create the graph
SELECT create_graph('medical_graph');

-- Create node labels
SELECT create_vlabel('medical_graph', 'Paciente');
SELECT create_vlabel('medical_graph', 'HistoriaClinica');
SELECT create_vlabel('medical_graph', 'Diagnostico');
SELECT create_vlabel('medical_graph', 'Procedimiento');
SELECT create_vlabel('medical_graph', 'Farmaco');
SELECT create_vlabel('medical_graph', 'Profesional');
SELECT create_vlabel('medical_graph', 'Centro');
SELECT create_vlabel('medical_graph', 'Documento');

-- Create edge labels
SELECT create_elabel('medical_graph', 'TIENE_HISTORIA');
SELECT create_elabel('medical_graph', 'DIAGNOSTICADO');
SELECT create_elabel('medical_graph', 'PRESCRITO');
SELECT create_elabel('medical_graph', 'REALIZADO_POR');
SELECT create_elabel('medical_graph', 'TRATADO_CON');
SELECT create_elabel('medical_graph', 'DERIVADO_A');
SELECT create_elabel('medical_graph', 'ADJUNTO');
SELECT create_elabel('medical_graph', 'CONTRAINDICADO');

-- =============================================================================
-- Business Ontology Graph Schema for Apache AGE
-- =============================================================================
-- Shared ontology graph that defines enterprise entity types and valid
-- relationships across all sectors and tenants.
--
-- This graph is NOT tenant-specific. It provides the "type system" that
-- tenant sector graphs reference via INSTANCE_OF edges.
--
-- Node types:
--   - EntityType    (document/entity/process type definition)
--   - RelationType  (valid relationship definition between entity types)
--
-- EntityType properties:
--   - name          (unique key, snake_case, e.g. "factura", "contrato")
--   - display_name  (human-readable, e.g. "Factura", "Contrato de Servicios")
--   - category      ("document", "entity", "process")
--   - parent        (parent type name for hierarchy, null = root)
--   - sector        (null = universal, or "legal"/"medical"/"documental")
--   - description   (brief description for LLM context)
--
-- RelationType properties:
--   - name          (edge label, e.g. "CREATED_BY", "SIGNED_BY")
--   - display_name  (human-readable)
--   - source_type   (EntityType name of the source node)
--   - target_type   (EntityType name of the target node)
--   - sector        (null = universal, or specific sector)
--
-- Design principles:
--   1. EntityType.name matches semantic_type_classifier output (1:1 mapping)
--   2. Hierarchy via parent property (not edges) for flat, fast lookups
--   3. No tenant_id — this is a shared reference graph
--   4. Sector-specific types coexist with universal types
--   5. RelationType defines the "schema" — what edges are valid
-- =============================================================================

-- Create the graph
SELECT create_graph('business_ontology');

-- Node labels
SELECT create_vlabel('business_ontology', 'EntityType');
SELECT create_vlabel('business_ontology', 'RelationType');

-- =============================================================================
-- SEED DATA: Document Type Hierarchy
-- =============================================================================
-- Root document types (abstract — not directly assigned to documents)
-- Category: "document"

-- Root
SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'document',
        display_name: 'Documento',
        category: 'document',
        parent: NULL,
        sector: NULL,
        description: 'Tipo raiz para todos los documentos empresariales'
    })
$$) as (v agtype);

-- Level 1: Abstract groupings
SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'financial_document',
        display_name: 'Documento Financiero',
        category: 'document',
        parent: 'document',
        sector: NULL,
        description: 'Documentos de naturaleza economica o contable'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'legal_document',
        display_name: 'Documento Legal',
        category: 'document',
        parent: 'document',
        sector: NULL,
        description: 'Documentos de naturaleza juridica o contractual'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'administrative_document',
        display_name: 'Documento Administrativo',
        category: 'document',
        parent: 'document',
        sector: NULL,
        description: 'Documentos de gestion interna y tramitacion'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'medical_document',
        display_name: 'Documento Clinico',
        category: 'document',
        parent: 'document',
        sector: 'medical',
        description: 'Documentos de ambito sanitario y asistencial'
    })
$$) as (v agtype);

-- =============================================================================
-- Level 2: Concrete document types (match semantic_type_classifier output)
-- =============================================================================

-- Financial documents
SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'factura',
        display_name: 'Factura',
        category: 'document',
        parent: 'financial_document',
        sector: NULL,
        description: 'Factura comercial con emisor, receptor, importe, IVA y fecha'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'nomina',
        display_name: 'Nomina',
        category: 'document',
        parent: 'financial_document',
        sector: NULL,
        description: 'Recibo de salario con retribuciones, deducciones e IRPF'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'presupuesto',
        display_name: 'Presupuesto',
        category: 'document',
        parent: 'financial_document',
        sector: NULL,
        description: 'Presupuesto economico con partidas de gasto e ingresos'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'albaran',
        display_name: 'Albaran',
        category: 'document',
        parent: 'financial_document',
        sector: NULL,
        description: 'Albaran de entrega con detalle de mercancias y cantidades'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'pedido',
        display_name: 'Pedido',
        category: 'document',
        parent: 'financial_document',
        sector: NULL,
        description: 'Orden de compra con productos, precios y condiciones'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'recibo',
        display_name: 'Recibo',
        category: 'document',
        parent: 'financial_document',
        sector: NULL,
        description: 'Justificante de pago con importe, concepto y fecha'
    })
$$) as (v agtype);

-- Legal documents
SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'contrato',
        display_name: 'Contrato',
        category: 'document',
        parent: 'legal_document',
        sector: NULL,
        description: 'Contrato legal con clausulas, obligaciones y firma'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'escritura',
        display_name: 'Escritura',
        category: 'document',
        parent: 'legal_document',
        sector: NULL,
        description: 'Escritura notarial de compraventa, constitucion o hipoteca'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'demanda',
        display_name: 'Demanda',
        category: 'document',
        parent: 'legal_document',
        sector: 'legal',
        description: 'Demanda judicial con hechos, fundamentos y peticiones'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'sentencia',
        display_name: 'Sentencia',
        category: 'document',
        parent: 'legal_document',
        sector: 'legal',
        description: 'Sentencia judicial con antecedentes, fundamentos y fallo'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'recurso',
        display_name: 'Recurso',
        category: 'document',
        parent: 'legal_document',
        sector: 'legal',
        description: 'Recurso de apelacion o casacion contra resolucion judicial'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'convenio',
        display_name: 'Convenio',
        category: 'document',
        parent: 'legal_document',
        sector: NULL,
        description: 'Convenio colectivo o acuerdo marco entre organizaciones'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'estatuto',
        display_name: 'Estatuto',
        category: 'document',
        parent: 'legal_document',
        sector: NULL,
        description: 'Estatutos sociales con normas de funcionamiento y gobierno'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'reglamento',
        display_name: 'Reglamento',
        category: 'document',
        parent: 'legal_document',
        sector: NULL,
        description: 'Reglamento interno con normas de obligado cumplimiento'
    })
$$) as (v agtype);

-- Administrative documents
SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'informe',
        display_name: 'Informe',
        category: 'document',
        parent: 'administrative_document',
        sector: NULL,
        description: 'Informe tecnico o de gestion con analisis y conclusiones'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'expediente',
        display_name: 'Expediente',
        category: 'document',
        parent: 'administrative_document',
        sector: NULL,
        description: 'Expediente administrativo con documentacion de un caso'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'acta',
        display_name: 'Acta',
        category: 'document',
        parent: 'administrative_document',
        sector: NULL,
        description: 'Acta de reunion con asistentes, acuerdos y firma'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'certificado',
        display_name: 'Certificado',
        category: 'document',
        parent: 'administrative_document',
        sector: NULL,
        description: 'Certificado oficial que acredita un hecho o cualificacion'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'circular',
        display_name: 'Circular',
        category: 'document',
        parent: 'administrative_document',
        sector: NULL,
        description: 'Circular informativa o normativa interna'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'propuesta',
        display_name: 'Propuesta',
        category: 'document',
        parent: 'administrative_document',
        sector: NULL,
        description: 'Propuesta comercial o tecnica con alcance y presupuesto'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'memoria',
        display_name: 'Memoria',
        category: 'document',
        parent: 'administrative_document',
        sector: NULL,
        description: 'Memoria anual con resumen de gestion y resultados'
    })
$$) as (v agtype);

-- =============================================================================
-- SEED DATA: Entity Types
-- =============================================================================
-- Category: "entity"

-- Root entities
SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'person',
        display_name: 'Persona',
        category: 'entity',
        parent: NULL,
        sector: NULL,
        description: 'Persona fisica identificable'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'organization',
        display_name: 'Organizacion',
        category: 'entity',
        parent: NULL,
        sector: NULL,
        description: 'Entidad juridica u organizativa'
    })
$$) as (v agtype);

-- Person subtypes
SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'employee',
        display_name: 'Empleado',
        category: 'entity',
        parent: 'person',
        sector: NULL,
        description: 'Trabajador de la organizacion'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'client',
        display_name: 'Cliente',
        category: 'entity',
        parent: 'person',
        sector: NULL,
        description: 'Cliente o beneficiario de servicios'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'supplier',
        display_name: 'Proveedor',
        category: 'entity',
        parent: 'person',
        sector: NULL,
        description: 'Proveedor de bienes o servicios'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'professional',
        display_name: 'Profesional Sanitario',
        category: 'entity',
        parent: 'person',
        sector: 'medical',
        description: 'Profesional del ambito sanitario (medico, enfermero)'
    })
$$) as (v agtype);

-- Organization subtypes
SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'company',
        display_name: 'Empresa',
        category: 'entity',
        parent: 'organization',
        sector: NULL,
        description: 'Sociedad mercantil o empresa'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'department',
        display_name: 'Departamento',
        category: 'entity',
        parent: 'organization',
        sector: NULL,
        description: 'Unidad organizativa interna'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'regulatory_body',
        display_name: 'Organismo Regulador',
        category: 'entity',
        parent: 'organization',
        sector: 'legal',
        description: 'Organismo publico regulador o supervisor'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'healthcare_facility',
        display_name: 'Centro Sanitario',
        category: 'entity',
        parent: 'organization',
        sector: 'medical',
        description: 'Hospital, clinica o centro de salud'
    })
$$) as (v agtype);

-- =============================================================================
-- SEED DATA: Process Types
-- =============================================================================
-- Category: "process"

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'process',
        display_name: 'Proceso',
        category: 'process',
        parent: NULL,
        sector: NULL,
        description: 'Proceso o flujo de trabajo empresarial'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'workflow',
        display_name: 'Flujo de Trabajo',
        category: 'process',
        parent: 'process',
        sector: NULL,
        description: 'Flujo de trabajo con etapas y aprobaciones'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'legal_proceeding',
        display_name: 'Procedimiento Legal',
        category: 'process',
        parent: 'process',
        sector: 'legal',
        description: 'Procedimiento judicial o administrativo'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:EntityType {
        name: 'medical_procedure',
        display_name: 'Procedimiento Medico',
        category: 'process',
        parent: 'process',
        sector: 'medical',
        description: 'Procedimiento clinico o asistencial'
    })
$$) as (v agtype);

-- =============================================================================
-- SEED DATA: Relation Types (valid edges between entity types)
-- =============================================================================

-- Document-Person relations
SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'CREATED_BY',
        display_name: 'Creado por',
        source_type: 'document',
        target_type: 'person',
        sector: NULL,
        description: 'Documento creado o redactado por una persona'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'SIGNED_BY',
        display_name: 'Firmado por',
        source_type: 'document',
        target_type: 'person',
        sector: NULL,
        description: 'Documento firmado por una persona'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'ASSOCIATED_WITH',
        display_name: 'Asociado a',
        source_type: 'document',
        target_type: 'person',
        sector: NULL,
        description: 'Documento asociado a una persona (por carpeta o contexto)'
    })
$$) as (v agtype);

-- Document-Organization relations
SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'BELONGS_TO',
        display_name: 'Pertenece a',
        source_type: 'document',
        target_type: 'organization',
        sector: NULL,
        description: 'Documento que pertenece a una organizacion'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'ISSUED_BY',
        display_name: 'Emitido por',
        source_type: 'financial_document',
        target_type: 'organization',
        sector: NULL,
        description: 'Documento financiero emitido por una entidad'
    })
$$) as (v agtype);

-- Document-Document relations
SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'REFERENCES',
        display_name: 'Referencia',
        source_type: 'document',
        target_type: 'document',
        sector: NULL,
        description: 'Documento que referencia otro documento'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'VERSION_OF',
        display_name: 'Version de',
        source_type: 'document',
        target_type: 'document',
        sector: NULL,
        description: 'Documento que es version de otro'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'SUPERSEDES',
        display_name: 'Sustituye',
        source_type: 'document',
        target_type: 'document',
        sector: NULL,
        description: 'Documento que sustituye o reemplaza otro'
    })
$$) as (v agtype);

-- Document-Process relations
SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'PART_OF_PROCESS',
        display_name: 'Parte de proceso',
        source_type: 'document',
        target_type: 'process',
        sector: NULL,
        description: 'Documento que forma parte de un proceso o flujo'
    })
$$) as (v agtype);

-- Legal-specific relations
SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'GOVERNED_BY',
        display_name: 'Regulado por',
        source_type: 'document',
        target_type: 'legal_document',
        sector: 'legal',
        description: 'Documento regulado por una norma juridica'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'MODIFIES',
        display_name: 'Modifica',
        source_type: 'legal_document',
        target_type: 'legal_document',
        sector: 'legal',
        description: 'Norma que modifica otra norma'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'DEROGATES',
        display_name: 'Deroga',
        source_type: 'legal_document',
        target_type: 'legal_document',
        sector: 'legal',
        description: 'Norma que deroga otra norma'
    })
$$) as (v agtype);

-- Person-Organization relations
SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'WORKS_FOR',
        display_name: 'Trabaja en',
        source_type: 'person',
        target_type: 'organization',
        sector: NULL,
        description: 'Persona que trabaja para una organizacion'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'MANAGES',
        display_name: 'Gestiona',
        source_type: 'person',
        target_type: 'department',
        sector: NULL,
        description: 'Persona que gestiona un departamento'
    })
$$) as (v agtype);

-- Medical-specific relations
SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'TREATED_BY',
        display_name: 'Tratado por',
        source_type: 'person',
        target_type: 'professional',
        sector: 'medical',
        description: 'Paciente atendido por un profesional sanitario'
    })
$$) as (v agtype);

SELECT * FROM cypher('business_ontology', $$
    CREATE (:RelationType {
        name: 'ATTENDED_AT',
        display_name: 'Atendido en',
        source_type: 'person',
        target_type: 'healthcare_facility',
        sector: 'medical',
        description: 'Paciente atendido en un centro sanitario'
    })
$$) as (v agtype);

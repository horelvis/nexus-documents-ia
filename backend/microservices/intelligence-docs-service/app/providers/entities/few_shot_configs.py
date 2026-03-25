"""
Few-shot extraction configs for LangExtract.

Each config has a prompt describing what to extract and example ExampleData
objects that teach the LLM the expected output format via few-shot learning.
"""
import langextract as lx

EXTRACTION_CONFIGS: dict[str, dict] = {
    "contract": {
        "prompt": """Extract the following information from this contract:
                - Parties involved (names and roles)
                - Contract type and purpose
                - Key dates (effective date, expiration, deadlines)
                - Payment terms and amounts
                - Obligations and deliverables
                - Termination clauses
                - Governing law and jurisdiction
                - Signatures and execution details

                Use exact text from the document. Map each extraction to its source.""",
        "examples": [
            lx.data.ExampleData(
                text="This Service Agreement ('Agreement') is entered into as of January 1, 2025, between TechCorp Inc. ('Service Provider') and ClientCo Ltd. ('Client').",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="party",
                        extraction_text="TechCorp Inc.",
                        attributes={"role": "Service Provider", "type": "company"},
                    ),
                    lx.data.Extraction(
                        extraction_class="party",
                        extraction_text="ClientCo Ltd.",
                        attributes={"role": "Client", "type": "company"},
                    ),
                    lx.data.Extraction(
                        extraction_class="contract_type",
                        extraction_text="Service Agreement",
                        attributes={"category": "services"},
                    ),
                    lx.data.Extraction(
                        extraction_class="date",
                        extraction_text="January 1, 2025",
                        attributes={"type": "effective_date"},
                    ),
                ],
            )
        ],
    },
    "invoice": {
        "prompt": """Extract the following information from this invoice:
                - Invoice number and date
                - Vendor/seller information
                - Customer/buyer information
                - Line items with descriptions and amounts
                - Subtotal, tax, and total amounts
                - Payment terms and due date
                - Bank/payment details

                Extract exact amounts and details as they appear.""",
        "examples": [
            lx.data.ExampleData(
                text="Invoice #2025-001\nDate: March 15, 2025\nBill To: ABC Company\nTotal: $5,000.00\nDue: April 15, 2025",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="invoice_number",
                        extraction_text="2025-001",
                        attributes={"format": "year-sequential"},
                    ),
                    lx.data.Extraction(
                        extraction_class="date",
                        extraction_text="March 15, 2025",
                        attributes={"type": "invoice_date"},
                    ),
                    lx.data.Extraction(
                        extraction_class="customer",
                        extraction_text="ABC Company",
                        attributes={"role": "buyer"},
                    ),
                    lx.data.Extraction(
                        extraction_class="amount",
                        extraction_text="$5,000.00",
                        attributes={"type": "total", "currency": "USD"},
                    ),
                    lx.data.Extraction(
                        extraction_class="date",
                        extraction_text="April 15, 2025",
                        attributes={"type": "due_date"},
                    ),
                ],
            )
        ],
    },
    "report": {
        "prompt": """Extract the following information from this report:
                - Report title and type
                - Author(s) and organization
                - Date of publication
                - Executive summary or abstract
                - Key findings and conclusions
                - Recommendations
                - Data points and statistics
                - References to other documents

                Maintain the context and relationships between extracted elements.""",
        "examples": [
            lx.data.ExampleData(
                text="Annual Financial Report 2025\nPrepared by: Finance Department\nKey Finding: Revenue increased by 25% year-over-year",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="title",
                        extraction_text="Annual Financial Report 2025",
                        attributes={"type": "financial", "period": "annual"},
                    ),
                    lx.data.Extraction(
                        extraction_class="author",
                        extraction_text="Finance Department",
                        attributes={"type": "department"},
                    ),
                    lx.data.Extraction(
                        extraction_class="finding",
                        extraction_text="Revenue increased by 25% year-over-year",
                        attributes={"category": "financial", "metric": "revenue", "change": "+25%"},
                    ),
                ],
            )
        ],
    },
    "nomina": {
        "prompt": """Extrae informacion estructurada de esta nomina laboral:
                - Trabajador (nombre completo, NIF, numero seguridad social)
                - Empresa (nombre, CIF)
                - Periodo de liquidacion (mes/ano)
                - Devengos (salario base, complementos, pagas extra, horas extra)
                - Deducciones (IRPF, Seguridad Social, anticipos)
                - Liquido total a percibir
                - Datos bancarios (IBAN)

                Extrae cantidades numericas exactas y fechas tal como aparecen.""",
        "examples": [
            lx.data.ExampleData(
                text="Nomina - Periodo: Enero 2025\nTrabajador: Juan Perez Lopez, NIF: 12345678A\nSalario Base: 1.800,00 EUR\nIRPF: -270,00 EUR\nLiquido a Percibir: 1.530,00 EUR",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="trabajador",
                        extraction_text="Juan Perez Lopez",
                        attributes={"nif": "12345678A", "tipo": "empleado"},
                    ),
                    lx.data.Extraction(
                        extraction_class="periodo",
                        extraction_text="Enero 2025",
                        attributes={"tipo": "mensual"},
                    ),
                    lx.data.Extraction(
                        extraction_class="devengo",
                        extraction_text="1.800,00 EUR",
                        attributes={"concepto": "salario_base"},
                    ),
                    lx.data.Extraction(
                        extraction_class="deduccion",
                        extraction_text="-270,00 EUR",
                        attributes={"concepto": "irpf", "tipo": "retencion"},
                    ),
                    lx.data.Extraction(
                        extraction_class="liquido",
                        extraction_text="1.530,00 EUR",
                        attributes={"tipo": "total_percibir"},
                    ),
                ],
            )
        ],
    },
    "modelo_111": {
        "prompt": """Extrae informacion del Modelo 111 (Retenciones IRPF trimestral):
                - NIF y nombre del declarante
                - Periodo de declaracion (trimestre y ano)
                - Numero de perceptores
                - Retenciones practicadas
                - Ingresos a cuenta
                - Resultado a ingresar o devolver
                - Fecha de presentacion

                Manten formato numerico exacto y estructura fiscal.""",
        "examples": [
            lx.data.ExampleData(
                text="Modelo 111 - 1T 2025\nDeclarante: TechCorp SL, CIF: B12345678\nPerceptores: 15\nRetenciones: 4.500,00 EUR\nResultado: 4.500,00 EUR a ingresar",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="declarante",
                        extraction_text="TechCorp SL",
                        attributes={"cif": "B12345678", "tipo": "empresa"},
                    ),
                    lx.data.Extraction(
                        extraction_class="periodo",
                        extraction_text="1T 2025",
                        attributes={"tipo": "trimestral", "trimestre": "1"},
                    ),
                    lx.data.Extraction(
                        extraction_class="perceptores",
                        extraction_text="15",
                        attributes={"tipo": "numero"},
                    ),
                    lx.data.Extraction(
                        extraction_class="retencion",
                        extraction_text="4.500,00 EUR",
                        attributes={"concepto": "irpf_practicado"},
                    ),
                    lx.data.Extraction(
                        extraction_class="resultado",
                        extraction_text="4.500,00 EUR",
                        attributes={"tipo": "a_ingresar"},
                    ),
                ],
            )
        ],
    },
    "modelo_190": {
        "prompt": """Extrae informacion del Modelo 190 (Resumen anual IRPF):
                - NIF y nombre del declarante
                - Ejercicio fiscal (ano)
                - Percepciones totales por empleado
                - Retenciones totales practicadas
                - Numero total de perceptores
                - Resumen por conceptos

                Preserva estructura de datos anuales y totalizaciones.""",
        "examples": [
            lx.data.ExampleData(
                text="Modelo 190 - Ejercicio 2024\nDeclarante: GlobalCorp SA, CIF: A87654321\nTotal Perceptores: 120\nTotal Percepciones: 2.400.000,00 EUR\nTotal Retenciones: 360.000,00 EUR",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="declarante",
                        extraction_text="GlobalCorp SA",
                        attributes={"cif": "A87654321"},
                    ),
                    lx.data.Extraction(
                        extraction_class="ejercicio",
                        extraction_text="2024",
                        attributes={"tipo": "anual"},
                    ),
                    lx.data.Extraction(
                        extraction_class="perceptores",
                        extraction_text="120",
                        attributes={"tipo": "total"},
                    ),
                    lx.data.Extraction(
                        extraction_class="percepciones",
                        extraction_text="2.400.000,00 EUR",
                        attributes={"tipo": "total_anual"},
                    ),
                    lx.data.Extraction(
                        extraction_class="retenciones",
                        extraction_text="360.000,00 EUR",
                        attributes={"tipo": "total_anual"},
                    ),
                ],
            )
        ],
    },
    "modelo_303": {
        "prompt": """Extrae informacion del Modelo 303 (IVA trimestral):
                - NIF y nombre del declarante
                - Periodo (trimestre y ano)
                - IVA devengado (base imponible y cuota)
                - IVA deducible (base imponible y cuota)
                - Resultado (a ingresar o compensar)

                Manten separacion entre bases imponibles y cuotas.""",
        "examples": [
            lx.data.ExampleData(
                text="Modelo 303 - 4T 2024\nDeclarante: Services Ltd, CIF: B99887766\nIVA Devengado: Base 50.000,00 EUR - Cuota 10.500,00 EUR\nIVA Deducible: Base 30.000,00 EUR - Cuota 6.300,00 EUR\nResultado: 4.200,00 EUR a ingresar",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="declarante",
                        extraction_text="Services Ltd",
                        attributes={"cif": "B99887766"},
                    ),
                    lx.data.Extraction(
                        extraction_class="periodo",
                        extraction_text="4T 2024",
                        attributes={"trimestre": "4", "ano": "2024"},
                    ),
                    lx.data.Extraction(
                        extraction_class="iva_devengado",
                        extraction_text="10.500,00 EUR",
                        attributes={"base": "50.000,00 EUR", "tipo": "cuota"},
                    ),
                    lx.data.Extraction(
                        extraction_class="iva_deducible",
                        extraction_text="6.300,00 EUR",
                        attributes={"base": "30.000,00 EUR", "tipo": "cuota"},
                    ),
                    lx.data.Extraction(
                        extraction_class="resultado",
                        extraction_text="4.200,00 EUR",
                        attributes={"tipo": "a_ingresar"},
                    ),
                ],
            )
        ],
    },
    "certificado": {
        "prompt": """Extrae informacion de este certificado laboral:
                - Emisor (empresa/organizacion)
                - Trabajador o beneficiario
                - Tipo de certificado
                - Fecha de emision
                - Periodo al que refiere
                - Datos certificados (antiguedad, salarios, etc.)
                - Firma y sello

                Preserva datos oficiales y declaraciones exactas.""",
        "examples": [
            lx.data.ExampleData(
                text="CERTIFICADO DE EMPRESA\nCertificamos que D. Carlos Martinez ha prestado servicios desde 01/01/2020 hasta 31/12/2024.\nPuesto: Ingeniero Senior\nMadrid, 15 de enero de 2025",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="trabajador",
                        extraction_text="Carlos Martinez",
                        attributes={"tratamiento": "D."},
                    ),
                    lx.data.Extraction(
                        extraction_class="periodo",
                        extraction_text="01/01/2020 hasta 31/12/2024",
                        attributes={"tipo": "antiguedad"},
                    ),
                    lx.data.Extraction(
                        extraction_class="puesto",
                        extraction_text="Ingeniero Senior",
                        attributes={"tipo": "cargo"},
                    ),
                    lx.data.Extraction(
                        extraction_class="fecha_emision",
                        extraction_text="15 de enero de 2025",
                        attributes={"lugar": "Madrid"},
                    ),
                ],
            )
        ],
    },
    "comunicacion_itss": {
        "prompt": """Extrae informacion de comunicacion de Inspeccion de Trabajo:
                - Organo emisor (Inspeccion Provincial, etc.)
                - Empresa destinataria
                - Numero de expediente
                - Tipo de comunicacion (requerimiento, acta, sancion)
                - Fecha de comunicacion
                - Plazo de respuesta
                - Objeto o motivo

                Identifica datos administrativos y plazos legales.""",
        "examples": [
            lx.data.ExampleData(
                text="INSPECCION DE TRABAJO Y SEGURIDAD SOCIAL\nExpediente: ITSS-2025-00123\nEmpresa: Industrial Corp SL\nRequerimiento de documentacion laboral\nPlazo: 10 dias habiles desde notificacion",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="expediente",
                        extraction_text="ITSS-2025-00123",
                        attributes={"tipo": "numero_expediente"},
                    ),
                    lx.data.Extraction(
                        extraction_class="empresa",
                        extraction_text="Industrial Corp SL",
                        attributes={"tipo": "destinatario"},
                    ),
                    lx.data.Extraction(
                        extraction_class="tipo_comunicacion",
                        extraction_text="Requerimiento de documentacion laboral",
                        attributes={"categoria": "requerimiento"},
                    ),
                    lx.data.Extraction(
                        extraction_class="plazo",
                        extraction_text="10 dias habiles",
                        attributes={"tipo": "respuesta"},
                    ),
                ],
            )
        ],
    },
    "general": {
        "prompt": """Extrae SOLO las siguientes entidades clave del documento:

PERSONAS:
- Nombres de personas (trabajadores, clientes, firmantes, representantes)
- Cargos o roles de las personas

EMPRESAS/ORGANIZACIONES:
- Nombres de empresas, sociedades, organizaciones
- CIF/NIF de empresas
- Direcciones de empresas

INFORMACION FINANCIERA:
- Importes monetarios (salarios, totales, deducciones, cuotas)
- Numeros de cuenta bancaria (IBAN)

FECHAS Y PERIODOS:
- Fechas relevantes (emision, vencimiento, periodo)
- Periodos (trimestres, meses, ejercicios)

IDENTIFICADORES:
- Numeros de factura, expediente, contrato
- NIF/CIF de personas

NO extraigas: descripciones genericas, temas, conceptos abstractos, ubicaciones genericas.
Usa el texto EXACTO del documento.""",
        "examples": [
            lx.data.ExampleData(
                text="Contrato entre TechCorp SL (CIF: B12345678) representada por Juan Garcia Lopez y el trabajador Maria Perez Ruiz (NIF: 12345678A). Salario: 30.000 EUR anuales. Fecha inicio: 01/02/2025.",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="empresa",
                        extraction_text="TechCorp SL",
                        attributes={"cif": "B12345678", "rol": "empleador"},
                    ),
                    lx.data.Extraction(
                        extraction_class="person",
                        extraction_text="Juan Garcia Lopez",
                        attributes={"rol": "representante legal"},
                    ),
                    lx.data.Extraction(
                        extraction_class="trabajador",
                        extraction_text="Maria Perez Ruiz",
                        attributes={"nif": "12345678A", "rol": "empleado"},
                    ),
                    lx.data.Extraction(
                        extraction_class="amount",
                        extraction_text="30.000 EUR",
                        attributes={"tipo": "salario", "periodicidad": "anual"},
                    ),
                    lx.data.Extraction(
                        extraction_class="fecha",
                        extraction_text="01/02/2025",
                        attributes={"tipo": "fecha_inicio"},
                    ),
                ],
            ),
            lx.data.ExampleData(
                text="Factura No 2025-0042. Cliente: Servicios Digitales SA. Total: 1.210,00 EUR (IVA incluido). Vencimiento: 15/03/2025. IBAN: ES91 2100 0418 4502 0005 1332",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="invoice_number",
                        extraction_text="2025-0042",
                        attributes={"tipo": "numero_factura"},
                    ),
                    lx.data.Extraction(
                        extraction_class="cliente",
                        extraction_text="Servicios Digitales SA",
                        attributes={"rol": "comprador"},
                    ),
                    lx.data.Extraction(
                        extraction_class="amount",
                        extraction_text="1.210,00 EUR",
                        attributes={"tipo": "total", "iva_incluido": "true"},
                    ),
                    lx.data.Extraction(
                        extraction_class="fecha",
                        extraction_text="15/03/2025",
                        attributes={"tipo": "vencimiento"},
                    ),
                    lx.data.Extraction(
                        extraction_class="iban",
                        extraction_text="ES91 2100 0418 4502 0005 1332",
                        attributes={"tipo": "cuenta_bancaria"},
                    ),
                ],
            ),
        ],
    },
}

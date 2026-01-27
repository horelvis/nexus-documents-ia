"""
Generic training datasets for domain experts.

These datasets provide baseline training examples for
common domains. They can be supplemented with tenant-specific
data or synthetic examples.
"""

# Legal domain examples
GENERIC_LEGAL_EXAMPLES = [
    {
        "input": "¿Cuál es el plazo de prescripción para reclamar una deuda?",
        "output": "El plazo de prescripción para reclamar deudas en España es de 5 años según el artículo 1964 del Código Civil, modificado por la Ley 42/2015. Este plazo comienza a contar desde que la obligación pudo exigirse. Para deudas tributarias, el plazo es de 4 años."
    },
    {
        "input": "¿Qué requisitos tiene el RGPD para el consentimiento?",
        "output": "Según el RGPD (Reglamento General de Protección de Datos), el consentimiento debe ser: 1) Libre: sin coacción ni condicionantes. 2) Específico: para finalidades concretas. 3) Informado: el interesado debe conocer la identidad del responsable y los fines. 4) Inequívoco: mediante una declaración o acción afirmativa clara. 5) Verificable: el responsable debe poder demostrar que se obtuvo."
    },
    {
        "input": "¿Qué es la responsabilidad civil contractual?",
        "output": "La responsabilidad civil contractual surge del incumplimiento de obligaciones derivadas de un contrato. Según los artículos 1101-1108 del Código Civil, el deudor que incumple está obligado a indemnizar los daños y perjuicios causados. Requiere: 1) Existencia de contrato válido. 2) Incumplimiento o cumplimiento defectuoso. 3) Daño real y cuantificable. 4) Relación de causalidad entre incumplimiento y daño."
    },
    {
        "input": "¿Cuándo es nulo un contrato?",
        "output": "Un contrato es nulo de pleno derecho cuando: 1) Falta consentimiento, objeto o causa (art. 1261 CC). 2) El objeto es ilícito o imposible. 3) La causa es ilícita o contraria a la moral. 4) Se incumplen requisitos formales esenciales. 5) Es contrario a normas imperativas o prohibitivas. La nulidad puede ser apreciada de oficio y no prescribe. El contrato nulo no produce efectos jurídicos desde su origen."
    },
    {
        "input": "¿Qué derechos tiene un trabajador despedido improcedentemente?",
        "output": "Ante un despido improcedente, el empresario puede optar entre: 1) Readmisión del trabajador con abono de salarios de tramitación. 2) Indemnización de 33 días por año trabajado (máximo 24 mensualidades) para contratos posteriores al 12/02/2012, o 45 días por año (máximo 42 mensualidades) para el período anterior. El trabajador tiene 20 días hábiles para impugnar el despido ante el Juzgado de lo Social."
    },
]

# Contract domain examples
GENERIC_CONTRACT_EXAMPLES = [
    {
        "input": "¿Qué elementos esenciales debe tener un contrato?",
        "output": "Según el artículo 1261 del Código Civil, todo contrato requiere tres elementos esenciales: 1) Consentimiento de los contratantes: voluntad libre y consciente de obligarse. 2) Objeto cierto: materia del contrato, que debe ser lícito, posible y determinado. 3) Causa de la obligación: razón o finalidad del contrato. Sin estos elementos, el contrato es nulo de pleno derecho."
    },
    {
        "input": "¿Cómo se calcula la indemnización por finalización de contrato temporal?",
        "output": "La indemnización por fin de contrato temporal es de 12 días de salario por año de servicio (desde 2015, antes era escalonada). Se calcula: (Salario diario × 12 × años trabajados) / 365. No aplica a contratos de interinidad, formativos ni de relevo. Los días trabajados inferiores a un año se prorratean proporcionalmente."
    },
    {
        "input": "¿Qué cláusulas son abusivas en un contrato con consumidores?",
        "output": "Son cláusulas abusivas (Ley General de Defensa de Consumidores): 1) Las que limitan derechos del consumidor. 2) Las que exoneran de responsabilidad al empresario. 3) Las que imponen cargas desproporcionadas. 4) Las que establecen penalizaciones excesivas. 5) Las que permiten modificaciones unilaterales. 6) Las que imponen fueros distintos al del domicilio del consumidor. Estas cláusulas son nulas de pleno derecho."
    },
    {
        "input": "¿Cuál es el plazo máximo de un contrato de arrendamiento de vivienda?",
        "output": "Según la LAU reformada (2019): La duración mínima obligatoria es de 5 años (7 si el arrendador es persona jurídica). Prórrogas obligatorias anuales hasta alcanzar el mínimo. Prórroga tácita de 3 años adicionales si ninguna parte notifica con 4 meses (arrendador) o 2 meses (arrendatario) de antelación. No hay plazo máximo legal, pero el arrendatario puede desistir tras 6 meses con preaviso de 30 días."
    },
    {
        "input": "¿Qué diferencia hay entre contrato de obra y de servicios?",
        "output": "Contrato de Obra (arrendamiento de obra): 1) Se compromete un resultado concreto. 2) El riesgo es del contratista hasta la entrega. 3) Pago al finalizar la obra. 4) Ejemplo: construcción de edificio. Contrato de Servicios (arrendamiento de servicios): 1) Se compromete actividad/diligencia, no resultado. 2) El riesgo es del cliente. 3) Pago periódico o por tiempo. 4) Ejemplo: asesoría legal, consultoría."
    },
]

# Compliance domain examples
GENERIC_COMPLIANCE_EXAMPLES = [
    {
        "input": "¿Qué controles requiere la ISO 27001?",
        "output": "La ISO 27001 establece 114 controles en el Anexo A, organizados en 14 dominios: 1) Políticas de seguridad. 2) Organización de la seguridad. 3) Seguridad de RRHH. 4) Gestión de activos. 5) Control de acceso. 6) Criptografía. 7) Seguridad física. 8) Seguridad operativa. 9) Seguridad de comunicaciones. 10) Adquisición y desarrollo de sistemas. 11) Relación con proveedores. 12) Gestión de incidentes. 13) Continuidad de negocio. 14) Cumplimiento legal."
    },
    {
        "input": "¿Cuáles son las obligaciones del DPO según el RGPD?",
        "output": "El Delegado de Protección de Datos (DPO) según el RGPD debe: 1) Informar y asesorar sobre obligaciones de protección de datos. 2) Supervisar el cumplimiento del RGPD. 3) Asesorar sobre evaluaciones de impacto. 4) Cooperar con la autoridad de control. 5) Actuar como punto de contacto con la AEPD. 6) Mantener independencia funcional. 7) Tener acceso a recursos necesarios. 8) Mantener secreto profesional."
    },
]

# Finance domain examples
GENERIC_FINANCE_EXAMPLES = [
    {
        "input": "¿Cuáles son los plazos de conservación de facturas?",
        "output": "Los plazos de conservación de facturas en España son: 1) Facturas emitidas y recibidas: 4 años (prescripción tributaria, art. 66 LGT). 2) A efectos mercantiles: 6 años (art. 30 Código de Comercio). 3) Para IVA: 4 años desde el último día de presentación de la declaración. Se recomienda conservar 6 años como mínimo. El formato puede ser electrónico si garantiza autenticidad e integridad."
    },
    {
        "input": "¿Qué requisitos debe cumplir una factura electrónica?",
        "output": "Una factura electrónica válida debe: 1) Garantizar autenticidad del origen. 2) Garantizar integridad del contenido. 3) Ser legible durante el período de conservación. 4) Incluir todos los datos obligatorios (NIF, fecha, concepto, base imponible, tipo IVA, cuota). 5) Usar formato estructurado (Facturae en sector público). 6) Firma electrónica reconocida o EDI con garantías equivalentes. 7) Conservarse en formato original."
    },
]

# HR domain examples
GENERIC_HR_EXAMPLES = [
    {
        "input": "¿Cuántos días de vacaciones corresponden por ley?",
        "output": "Según el artículo 38 del Estatuto de los Trabajadores, las vacaciones anuales mínimas son de 30 días naturales (o 22 días laborables). No son sustituibles por compensación económica excepto al finalizar la relación laboral. Se deben disfrutar dentro del año natural o período acordado. El empresario debe comunicar el calendario con 2 meses de antelación. Por convenio pueden ampliarse pero nunca reducirse."
    },
    {
        "input": "¿Qué permisos retribuidos tiene un trabajador?",
        "output": "El artículo 37.3 del ET establece permisos retribuidos por: 1) Matrimonio: 15 días. 2) Nacimiento de hijo: 16 semanas (ampliable). 3) Fallecimiento de familiar hasta 2º grado: 2-4 días. 4) Traslado de domicilio: 1 día. 5) Deber público inexcusable: tiempo necesario. 6) Funciones sindicales: según normativa. 7) Exámenes prenatales: tiempo necesario. 8) Lactancia: 1 hora diaria hasta 9 meses. Los convenios pueden mejorar estos mínimos."
    },
]


def get_domain_examples(domain: str) -> list:
    """Get generic examples for a domain."""
    examples_map = {
        "legal": GENERIC_LEGAL_EXAMPLES,
        "contract": GENERIC_CONTRACT_EXAMPLES,
        "compliance": GENERIC_COMPLIANCE_EXAMPLES,
        "finance": GENERIC_FINANCE_EXAMPLES,
        "hr": GENERIC_HR_EXAMPLES,
    }
    return examples_map.get(domain, [])

"""
Dataset de Entrenamiento para Experto Documental.

Este dataset cubre las áreas principales de gestión documental empresarial:
1. Tipos de documentos y características
2. Metadatos y clasificación
3. Ciclo de vida del documento
4. Políticas de retención
5. Flujos de trabajo (workflows)
6. Control de versiones
7. Permisos y acceso
8. Búsqueda y recuperación
9. Cumplimiento normativo
10. Digitalización y OCR
11. Gestión de expedientes administrativos (Ley 39/2015, ENI)

Total: ~50 ejemplos de alta calidad
"""

from typing import List, Dict

# =============================================================================
# 1. TIPOS DE DOCUMENTOS Y CARACTERÍSTICAS
# =============================================================================
DOCUMENT_TYPES_EXAMPLES: List[Dict[str, str]] = [
    {
        "input": "¿Qué tipos de documentos se pueden gestionar en el sistema?",
        "output": "El sistema gestiona múltiples tipos documentales:\n\n**Documentos Legales:**\n- Contratos (arrendamiento, servicios, compraventa)\n- Poderes notariales\n- Actas societarias\n- Escrituras\n\n**Documentos Financieros:**\n- Facturas (emitidas y recibidas)\n- Presupuestos y ofertas\n- Órdenes de compra\n- Albaranes\n- Estados financieros\n\n**Documentos de RRHH:**\n- Contratos laborales\n- Nóminas\n- Expedientes de personal\n- Evaluaciones de desempeño\n\n**Documentos Técnicos:**\n- Manuales y procedimientos\n- Especificaciones técnicas\n- Planos y diagramas\n- Informes técnicos\n\n**Correspondencia:**\n- Emails archivados\n- Cartas oficiales\n- Comunicaciones internas"
    },
    {
        "input": "¿Cuál es la diferencia entre un documento original y una copia?",
        "output": "La distinción es importante para validez legal:\n\n**Documento Original:**\n- Primera versión creada\n- Contiene firmas manuscritas o electrónicas válidas\n- Tiene plena validez legal\n- Se marca como 'original' en metadatos\n- Requiere custodia especial\n\n**Copia Simple:**\n- Reproducción del original\n- Sin firma o con firma escaneada\n- Validez limitada (solo informativa)\n- Se marca como 'copia'\n\n**Copia Compulsada:**\n- Copia certificada por autoridad competente\n- Tiene validez legal equivalente al original\n- Incluye sello de compulsa\n- Se registra fecha y autoridad que compulsa\n\n**Copia Electrónica Auténtica:**\n- Según Ley 39/2015\n- Firmada electrónicamente por funcionario\n- Mismo valor que el original"
    },
    {
        "input": "¿Qué es un expediente y cómo se estructura?",
        "output": "Un expediente es un conjunto ordenado de documentos relacionados con un asunto:\n\n**Estructura del Expediente:**\n```\nExpediente EXP-2024-00123\n├── Carátula (datos identificativos)\n├── Índice de documentos\n├── Documentos por orden cronológico\n│   ├── 001_Solicitud_inicial.pdf\n│   ├── 002_Informe_tecnico.pdf\n│   ├── 003_Resolucion.pdf\n│   └── ...\n└── Diligencias de cierre\n```\n\n**Metadatos del Expediente:**\n- Número identificador único\n- Fecha de apertura/cierre\n- Procedimiento asociado\n- Responsable/tramitador\n- Estado (abierto, en trámite, cerrado)\n- Clasificación archivística\n\n**Tipos de Expedientes:**\n- Administrativos\n- Judiciales\n- De personal\n- Comerciales\n- Técnicos"
    },
    {
        "input": "¿Qué formatos de archivo son aceptados para documentos?",
        "output": "Los formatos aceptados se clasifican por uso:\n\n**Formatos de Preservación (recomendados):**\n- PDF/A (ISO 19005): Formato de archivo a largo plazo\n- PDF/A-1b: Nivel básico de conformidad\n- PDF/A-2: Permite capas y transparencias\n- PDF/A-3: Permite archivos adjuntos\n\n**Formatos de Trabajo:**\n- PDF estándar\n- Microsoft Office (.docx, .xlsx, .pptx)\n- OpenDocument (.odt, .ods, .odp)\n- Imágenes (.jpg, .png, .tiff)\n\n**Formatos Especiales:**\n- XML estructurado (facturas electrónicas)\n- CAD (.dwg, .dxf) para planos\n- Emails (.eml, .msg)\n\n**No Recomendados:**\n- Formatos propietarios obsoletos\n- Ejecutables (.exe, .bat)\n- Formatos sin soporte a largo plazo\n\n**Conversión Automática:**\nEl sistema puede convertir automáticamente documentos Office a PDF/A para archivo definitivo."
    },
    {
        "input": "¿Cómo se clasifican los documentos por su nivel de confidencialidad?",
        "output": "El sistema implementa niveles de clasificación estándar:\n\n**Público:**\n- Acceso sin restricciones\n- Puede publicarse externamente\n- Ejemplo: Catálogos, información corporativa general\n\n**Interno:**\n- Solo empleados de la organización\n- No divulgable externamente\n- Ejemplo: Procedimientos internos, comunicados\n\n**Confidencial:**\n- Acceso restringido a roles específicos\n- Requiere justificación de acceso\n- Ejemplo: Datos financieros, estrategia comercial\n\n**Reservado/Secreto:**\n- Máxima restricción\n- Acceso nominativo (personas concretas)\n- Registro de todos los accesos\n- Ejemplo: Datos personales sensibles, secretos industriales\n\n**Controles por Nivel:**\n- Público: Sin restricción\n- Interno: Autenticación requerida\n- Confidencial: Autenticación + Rol\n- Reservado: Autenticación + Rol + Aprobación"
    },
]

# =============================================================================
# 2. METADATOS Y CLASIFICACIÓN
# =============================================================================
METADATA_EXAMPLES: List[Dict[str, str]] = [
    {
        "input": "¿Qué metadatos debe tener un documento?",
        "output": "Los metadatos se organizan en categorías:\n\n**Metadatos de Identificación:**\n- ID único del documento\n- Título descriptivo\n- Código de clasificación\n- Número de registro\n\n**Metadatos Descriptivos:**\n- Autor/Creador\n- Fecha de creación\n- Fecha de modificación\n- Versión actual\n- Idioma\n- Resumen/Descripción\n\n**Metadatos de Gestión:**\n- Tipo documental\n- Estado (borrador, vigente, obsoleto)\n- Fecha de vigencia\n- Fecha de caducidad\n- Política de retención aplicable\n\n**Metadatos de Acceso:**\n- Nivel de confidencialidad\n- Propietario\n- Permisos de acceso\n- Restricciones de uso\n\n**Metadatos Técnicos:**\n- Formato de archivo\n- Tamaño en bytes\n- Hash de integridad (SHA-256)\n- Firma electrónica (si aplica)"
    },
    {
        "input": "¿Cómo funciona la clasificación documental?",
        "output": "La clasificación documental organiza los documentos jerárquicamente:\n\n**Cuadro de Clasificación (ejemplo):**\n```\n01. ÓRGANOS DE GOBIERNO\n    01.01 Junta General\n    01.02 Consejo de Administración\n02. ADMINISTRACIÓN\n    02.01 Gestión económica\n         02.01.01 Contabilidad\n         02.01.02 Presupuestos\n    02.02 Recursos Humanos\n         02.02.01 Selección\n         02.02.02 Contratación\n03. OPERACIONES\n    03.01 Producción\n    03.02 Calidad\n```\n\n**Aplicación:**\n1. Cada documento recibe un código de clasificación\n2. El código determina:\n   - Ubicación en el archivo\n   - Política de retención\n   - Responsable de custodia\n   - Acceso permitido\n\n**Beneficios:**\n- Localización rápida\n- Retención automática\n- Auditoría simplificada\n- Migración ordenada"
    },
    {
        "input": "¿Qué es el esquema de metadatos Dublin Core?",
        "output": "Dublin Core es un estándar internacional de metadatos (ISO 15836):\n\n**15 Elementos Básicos:**\n1. **Title**: Título del documento\n2. **Creator**: Autor o creador\n3. **Subject**: Tema o palabras clave\n4. **Description**: Resumen del contenido\n5. **Publisher**: Entidad que publica\n6. **Contributor**: Otros colaboradores\n7. **Date**: Fecha relevante\n8. **Type**: Tipo de recurso\n9. **Format**: Formato de archivo\n10. **Identifier**: ID único (URI, ISBN, etc.)\n11. **Source**: Recurso del que deriva\n12. **Language**: Idioma\n13. **Relation**: Relación con otros documentos\n14. **Coverage**: Cobertura espacial/temporal\n15. **Rights**: Derechos de uso\n\n**Ventajas:**\n- Interoperabilidad entre sistemas\n- Estándar reconocido internacionalmente\n- Extensible con calificadores\n- Compatible con linked data (RDF)"
    },
    {
        "input": "¿Cómo se asignan automáticamente los metadatos?",
        "output": "El sistema utiliza varias técnicas de extracción automática:\n\n**1. Extracción de Texto (OCR + NLP):**\n- Reconocimiento de texto en documentos escaneados\n- Identificación de entidades (nombres, fechas, importes)\n- Detección de idioma\n\n**2. Análisis de Estructura:**\n- Identificación de tipo documental por plantilla\n- Extracción de campos de formularios\n- Reconocimiento de tablas\n\n**3. Clasificación por IA:**\n- Modelo entrenado con documentos históricos\n- Sugerencia de categoría con % de confianza\n- Aprendizaje continuo de correcciones\n\n**4. Metadatos Heredados:**\n- Del archivo de origen (EXIF, propiedades Office)\n- Del proceso de digitalización\n- Del flujo de trabajo\n\n**5. Reglas de Negocio:**\n- Patrones en nombres de archivo\n- Carpeta de origen\n- Usuario que sube el documento\n\n**Validación:**\n- Campos obligatorios según tipo documental\n- Formato de fechas y códigos\n- Valores permitidos (listas controladas)"
    },
    {
        "input": "¿Qué son las taxonomías y vocabularios controlados?",
        "output": "Son herramientas para estandarizar la clasificación:\n\n**Taxonomía:**\nEstructura jerárquica de categorías predefinidas.\n```\nContratos\n├── Por tipo\n│   ├── Arrendamiento\n│   ├── Servicios\n│   └── Compraventa\n├── Por estado\n│   ├── Vigente\n│   ├── Vencido\n│   └── En negociación\n└── Por departamento\n    ├── Legal\n    ├── Compras\n    └── RRHH\n```\n\n**Vocabulario Controlado:**\nLista cerrada de términos permitidos.\n- Evita sinónimos (factura vs. recibo)\n- Normaliza escritura (ACME Corp = Acme Corporation)\n- Incluye términos preferidos y alternativos\n\n**Tesauro:**\nVocabulario con relaciones semánticas.\n- Términos más amplios (BT)\n- Términos más específicos (NT)\n- Términos relacionados (RT)\n- Sinónimos (USE/UF)\n\n**Beneficios:**\n- Búsqueda más precisa\n- Navegación por facetas\n- Consistencia en metadatos\n- Interoperabilidad con otros sistemas"
    },
]

# =============================================================================
# 3. CICLO DE VIDA DEL DOCUMENTO
# =============================================================================
LIFECYCLE_EXAMPLES: List[Dict[str, str]] = [
    {
        "input": "¿Cuáles son las fases del ciclo de vida de un documento?",
        "output": "El ciclo de vida documental tiene fases claramente definidas:\n\n**1. CREACIÓN/CAPTURA**\n- Documento nuevo interno\n- Digitalización de documento físico\n- Recepción de documento externo\n- Importación desde otro sistema\n\n**2. CLASIFICACIÓN**\n- Asignación de tipo documental\n- Aplicación de metadatos\n- Indexación para búsqueda\n- Verificación de calidad\n\n**3. ALMACENAMIENTO**\n- Ubicación en repositorio\n- Control de versiones\n- Copias de seguridad\n- Garantía de integridad\n\n**4. USO/DISTRIBUCIÓN**\n- Consulta y visualización\n- Descarga controlada\n- Compartición interna/externa\n- Colaboración en edición\n\n**5. ARCHIVO**\n- Transferencia al archivo histórico\n- Reducción de acceso frecuente\n- Preservación a largo plazo\n\n**6. DISPOSICIÓN**\n- Evaluación según política de retención\n- Destrucción certificada\n- Transferencia a archivo histórico\n- Conservación permanente"
    },
    {
        "input": "¿Qué es el archivo de gestión y el archivo histórico?",
        "output": "Son dos fases del ciclo archivístico:\n\n**ARCHIVO DE GESTIÓN (Activo):**\n- Documentos en uso frecuente\n- Tramitación en curso\n- Acceso habitual por usuarios\n- Retención: 0-5 años típicamente\n- Responsable: Unidad productora\n- Ubicación: Cerca del usuario\n\n**ARCHIVO INTERMEDIO:**\n- Documentos de consulta ocasional\n- Tramitación finalizada\n- Valor administrativo vigente\n- Retención: 5-15 años\n- Responsable: Archivo central\n- Ubicación: Centralizado\n\n**ARCHIVO HISTÓRICO:**\n- Documentos de valor permanente\n- Patrimonio documental\n- Consulta para investigación\n- Retención: Permanente\n- Responsable: Archivero profesional\n- Ubicación: Archivo histórico\n\n**Transferencias:**\n- De gestión a intermedio: Automática por antigüedad\n- De intermedio a histórico: Evaluación de valor\n- Destrucción: Solo con acta y autorización"
    },
    {
        "input": "¿Cómo se gestiona un documento obsoleto?",
        "output": "La gestión de documentos obsoletos sigue un proceso riguroso:\n\n**1. Identificación:**\n- Detección automática por fecha de vigencia\n- Revisión periódica de contenido\n- Notificación a responsable\n\n**2. Evaluación:**\n- ¿Tiene valor histórico?\n- ¿Existe obligación legal de conservación?\n- ¿Hay sustituto actualizado?\n- ¿Está referenciado por otros documentos?\n\n**3. Marcado:**\n- Estado: 'Obsoleto' o 'Anulado'\n- Fecha de obsolescencia\n- Motivo de la obsolescencia\n- Documento que lo sustituye (si aplica)\n\n**4. Restricción de Acceso:**\n- Eliminar de búsquedas por defecto\n- Mostrar aviso de obsolescencia\n- Mantener acceso para histórico\n\n**5. Acciones Posibles:**\n- **Conservar**: Como histórico con marca\n- **Archivar**: Mover a archivo histórico\n- **Destruir**: Cuando cumple retención\n\n**Importante:**\n- Nunca eliminar sin evaluar\n- Documentar la decisión\n- Mantener trazabilidad"
    },
    {
        "input": "¿Qué es la preservación digital a largo plazo?",
        "output": "La preservación digital garantiza la accesibilidad futura:\n\n**Desafíos:**\n- Obsolescencia de formatos (¿quién abre un .wpd?)\n- Degradación de soportes\n- Pérdida de contexto\n- Cambios tecnológicos\n\n**Estrategias de Preservación:**\n\n**1. Migración:**\n- Convertir a formatos actuales periódicamente\n- PDF/A para documentos de texto\n- TIFF para imágenes\n\n**2. Emulación:**\n- Mantener entornos antiguos virtualizados\n- Para formatos no convertibles\n\n**3. Encapsulación:**\n- Incluir toda información necesaria\n- Metadatos de preservación (PREMIS)\n- Documentación del contexto\n\n**4. Normalización:**\n- Convertir a formato estándar al ingresar\n- Reducir variedad de formatos\n\n**Verificación de Integridad:**\n- Hash SHA-256 al ingresar\n- Verificación periódica automática\n- Alertas de corrupción\n\n**Estándares:**\n- OAIS (ISO 14721): Modelo de referencia\n- PREMIS: Metadatos de preservación\n- METS: Empaquetado de objetos digitales"
    },
]

# =============================================================================
# 4. POLÍTICAS DE RETENCIÓN
# =============================================================================
RETENTION_EXAMPLES: List[Dict[str, str]] = [
    {
        "input": "¿Qué es una política de retención documental?",
        "output": "Una política de retención define cuánto tiempo conservar cada tipo de documento:\n\n**Componentes:**\n1. **Tipo documental**: Qué documentos aplica\n2. **Plazo de retención**: Tiempo mínimo de conservación\n3. **Evento de inicio**: Desde cuándo cuenta (fecha documento, fin contrato, etc.)\n4. **Disposición final**: Qué hacer al cumplir el plazo\n5. **Base legal**: Normativa que lo exige\n\n**Ejemplo de Política:**\n```\nTipo: Facturas emitidas\nRetención: 6 años\nInicio: Fecha de emisión\nDisposición: Destrucción certificada\nBase legal: Art. 30 Código de Comercio\n```\n\n**Beneficios:**\n- Cumplimiento legal garantizado\n- Optimización de almacenamiento\n- Reducción de riesgos\n- Auditoría simplificada\n\n**Aplicación Automática:**\n- El sistema asigna política según tipo documental\n- Alerta antes de expiración\n- Propone disposición al cumplir plazo\n- Registra todas las acciones"
    },
    {
        "input": "¿Cuánto tiempo debo conservar las facturas?",
        "output": "Los plazos de retención de facturas varían según normativa:\n\n**Plazos Legales en España:**\n\n| Tipo | Plazo | Base Legal |\n|------|-------|------------|\n| Facturas emitidas | 6 años | Art. 30 C. Comercio |\n| Facturas recibidas | 6 años | Art. 30 C. Comercio |\n| Facturas (IVA) | 4 años | Art. 66 LGT |\n| Libros registro IVA | 4 años | Art. 66 LGT |\n\n**Recomendación Práctica:**\n- Conservar **6 años** como mínimo\n- Desde el 31 de diciembre del año de emisión\n- Considerar **10 años** si hay posibles litigios\n\n**Formato de Conservación:**\n- Original electrónico: Válido con garantías de integridad\n- Digitalización certificada: Válido según Ley 39/2015\n- Papel: Válido pero no recomendado\n\n**Importante:**\n- Facturas de bienes de inversión: Conservar durante vida útil del bien\n- Facturas con IVA deducible: 4 años desde última declaración\n- Operaciones intracomunitarias: Pueden requerir más tiempo"
    },
    {
        "input": "¿Cuánto tiempo se conservan los contratos laborales?",
        "output": "Los documentos laborales tienen plazos específicos:\n\n**Contratos de Trabajo:**\n- Plazo: **4 años** desde finalización de relación laboral\n- Base: Art. 59 Estatuto de los Trabajadores\n- Recomendación: Conservar **5-6 años** por seguridad\n\n**Nóminas y TC2:**\n- Plazo: **4 años** (obligaciones Seguridad Social)\n- Recomendación: **6 años** por Código de Comercio\n\n**Expedientes de Personal:**\n- Durante relación laboral: Archivo activo\n- Tras baja: Mínimo 4 años\n\n**Partes de Accidente:**\n- Plazo: **5 años**\n- Base: Normativa de prevención de riesgos\n\n**Reconocimientos Médicos:**\n- Plazo: Durante relación + 5 años\n- Vigilancia de salud: Puede ser mayor\n\n**Convenios Colectivos:**\n- Plazo: Permanente (valor histórico)\n\n**Importante:**\n- Si hay litigio pendiente: Conservar hasta resolución firme\n- Reclamaciones por accidente: Pueden ser hasta 15 años\n- Pensiones: Documentos relevantes permanentes"
    },
    {
        "input": "¿Cómo se destruyen los documentos de forma segura?",
        "output": "La destrucción certificada sigue un protocolo estricto:\n\n**Proceso de Destrucción:**\n\n**1. Verificación Previa:**\n- Confirmar que cumple plazo de retención\n- Verificar que no hay litigios pendientes\n- Comprobar que no hay retención legal (hold)\n\n**2. Aprobación:**\n- Responsable del documento aprueba\n- Registro de la autorización\n- Notificación a interesados si procede\n\n**3. Ejecución:**\n- **Documentos físicos**: Trituración certificada (DIN 66399)\n- **Documentos digitales**: Borrado seguro (múltiples pasadas)\n- **Soportes completos**: Degaussing o destrucción física\n\n**4. Certificación:**\n- Acta de destrucción con:\n  - Lista de documentos destruidos\n  - Fecha y hora\n  - Método utilizado\n  - Testigos/responsables\n  - Firma del destructor (si externo)\n\n**Niveles de Seguridad (DIN 66399):**\n- P-1 a P-3: Documentos generales\n- P-4 a P-5: Datos confidenciales\n- P-6 a P-7: Datos secretos/clasificados\n\n**Documentación a Conservar:**\n- Acta de destrucción: 10 años\n- Índice de documentos destruidos: Permanente"
    },
]

# =============================================================================
# 5. FLUJOS DE TRABAJO (WORKFLOWS)
# =============================================================================
WORKFLOW_EXAMPLES: List[Dict[str, str]] = [
    {
        "input": "¿Qué es un flujo de trabajo documental?",
        "output": "Un workflow automatiza el ciclo de revisión y aprobación:\n\n**Componentes:**\n1. **Tareas**: Acciones a realizar (revisar, aprobar, firmar)\n2. **Participantes**: Quién realiza cada tarea\n3. **Transiciones**: Condiciones para pasar entre tareas\n4. **Plazos**: Tiempo límite para cada tarea\n5. **Notificaciones**: Alertas automáticas\n\n**Ejemplo - Aprobación de Factura:**\n```\n[Recepción] → [Validación Contable] → [Aprobación Jefe]\n     ↓              ↓                       ↓\n  Registro    Verificar datos         Si > 5000€ → [Dir. Financiero]\n  Metadatos   Asignar cuenta                ↓\n              contable              [Orden de Pago]\n```\n\n**Tipos de Flujos:**\n- **Secuencial**: Una tarea tras otra\n- **Paralelo**: Varias tareas simultáneas\n- **Condicional**: Rutas según criterios\n- **Ad-hoc**: Definido sobre la marcha\n\n**Beneficios:**\n- Trazabilidad completa\n- Reducción de tiempos\n- Cumplimiento de políticas\n- Alertas de cuellos de botella"
    },
    {
        "input": "¿Cómo se configura un flujo de aprobación?",
        "output": "La configuración de un flujo de aprobación requiere definir:\n\n**1. Trigger (Disparador):**\n- Subida de documento de tipo X\n- Cambio de estado\n- Solicitud manual\n- Fecha programada\n\n**2. Participantes:**\n- Roles fijos (Jefe de Compras)\n- Dinámicos (Jefe del solicitante)\n- Grupos (Comité de Compras)\n- Escalado (si no responde en X días)\n\n**3. Tareas:**\n```yaml\ntarea_revision:\n  tipo: aprobación\n  participante: ${jefe_departamento}\n  plazo: 3 días\n  acciones:\n    - aprobar → siguiente_tarea\n    - rechazar → notificar_solicitante\n    - devolver → tarea_anterior\n  campos_requeridos:\n    - comentario (si rechaza)\n```\n\n**4. Reglas de Negocio:**\n- Importe > 10.000€ → Requiere Director\n- Proveedor nuevo → Requiere Compliance\n- Urgente → Plazos reducidos 50%\n\n**5. Notificaciones:**\n- Tarea asignada: Email + App\n- Recordatorio: 24h antes del plazo\n- Vencimiento: Escalado automático"
    },
    {
        "input": "¿Qué pasa si un aprobador no responde a tiempo?",
        "output": "El sistema gestiona automáticamente los retrasos:\n\n**Recordatorios Automáticos:**\n- 48h antes: Primer recordatorio\n- 24h antes: Segundo recordatorio (urgente)\n- Al vencer: Notificación de vencimiento\n\n**Escalado:**\n1. **Escalado Jerárquico:**\n   - La tarea pasa al superior del aprobador\n   - Se notifica al aprobador original\n   - Se registra el escalado\n\n2. **Escalado Lateral:**\n   - Se asigna a un sustituto designado\n   - O a cualquier miembro del grupo aprobador\n\n3. **Escalado Administrativo:**\n   - Notificación a administrador del sistema\n   - Posible reasignación manual\n\n**Opciones de Configuración:**\n- `escalado_automatico: true`\n- `dias_para_escalar: 3`\n- `destinatario_escalado: superior`\n- `notificar_original: true`\n\n**Registro:**\n- Todos los vencimientos quedan registrados\n- Métricas de cumplimiento por usuario\n- Alertas para gestores de proceso"
    },
    {
        "input": "¿Cómo se integra la firma electrónica en el flujo?",
        "output": "La firma electrónica se integra como tarea del workflow:\n\n**Tipos de Firma Soportados:**\n\n**1. Firma Simple:**\n- Checkbox de aceptación\n- Para documentos internos de bajo riesgo\n- No tiene valor probatorio fuerte\n\n**2. Firma Avanzada:**\n- Vinculada al firmante\n- Permite detectar cambios posteriores\n- Basada en certificado de servidor\n\n**3. Firma Cualificada:**\n- Certificado emitido por prestador cualificado\n- Equivalente legal a firma manuscrita\n- Requiere dispositivo seguro (tarjeta, USB)\n\n**Integración en Workflow:**\n```yaml\ntarea_firma:\n  tipo: firma_electronica\n  nivel: cualificada\n  firmantes:\n    - rol: representante_legal\n    - rol: director_financiero\n  orden: secuencial  # o paralelo\n  posicion_firma:\n    pagina: ultima\n    coordenadas: [100, 100, 300, 150]\n  timestamp: qualified  # Sello de tiempo cualificado\n```\n\n**Proveedores Integrados:**\n- @firma (Administración Pública España)\n- Docusign\n- Adobe Sign\n- Signaturit\n\n**Verificación:**\n- Validación automática de certificados\n- Comprobación de revocación (OCSP/CRL)\n- Sello de tiempo de la firma"
    },
]

# =============================================================================
# 6. CONTROL DE VERSIONES
# =============================================================================
VERSION_CONTROL_EXAMPLES: List[Dict[str, str]] = [
    {
        "input": "¿Cómo funciona el control de versiones de documentos?",
        "output": "El sistema mantiene un historial completo de cada documento:\n\n**Numeración de Versiones:**\n- **Mayor (1.0, 2.0)**: Cambios significativos, nuevas aprobaciones\n- **Menor (1.1, 1.2)**: Correcciones menores, ajustes\n- **Borrador (0.1, 0.2)**: Versiones de trabajo no aprobadas\n\n**Información por Versión:**\n```\nDocumento: Contrato_Servicios_ACME.pdf\n├── v2.0 (actual, vigente)\n│   ├── Fecha: 2024-01-15\n│   ├── Autor: María García\n│   ├── Comentario: \"Actualización cláusula 5\"\n│   └── Hash: sha256:abc123...\n├── v1.1\n│   ├── Fecha: 2023-06-20\n│   ├── Autor: Juan López\n│   └── Comentario: \"Corrección typos\"\n└── v1.0\n    ├── Fecha: 2023-01-10\n    └── Comentario: \"Versión inicial aprobada\"\n```\n\n**Funcionalidades:**\n- Ver cualquier versión anterior\n- Comparar diferencias entre versiones\n- Restaurar versión anterior\n- Bloquear edición (check-out/check-in)\n\n**Políticas:**\n- Versión menor automática al guardar\n- Versión mayor requiere aprobación\n- Comentario obligatorio en cambios"
    },
    {
        "input": "¿Qué es el check-out y check-in de documentos?",
        "output": "Es el mecanismo para edición exclusiva de documentos:\n\n**CHECK-OUT (Desproteger):**\n1. Usuario solicita editar documento\n2. Sistema bloquea el documento\n3. Se descarga copia de trabajo\n4. Otros usuarios ven \"En edición por [Usuario]\"\n5. Solo lectura para el resto\n\n**Estado Durante Check-Out:**\n```\n🔒 Contrato_ACME.pdf\n   Bloqueado por: María García\n   Desde: 2024-01-15 09:30\n   Acciones disponibles:\n   - Ver versión actual (solo lectura)\n   - Solicitar desbloqueo\n   - Notificar al editor\n```\n\n**CHECK-IN (Proteger):**\n1. Usuario termina de editar\n2. Sube nueva versión\n3. Añade comentario de cambios\n4. Sistema desbloquea documento\n5. Nueva versión disponible para todos\n\n**Cancelar Check-Out:**\n- El editor puede cancelar sin guardar cambios\n- Un administrador puede forzar desbloqueo\n- Se notifica al editor original\n\n**Protección contra Pérdidas:**\n- Autoguardado cada 5 minutos (borrador)\n- Recuperación de borradores\n- Timeout de bloqueo (24h por defecto)"
    },
    {
        "input": "¿Cómo se comparan dos versiones de un documento?",
        "output": "El sistema ofrece comparación visual y textual:\n\n**Comparación de Texto:**\n```diff\n- El plazo de entrega será de 30 días\n+ El plazo de entrega será de 45 días\n\n  Las penalizaciones por retraso se mantienen\n+ según lo establecido en el Anexo B.\n```\n\n**Tipos de Comparación:**\n\n**1. Lado a Lado:**\n- Dos paneles con cada versión\n- Diferencias resaltadas en color\n- Sincronización de scroll\n\n**2. Combinada (Markup):**\n- Un solo documento con marcas\n- Tachado para eliminaciones\n- Subrayado para adiciones\n- Colores por autor\n\n**3. Resumen de Cambios:**\n- Lista de modificaciones\n- Número de páginas afectadas\n- Estadísticas (palabras añadidas/eliminadas)\n\n**Formatos Soportados:**\n- PDF: Comparación visual y textual\n- Office: Usar \"Control de Cambios\" nativo\n- Texto plano: Diff estándar\n\n**Uso Típico:**\n- Revisar cambios antes de aprobar\n- Auditar modificaciones históricas\n- Identificar autor de cada cambio"
    },
]

# =============================================================================
# 7. PERMISOS Y ACCESO
# =============================================================================
ACCESS_CONTROL_EXAMPLES: List[Dict[str, str]] = [
    {
        "input": "¿Cómo funcionan los permisos de acceso a documentos?",
        "output": "El sistema implementa control de acceso multinivel:\n\n**Niveles de Permisos:**\n\n**1. Por Rol (RBAC):**\n```\nRol: Gestor de Contratos\n├── Ver: Todos los contratos\n├── Editar: Contratos de su departamento\n├── Aprobar: Contratos < 50.000€\n└── Eliminar: No permitido\n```\n\n**2. Por Documento (ACL):**\n- Lista de control de acceso específica\n- Usuarios/grupos con permisos explícitos\n- Sobrescribe permisos de rol si es más restrictivo\n\n**3. Por Metadatos:**\n- Confidencialidad determina acceso base\n- Departamento propietario\n- Proyecto asociado\n\n**Permisos Granulares:**\n| Permiso | Descripción |\n|---------|-------------|\n| Leer | Ver contenido y metadatos |\n| Descargar | Obtener copia local |\n| Editar | Modificar contenido |\n| Versionar | Crear nuevas versiones |\n| Compartir | Dar acceso a otros |\n| Mover | Cambiar ubicación |\n| Eliminar | Borrar documento |\n| Administrar | Gestionar permisos |\n\n**Herencia:**\n- Carpetas heredan permisos a documentos\n- Se puede romper herencia explícitamente"
    },
    {
        "input": "¿Cómo se comparte un documento con usuarios externos?",
        "output": "El sistema ofrece varias opciones de compartición externa:\n\n**1. Enlace de Descarga:**\n- URL única con token de seguridad\n- Configurable: expiración, número de descargas\n- Opcional: contraseña de acceso\n```\nhttps://docs.empresa.com/share/abc123?token=xyz789\nExpira: 7 días | Descargas: 5 | Contraseña: Sí\n```\n\n**2. Visor en Línea:**\n- Documento visible en navegador\n- Sin posibilidad de descarga\n- Marca de agua con identificación\n\n**3. Sala de Datos Virtual:**\n- Espacio seguro para due diligence\n- Múltiples documentos\n- Permisos granulares por usuario/documento\n- Auditoría completa de accesos\n\n**Controles de Seguridad:**\n- Marca de agua dinámica (nombre, fecha, IP)\n- Prohibir impresión/copia\n- Geobloqueo (solo desde ciertos países)\n- Rango de IPs permitidas\n- Autenticación de dos factores\n\n**Registro de Actividad:**\n- Quién accedió y cuándo\n- Tiempo de visualización por página\n- Intentos fallidos\n- Descargas realizadas"
    },
    {
        "input": "¿Qué es una retención legal (legal hold)?",
        "output": "Una retención legal impide la modificación o destrucción de documentos:\n\n**¿Cuándo se Aplica?**\n- Litigio pendiente o anticipado\n- Investigación regulatoria\n- Auditoría en curso\n- Requerimiento judicial\n\n**Efectos de la Retención:**\n```\n⚖️ LEGAL HOLD ACTIVO\nDocumento: Contrato_Proveedor_XYZ.pdf\nMotivo: Litigio caso #2024-1234\nFecha inicio: 2024-01-15\nResponsable: Dpto. Legal\n\nRestricciones:\n✗ No se puede eliminar\n✗ No se puede modificar\n✗ No aplica política de retención\n✓ Se puede consultar (con registro)\n```\n\n**Proceso:**\n1. Legal identifica documentos afectados\n2. Se crea caso de retención con criterios\n3. Sistema localiza documentos matching\n4. Se aplica bloqueo automático\n5. Se notifica a custodios\n6. Al cerrar caso, se libera retención\n\n**Auditoría:**\n- Log de todos los accesos durante retención\n- Registro de intentos de modificación\n- Informe para proceso legal\n\n**Importante:**\n- Destruir documentos bajo retención legal = Spoliation\n- Puede conllevar sanciones severas"
    },
]

# =============================================================================
# 8. BÚSQUEDA Y RECUPERACIÓN
# =============================================================================
SEARCH_EXAMPLES: List[Dict[str, str]] = [
    {
        "input": "¿Qué tipos de búsqueda están disponibles?",
        "output": "El sistema ofrece múltiples métodos de búsqueda:\n\n**1. Búsqueda Simple:**\n- Caja de texto única\n- Busca en título, contenido y metadatos\n- Soporta comillas para frases exactas\n- Ejemplo: `contrato \"ACME Corporation\" 2024`\n\n**2. Búsqueda Avanzada:**\n- Formulario con campos específicos\n- Combinación de criterios (AND/OR)\n- Rangos de fechas\n- Filtros por tipo, estado, autor\n\n**3. Búsqueda por Metadatos:**\n- Filtrado por facetas\n- Navegación por taxonomía\n- Valores exactos de campos\n\n**4. Búsqueda Semántica (IA):**\n- Entiende el significado, no solo palabras\n- \"documentos sobre incumplimiento de contrato\"\n- Encuentra sinónimos y conceptos relacionados\n\n**5. Búsqueda por Similitud:**\n- \"Encuentra documentos similares a este\"\n- Basada en contenido y estructura\n\n**Operadores de Búsqueda:**\n- `AND`: ambos términos (por defecto)\n- `OR`: cualquiera de los términos\n- `NOT`: excluir término\n- `*`: comodín (contrat* → contrato, contratos)\n- `~`: fuzzy (aproximado)"
    },
    {
        "input": "¿Cómo busco documentos por fecha?",
        "output": "Las búsquedas por fecha soportan varios formatos:\n\n**Por Campo de Fecha:**\n```\nfecha_creacion: 2024-01-15\nfecha_modificacion: [2024-01-01 TO 2024-01-31]\nfecha_vigencia: <2024-06-30\n```\n\n**Operadores Temporales:**\n- `>`: Mayor que (después de)\n- `<`: Menor que (antes de)\n- `>=`, `<=`: Incluye el límite\n- `[fecha1 TO fecha2]`: Rango cerrado\n- `{fecha1 TO fecha2}`: Rango abierto\n\n**Fechas Relativas:**\n- `hoy`, `ayer`, `mañana`\n- `esta_semana`, `este_mes`, `este_año`\n- `ultimos_7_dias`, `ultimos_30_dias`\n- `hace_1_mes`, `hace_1_año`\n\n**Ejemplos Prácticos:**\n```\n# Contratos que vencen este mes\ntipo:contrato AND fecha_vencimiento:este_mes\n\n# Facturas de los últimos 90 días\ntipo:factura AND fecha_creacion:ultimos_90_dias\n\n# Documentos modificados ayer\nfecha_modificacion:ayer\n```\n\n**Ordenación:**\n- Por fecha más reciente (defecto)\n- Por fecha más antigua\n- Por relevancia + fecha"
    },
    {
        "input": "¿Cómo funciona la búsqueda semántica?",
        "output": "La búsqueda semántica usa IA para entender el significado:\n\n**Diferencia con Búsqueda Tradicional:**\n\n| Búsqueda Texto | Búsqueda Semántica |\n|----------------|--------------------|\n| Coincidencia exacta de palabras | Entiende el significado |\n| \"contrato\" no encuentra \"acuerdo\" | Encuentra sinónimos |\n| Orden de palabras importa | Entiende la intención |\n| Fallos por errores tipográficos | Tolerante a variaciones |\n\n**Ejemplo:**\nQuery: \"documentos sobre penalizaciones por retraso en entregas\"\n\n*Encuentra:*\n- Cláusulas de penalización en contratos\n- Emails sobre incumplimiento de plazos\n- Facturas con descuentos por demora\n- Actas de reunión discutiendo retrasos\n\n**Cómo Funciona:**\n1. El texto se convierte en vector numérico (embedding)\n2. La consulta también se vectoriza\n3. Se buscan vectores similares\n4. Los más cercanos son más relevantes\n\n**Mejores Prácticas:**\n- Usar lenguaje natural, no keywords\n- Describir lo que buscas, no cómo se llama\n- Combinar con filtros de metadatos para refinar\n\n**Limitaciones:**\n- Requiere buena calidad de texto (OCR)\n- Funciona mejor con documentos largos\n- Puede traer falsos positivos semánticos"
    },
]

# =============================================================================
# 9. CUMPLIMIENTO NORMATIVO
# =============================================================================
COMPLIANCE_EXAMPLES: List[Dict[str, str]] = [
    {
        "input": "¿Qué normativas aplican a la gestión documental?",
        "output": "Las principales normativas en España son:\n\n**Normativa General:**\n\n**1. Ley 39/2015 - Procedimiento Administrativo:**\n- Documento electrónico administrativo\n- Copias auténticas\n- Archivo electrónico único\n\n**2. Ley 40/2015 - Régimen Jurídico Sector Público:**\n- Sede electrónica\n- Firma electrónica\n- Interoperabilidad\n\n**3. RGPD + LOPDGDD:**\n- Protección de datos personales\n- Derechos de acceso, rectificación, supresión\n- Medidas de seguridad\n\n**Normativa Sectorial:**\n\n**Mercantil:**\n- Código de Comercio (art. 30): Conservación 6 años\n- Ley de Sociedades de Capital: Actas y libros\n\n**Fiscal:**\n- LGT: Conservación 4 años (prescripción)\n- Reglamento de Facturación\n\n**Laboral:**\n- Estatuto de los Trabajadores\n- Ley de Prevención de Riesgos Laborales\n\n**Estándares Técnicos:**\n- ENI (Esquema Nacional de Interoperabilidad)\n- ENS (Esquema Nacional de Seguridad)\n- ISO 15489 (Gestión de documentos)\n- ISO 27001 (Seguridad de la información)"
    },
    {
        "input": "¿Qué requisitos tiene el RGPD para documentos?",
        "output": "El RGPD impone obligaciones específicas sobre documentos con datos personales:\n\n**Principios Aplicables:**\n\n**1. Minimización:**\n- Solo recoger datos necesarios\n- Eliminar datos innecesarios de documentos\n\n**2. Limitación de Conservación:**\n- No conservar más tiempo del necesario\n- Definir plazos de retención justificados\n\n**3. Integridad y Confidencialidad:**\n- Proteger contra acceso no autorizado\n- Cifrado de documentos sensibles\n- Control de acceso basado en necesidad\n\n**Derechos del Interesado:**\n\n| Derecho | Implicación Documental |\n|---------|------------------------|\n| Acceso | Localizar todos los documentos con sus datos |\n| Rectificación | Poder modificar datos incorrectos |\n| Supresión | Eliminar/anonimizar cuando solicite |\n| Portabilidad | Exportar en formato estructurado |\n\n**Medidas Técnicas:**\n- Búsqueda por datos personales (nombre, DNI)\n- Anonimización/Pseudonimización\n- Registro de actividades de tratamiento\n- Notificación de brechas en 72h\n\n**Documentación Obligatoria:**\n- Registro de actividades de tratamiento\n- Evaluaciones de impacto (EIPD)\n- Contratos con encargados de tratamiento"
    },
    {
        "input": "¿Cómo se garantiza la autenticidad de un documento electrónico?",
        "output": "La autenticidad se garantiza mediante varios mecanismos:\n\n**1. Firma Electrónica:**\n```\nNiveles (eIDAS):\n├── Simple: Email, checkbox\n├── Avanzada: Vinculada a firmante, detecta cambios\n└── Cualificada: Certificado cualificado + dispositivo seguro\n    → Equivalente a firma manuscrita\n```\n\n**2. Sello de Tiempo (Timestamp):**\n- Prueba que el documento existía en fecha X\n- Emitido por Autoridad de Sellado de Tiempo\n- Estándar RFC 3161\n\n**3. Código Seguro de Verificación (CSV):**\n- Código único por documento\n- Permite verificar en sede electrónica\n- Ejemplo: `CSV-2024-ABC123XYZ`\n\n**4. Hash de Integridad:**\n```\nDocumento: Contrato_2024.pdf\nSHA-256: 3a7bd3e2f4c5d6e7f8a9b0c1d2e3f4a5...\nFecha cálculo: 2024-01-15 10:30:00 UTC\n```\n\n**5. Metadatos de Autenticidad:**\n- Fecha de creación certificada\n- Autor verificado\n- Cadena de custodia\n- Registro de accesos\n\n**Verificación:**\n1. Comprobar firma electrónica válida\n2. Verificar certificado no revocado\n3. Validar sello de tiempo\n4. Confirmar integridad (hash coincide)\n5. Revisar cadena de custodia"
    },
]

# =============================================================================
# 10. DIGITALIZACIÓN Y OCR
# =============================================================================
DIGITIZATION_EXAMPLES: List[Dict[str, str]] = [
    {
        "input": "¿Cómo se digitaliza correctamente un documento?",
        "output": "La digitalización sigue un proceso estandarizado:\n\n**Preparación del Documento:**\n1. Retirar grapas, clips\n2. Alisar dobleces\n3. Ordenar páginas\n4. Verificar legibilidad\n\n**Configuración del Escáner:**\n```\nResolución: 300 DPI (mínimo para OCR)\nColor: Según documento\n  - B/N: Texto simple\n  - Escala grises: Documentos con sellos\n  - Color: Fotos, diagramas\nFormato: PDF/A o TIFF\nCompresión: Sin pérdida (lossless)\n```\n\n**Proceso de Captura:**\n1. Escanear documento completo\n2. Verificar calidad de imagen\n3. Corregir orientación si necesario\n4. Aplicar OCR para texto buscable\n5. Asignar metadatos\n6. Validar resultado\n\n**Control de Calidad:**\n- Legibilidad de texto\n- Ausencia de páginas en blanco no deseadas\n- Orientación correcta\n- OCR verificado por muestreo\n\n**Digitalización Certificada (Ley 39/2015):**\n- Funcionario habilitado\n- Garantiza autenticidad e integridad\n- Misma validez que el original"
    },
    {
        "input": "¿Qué es el OCR y cómo funciona?",
        "output": "OCR (Optical Character Recognition) convierte imágenes en texto editable:\n\n**Proceso:**\n```\n[Imagen] → [Preprocesado] → [Detección] → [Reconocimiento] → [Texto]\n   │            │               │               │\n   │         Binarización    Localizar      Identificar\n   │         Enderezar       líneas y       caracteres\n   │         Limpiar ruido   palabras       usando IA\n```\n\n**Tipos de OCR:**\n\n**1. OCR Básico:**\n- Reconoce texto impreso estándar\n- Funciona bien con buena calidad\n- Rápido y económico\n\n**2. ICR (Intelligent Character Recognition):**\n- Reconoce escritura manuscrita\n- Menor precisión\n- Requiere entrenamiento\n\n**3. OCR con IA (Deep Learning):**\n- Mayor precisión en documentos difíciles\n- Entiende contexto\n- Mejor con sellos, firmas, degradación\n\n**Factores que Afectan Precisión:**\n- Calidad del escaneo (mínimo 300 DPI)\n- Contraste texto/fondo\n- Tipo de fuente\n- Estado del documento original\n- Idioma (español bien soportado)\n\n**Salida:**\n- Texto plano extraído\n- PDF con capa de texto (searchable PDF)\n- Coordenadas de cada palabra (hOCR)"
    },
    {
        "input": "¿Qué hacer con documentos escaneados de baja calidad?",
        "output": "El sistema incluye técnicas de mejora para OCR:\n\n**Preprocesamiento Automático:**\n\n**1. Corrección de Inclinación (Deskew):**\n- Detecta ángulo de rotación\n- Endereza el documento\n- Mejora detección de líneas\n\n**2. Binarización Adaptativa:**\n- Convierte a blanco/negro\n- Ajusta umbral por zonas\n- Mejora contraste local\n\n**3. Eliminación de Ruido:**\n- Filtro de manchas pequeñas\n- Suavizado de bordes\n- Eliminación de líneas de fondo\n\n**4. Mejora de Contraste:**\n- Ecualización de histograma\n- Ajuste de niveles\n- Realce de bordes\n\n**OCR Mejorado con IA:**\n```\nDocumento: Factura_1975_borrosa.pdf\nOCR estándar: 65% precisión\nOCR + preprocesado: 82% precisión\nOCR + IA (EasyOCR): 91% precisión\n```\n\n**Opciones si OCR Falla:**\n1. Re-escanear con mejor configuración\n2. Transcripción manual asistida\n3. Marcar como \"solo imagen\" (no buscable)\n4. Indexar con metadatos manuales\n\n**Indicador de Confianza:**\n- Sistema muestra % de confianza OCR\n- Alerta si < 80%\n- Sugiere revisión manual"
    },
]

# =============================================================================
# 11. GESTIÓN DE EXPEDIENTES ADMINISTRATIVOS
# =============================================================================
EXPEDIENTES_ADMINISTRATIVOS_EXAMPLES: List[Dict[str, str]] = [
    {
        "input": "¿Qué es un expediente administrativo electrónico?",
        "output": "Según el artículo 70 de la Ley 39/2015, el expediente administrativo es:\n\n**Definición Legal:**\nConjunto ordenado de documentos y actuaciones que sirven de antecedente y fundamento a la resolución administrativa, así como las diligencias encaminadas a ejecutarla.\n\n**Características del Expediente Electrónico:**\n\n**1. Formato:**\n- Debe ser electrónico (obligatorio desde 2018)\n- Formato de intercambio según ENI\n- Estructura XML normalizada\n\n**2. Componentes Obligatorios:**\n```\nExpediente Electrónico\n├── Índice electrónico (firmado)\n│   ├── Fecha de generación\n│   ├── Lista de documentos con hash\n│   └── Firma del órgano competente\n├── Documentos electrónicos\n│   ├── Originales o copias auténticas\n│   ├── Con firma electrónica válida\n│   └── Metadatos ENI completos\n└── Metadatos del expediente\n    ├── Identificador único\n    ├── Órgano responsable\n    ├── Fecha apertura/cierre\n    └── Estado de tramitación\n```\n\n**3. Garantías:**\n- Integridad: Hash de cada documento\n- Autenticidad: Firma electrónica\n- Disponibilidad: Acceso durante plazo legal\n- Trazabilidad: Registro de acciones"
    },
    {
        "input": "¿Cómo se numera y organiza un expediente administrativo?",
        "output": "La numeración y organización sigue normas específicas:\n\n**Identificador del Expediente:**\n```\nFormato recomendado ENI:\nES_[Código DIR3]_[Año]_EXP_[Secuencial]\n\nEjemplo:\nES_A05003001_2024_EXP_00001234\n│  │          │    │   │\n│  │          │    │   └── Número secuencial\n│  │          │    └────── Tipo: Expediente\n│  │          └─────────── Año de apertura\n│  └────────────────────── Código DIR3 del órgano\n└──────────────────────────País (España)\n```\n\n**Organización de Documentos:**\n\n**1. Orden Cronológico:**\n- Por fecha de incorporación al expediente\n- Numeración secuencial: 001, 002, 003...\n\n**2. Por Fases del Procedimiento:**\n```\n/Fase_1_Inicio/\n  ├── 001_Solicitud.pdf\n  ├── 002_Documentacion_aportada.pdf\n  └── 003_Acuse_recibo.pdf\n/Fase_2_Instruccion/\n  ├── 004_Informe_tecnico.pdf\n  └── 005_Alegaciones.pdf\n/Fase_3_Resolucion/\n  └── 006_Resolucion_final.pdf\n```\n\n**3. Foliado Electrónico:**\n- Cada documento tiene número de folio\n- Páginas numeradas dentro del documento\n- Referencia: Folio 5, página 3 de 10"
    },
    {
        "input": "¿Qué es el índice electrónico del expediente?",
        "output": "El índice electrónico es obligatorio según art. 70.3 Ley 39/2015:\n\n**Definición:**\nRelación de documentos electrónicos que conforman el expediente, firmada electrónicamente por el órgano competente.\n\n**Contenido Obligatorio:**\n\n```xml\n<IndiceElectronico>\n  <FechaIndiceElectronico>2024-01-15T10:30:00</FechaIndiceElectronico>\n  <DocumentosIndizados>\n    <DocumentoIndizado>\n      <IdentificadorDocumento>ES_A05003001_2024_DOC_0001</IdentificadorDocumento>\n      <NombreDocumento>Solicitud de licencia</NombreDocumento>\n      <FechaIncorporacion>2024-01-10</FechaIncorporacion>\n      <OrdenDocumento>1</OrdenDocumento>\n      <HashDocumento algoritmo=\"SHA-256\">3a7bd3...</HashDocumento>\n      <TipoDocumental>TD01</TipoDocumental>\n      <EstadoElaboracion>Original</EstadoElaboracion>\n    </DocumentoIndizado>\n    <!-- Más documentos -->\n  </DocumentosIndizados>\n  <FirmaIndice><!-- Firma XAdES --></FirmaIndice>\n</IndiceElectronico>\n```\n\n**Funciones del Índice:**\n1. Garantiza integridad del expediente\n2. Permite verificar completitud\n3. Documenta el orden de los documentos\n4. Base para la foliación electrónica\n\n**Generación:**\n- Automática al cerrar expediente\n- Actualizable durante tramitación\n- Firma al remitir o archivar"
    },
    {
        "input": "¿Cuáles son los estados de un expediente administrativo?",
        "output": "El expediente pasa por varios estados durante su ciclo de vida:\n\n**Estados Principales:**\n\n```\n┌─────────────────────────────────────────────────────────────┐\n│  CICLO DE VIDA DEL EXPEDIENTE ADMINISTRATIVO                │\n├─────────────────────────────────────────────────────────────┤\n│                                                              │\n│  [ABIERTO] ────────────────────────────────────────────┐    │\n│      │                                                  │    │\n│      ▼                                                  │    │\n│  [EN TRAMITACIÓN] ──────► [SUSPENDIDO] ◄───────────────┤    │\n│      │                         │                        │    │\n│      │                         │ (Reanudar)             │    │\n│      ▼                         ▼                        │    │\n│  [PENDIENTE DE RESOLUCIÓN] ◄───┘                        │    │\n│      │                                                  │    │\n│      ▼                                                  │    │\n│  [RESUELTO]                                             │    │\n│      │                                                  │    │\n│      ▼                                                  │    │\n│  [CERRADO] ─────────► [ARCHIVADO]                       │    │\n│                                                          │    │\n└─────────────────────────────────────────────────────────────┘\n```\n\n**Descripción de Estados:**\n\n| Estado | Descripción | Acciones Permitidas |\n|--------|-------------|---------------------|\n| Abierto | Recién creado, sin documentos | Añadir documentos |\n| En tramitación | Instrucción activa | Añadir, consultar, informes |\n| Suspendido | Paralizado por causa legal | Solo consulta |\n| Pendiente resolución | Instrucción completa | Resolver |\n| Resuelto | Con resolución dictada | Notificar, recursos |\n| Cerrado | Trámite finalizado | Solo consulta |\n| Archivado | En archivo definitivo | Consulta restringida |"
    },
    {
        "input": "¿Cómo se incorporan documentos a un expediente?",
        "output": "La incorporación de documentos sigue reglas específicas:\n\n**Tipos de Documentos a Incorporar:**\n\n**1. Documentos Aportados por el Interesado:**\n- Solicitudes y escritos\n- Documentación justificativa\n- Alegaciones y recursos\n\n**2. Documentos Generados por la Administración:**\n- Informes técnicos y jurídicos\n- Requerimientos y notificaciones\n- Resoluciones y acuerdos\n\n**3. Documentos de Otras Administraciones:**\n- Informes preceptivos\n- Certificados obtenidos por interoperabilidad\n\n**Proceso de Incorporación:**\n```\n1. Recepción del documento\n   ├── Registro de entrada (si externo)\n   └── Generación (si interno)\n\n2. Validación\n   ├── Formato válido (PDF/A preferible)\n   ├── Firma electrónica (si requerida)\n   └── Metadatos completos\n\n3. Asignación de metadatos\n   ├── Tipo documental (NTI)\n   ├── Fecha de incorporación\n   ├── Origen (ciudadano/administración)\n   └── Estado de elaboración\n\n4. Incorporación al expediente\n   ├── Número de orden asignado\n   ├── Hash calculado\n   └── Índice actualizado\n\n5. Notificación (si procede)\n```\n\n**Documentos NO Incorporables:**\n- Borradores no definitivos\n- Notas internas informales\n- Documentos anónimos (salvo excepciones)"
    },
    {
        "input": "¿Qué metadatos debe tener un expediente según el ENI?",
        "output": "El Esquema Nacional de Interoperabilidad (ENI) define metadatos obligatorios:\n\n**Metadatos Obligatorios del Expediente:**\n\n```yaml\nexpediente:\n  # Identificación\n  identificador: \"ES_A05003001_2024_EXP_00001234\"\n  organo: \"A05003001\"  # Código DIR3\n  \n  # Clasificación\n  codigo_clasificacion: \"SIA_123456\"  # Código SIA del procedimiento\n  \n  # Fechas\n  fecha_apertura: \"2024-01-10\"\n  fecha_cierre: null  # Hasta que se cierre\n  \n  # Estado\n  estado: \"En tramitación\"\n  \n  # Interesados\n  interesados:\n    - tipo: \"Persona física\"\n      identificador: \"12345678Z\"\n      nombre: \"Juan García López\"\n  \n  # Acceso\n  tipo_acceso: \"Restringido\"\n  clasificacion_eni: \"CONFIDENCIAL\"\n  sensibilidad_datos_personales: \"Medio\"\n```\n\n**Metadatos de Cada Documento en el Expediente:**\n\n| Metadato | Obligatorio | Ejemplo |\n|----------|-------------|----------|\n| Identificador | Sí | ES_A05003001_2024_DOC_0001 |\n| Órgano | Sí | A05003001 |\n| Fecha captura | Sí | 2024-01-10T09:15:00 |\n| Origen | Sí | Ciudadano / Administración |\n| Estado elaboración | Sí | Original / Copia |\n| Tipo documental | Sí | TD01 (Solicitud) |\n| Tipo firma | Condicional | CSV, XAdES, CAdES |\n| Formato | Sí | PDF/A-1B |\n\n**Vocabularios Controlados:**\n- Tipos documentales: NTI de Política de gestión\n- Códigos SIA: Sistema de Información Administrativa\n- Códigos DIR3: Directorio Común de Unidades Orgánicas"
    },
    {
        "input": "¿Cómo se cierra un expediente administrativo?",
        "output": "El cierre del expediente sigue un proceso formal:\n\n**Requisitos para el Cierre:**\n\n1. **Resolución dictada y notificada**\n   - Resolución expresa o por silencio\n   - Notificación practicada (o intentada)\n   - Plazo de recursos transcurrido (o interpuesto)\n\n2. **Documentación completa**\n   - Todos los documentos incorporados\n   - Informes preceptivos incluidos\n   - Acuse de recibo de notificaciones\n\n3. **Ejecución de la resolución (si procede)**\n   - Actos de ejecución documentados\n   - Cumplimiento verificado\n\n**Proceso de Cierre:**\n\n```\n1. Verificación de completitud\n   └── Sistema comprueba documentos obligatorios\n\n2. Generación del índice electrónico definitivo\n   ├── Lista final de documentos\n   ├── Hash de cada documento\n   └── Firma del índice\n\n3. Diligencia de cierre\n   ├── Fecha de cierre\n   ├── Motivo (resolución, desistimiento, caducidad...)\n   └── Funcionario que cierra\n\n4. Cambio de estado\n   └── \"En tramitación\" → \"Cerrado\"\n\n5. Transferencia al archivo\n   └── Según calendario de conservación\n```\n\n**Diligencia de Cierre (ejemplo):**\n```\nDILIGENCIA: Para hacer constar que con fecha 15/01/2024\nse procede al cierre del expediente EXP-2024-00123,\ntramitado por el procedimiento \"Licencia de Apertura\",\nhabiendo quedado completo con la incorporación de la\nnotificación de la resolución favorable.\n\nEl expediente consta de 15 documentos según índice adjunto.\n\nEn Madrid, a 15 de enero de 2024.\nEl/La funcionario/a responsable.\n[Firma electrónica]\n```"
    },
    {
        "input": "¿Cómo se transfiere un expediente entre órganos administrativos?",
        "output": "La transferencia de expedientes (remisión) está regulada por el ENI:\n\n**Casos de Transferencia:**\n- Cambio de competencia\n- Recursos ante órgano superior\n- Colaboración entre administraciones\n- Transferencia al archivo\n\n**Proceso de Remisión Electrónica:**\n\n```\n┌──────────────────┐         ┌──────────────────┐\n│  Órgano Remitente │  ────►  │  Órgano Receptor │\n└──────────────────┘         └──────────────────┘\n        │                             │\n        ▼                             ▼\n1. Generar índice firmado     4. Verificar firma índice\n2. Empaquetar expediente      5. Comprobar hashes\n3. Enviar por SCSP/SIR        6. Incorporar a sistema\n                              7. Acuse de recibo\n```\n\n**Formato de Intercambio (NTI):**\n```xml\n<ExpedienteENI>\n  <Metadatos>\n    <Identificador>ES_A05003001_2024_EXP_00001</Identificador>\n    <!-- Metadatos del expediente -->\n  </Metadatos>\n  <IndiceElectronico>\n    <!-- Índice firmado -->\n  </IndiceElectronico>\n  <Documentos>\n    <Documento>\n      <ContenidoBinario><!-- Base64 --></ContenidoBinario>\n      <MetadatosDocumento><!-- ENI --></MetadatosDocumento>\n    </Documento>\n  </Documentos>\n  <FirmaExpediente><!-- Opcional --></FirmaExpediente>\n</ExpedienteENI>\n```\n\n**Plataformas de Intercambio:**\n- **SIR** (Sistema de Interconexión de Registros): Entre registros\n- **SCSP** (Sustitución de Certificados): Consulta de datos\n- **PID** (Plataforma de Intermediación): Datos entre AAPP\n\n**Garantías:**\n- Integridad verificada por hash\n- Autenticidad por firma del índice\n- Trazabilidad completa del envío"
    },
    {
        "input": "¿Qué es el desglose de documentos de un expediente?",
        "output": "El desglose permite extraer documentos originales de un expediente:\n\n**¿Qué es el Desglose?**\nExtracción de documentos originales aportados por el interesado para su devolución, dejando copia auténtica en el expediente.\n\n**Supuestos de Desglose:**\n1. Solicitud del interesado para recuperar originales\n2. Necesidad de presentar original en otro procedimiento\n3. Documentos de valor (títulos, certificados originales)\n\n**Proceso de Desglose:**\n\n```\n1. Solicitud de desglose\n   ├── Identificación del documento\n   └── Motivo de la solicitud\n\n2. Verificación\n   ├── El expediente permite desglose\n   ├── El documento es original aportado\n   └── No perjudica la tramitación\n\n3. Generación de copia auténtica\n   ├── Copia electrónica del documento\n   ├── Firma electrónica de autenticidad\n   └── CSV para verificación\n\n4. Sustitución en expediente\n   └── Original → Copia auténtica\n\n5. Diligencia de desglose\n   ├── Documento desglosado\n   ├── Fecha y hora\n   ├── Copia que lo sustituye\n   └── Firma del funcionario\n\n6. Entrega al interesado\n   └── Con acuse de recibo\n```\n\n**Diligencia de Desglose:**\n```\nDILIGENCIA DE DESGLOSE\n\nEn el expediente EXP-2024-00123 se procede al\ndesglose del documento \"Título universitario original\"\n(folio 3), a solicitud del interesado D. Juan García.\n\nEl documento original se sustituye por copia electrónica\nauténtica con CSV: ABC-123-XYZ, verificable en\nhttps://sede.ejemplo.gob.es/validar\n\nFecha: 15/01/2024\n[Firma electrónica]\n```\n\n**Limitaciones:**\n- No desglosar documentos generados por la Administración\n- No desglosar si perjudica derechos de terceros\n- Documentos en expedientes cerrados: Solo con autorización"
    },
    {
        "input": "¿Cómo se gestiona el acceso al expediente por el interesado?",
        "output": "El derecho de acceso al expediente está regulado en la Ley 39/2015:\n\n**Base Legal:**\n- Art. 53.1.a) Ley 39/2015: Derecho a conocer el estado de tramitación\n- Art. 53.1.d): Derecho a obtener copia de documentos\n\n**Tipos de Acceso:**\n\n**1. Consulta del Estado:**\n```\n[Sede Electrónica]\n     │\n     ▼\nConsulta expediente: EXP-2024-00123\n┌─────────────────────────────────────┐\n│ Estado: En tramitación              │\n│ Fase: Instrucción                   │\n│ Último movimiento: 10/01/2024       │\n│ Próxima acción: Informe técnico     │\n│ Plazo restante: 15 días             │\n└─────────────────────────────────────┘\n```\n\n**2. Vista del Expediente:**\n- Acceso completo a todos los documentos\n- Restricción: Documentos confidenciales de terceros\n- Formato: Visualización online o descarga\n\n**3. Obtención de Copias:**\n- Copias simples: Gratuitas si electrónicas\n- Copias auténticas: Pueden tener tasa\n- Formato: PDF con CSV para verificación\n\n**Procedimiento de Acceso:**\n```\n1. Identificación del interesado\n   ├── Cl@ve, DNIe, certificado\n   └── Verificación de legitimación\n\n2. Comprobación de derechos\n   ├── Es interesado en el procedimiento\n   └── O tiene autorización/representación\n\n3. Filtrado de contenido\n   ├── Ocultar datos de terceros\n   └── Restringir documentos confidenciales\n\n4. Registro del acceso\n   └── Auditoría: quién, cuándo, qué documentos\n```\n\n**Restricciones al Acceso:**\n- Documentos que afecten a terceros (sin su consentimiento)\n- Informes internos antes de resolución\n- Datos especialmente protegidos\n- Secreto profesional o industrial"
    },
    {
        "input": "¿Qué es el archivo del expediente y cuánto tiempo se conserva?",
        "output": "El archivo de expedientes sigue el ciclo archivístico:\n\n**Fases del Archivo:**\n\n```\n┌─────────────────────────────────────────────────────────────┐\n│                  CICLO ARCHIVÍSTICO                          │\n├─────────────────────────────────────────────────────────────┤\n│                                                              │\n│  ARCHIVO DE OFICINA (0-5 años)                               │\n│  └── Expedientes cerrados recientemente                      │\n│      └── Acceso frecuente para consultas                     │\n│                     │                                        │\n│                     ▼ (Transferencia)                        │\n│  ARCHIVO CENTRAL (5-15 años)                                 │\n│  └── Expedientes de valor administrativo                     │\n│      └── Consulta ocasional                                  │\n│                     │                                        │\n│                     ▼ (Transferencia)                        │\n│  ARCHIVO INTERMEDIO (15-30 años)                             │\n│  └── Evaluación de valor histórico                           │\n│      └── Expurgo de documentos sin valor                     │\n│                     │                                        │\n│          ┌─────────┴─────────┐                               │\n│          ▼                   ▼                               │\n│  ARCHIVO HISTÓRICO    ELIMINACIÓN                            │\n│  (Conservación        (Certificada)                          │\n│   permanente)                                                │\n│                                                              │\n└─────────────────────────────────────────────────────────────┘\n```\n\n**Plazos de Conservación por Tipo:**\n\n| Tipo de Expediente | Plazo Mínimo | Base Legal |\n|--------------------|--------------|-----------|\n| Licencias urbanísticas | 15 años | Normativa urbanística |\n| Contratación pública | 5 años tras fin contrato | LCSP |\n| Subvenciones | 4 años | LGS |\n| Sanciones | 4 años (prescripción) | Ley 40/2015 |\n| Personal funcionario | Vida administrativa | EBEP |\n| Padrones/censos | Permanente | Valor histórico |\n\n**Calendario de Conservación:**\nDocumento que establece para cada serie documental:\n- Plazo en cada fase de archivo\n- Acción de disposición (conservar/eliminar)\n- Criterios de muestreo (si eliminación parcial)\n\n**Transferencias:**\n- Relación de entrega firmada\n- Verificación de integridad\n- Actualización de ubicación en sistema"
    },
    {
        "input": "¿Cómo se relaciona un expediente con el procedimiento administrativo?",
        "output": "El expediente documenta todo el procedimiento administrativo:\n\n**Relación Procedimiento-Expediente:**\n\n```\n┌─────────────────────────────────────────────────────────────┐\n│               PROCEDIMIENTO ADMINISTRATIVO                   │\n│          (Secuencia de trámites regulada por ley)           │\n├─────────────────────────────────────────────────────────────┤\n│                                                              │\n│  INICIACIÓN ──────────────────────────────────────────────┐ │\n│  ├── De oficio: Acuerdo de iniciación                     │ │\n│  └── A instancia: Solicitud del interesado         ───────┼─┼──► Expediente\n│                                                           │ │    (Documentos)\n│  INSTRUCCIÓN ─────────────────────────────────────────────┤ │\n│  ├── Alegaciones                                          │ │\n│  ├── Informes (preceptivos/facultativos)                  │ │\n│  ├── Pruebas                                              │ │\n│  ├── Audiencia al interesado                              │ │\n│  └── Información pública (si procede)             ───────┼─┼──► Expediente\n│                                                           │ │    (Documentos)\n│  TERMINACIÓN ─────────────────────────────────────────────┤ │\n│  ├── Resolución expresa                                   │ │\n│  ├── Desistimiento/Renuncia                               │ │\n│  ├── Caducidad                                            │ │\n│  └── Silencio administrativo                      ───────┼─┼──► Expediente\n│                                                           │ │    (Documentos)\n│  EJECUCIÓN (si procede) ──────────────────────────────────┘ │\n│  └── Actos de ejecución                           ──────────┼──► Expediente\n│                                                              │\n└─────────────────────────────────────────────────────────────┘\n```\n\n**Vinculación en el Sistema:**\n\n```yaml\nexpediente:\n  identificador: \"EXP-2024-00123\"\n  procedimiento:\n    codigo_SIA: \"991234\"  # Sistema Información Administrativa\n    nombre: \"Licencia de apertura de actividad\"\n    normativa_reguladora: \"Ordenanza municipal de actividades\"\n    plazo_resolucion: \"3 meses\"\n    silencio: \"Positivo\"\n  tramites_realizados:\n    - codigo: \"INI01\"\n      nombre: \"Solicitud\"\n      fecha: \"2024-01-10\"\n      documento: \"DOC-001\"\n    - codigo: \"INS02\"\n      nombre: \"Informe técnico\"\n      fecha: \"2024-01-20\"\n      documento: \"DOC-002\"\n```\n\n**Trazabilidad:**\n- Cada trámite del procedimiento genera documentos\n- Los documentos se incorporan al expediente\n- El expediente refleja el estado del procedimiento\n- Cumplimiento de plazos verificable"
    },
    {
        "input": "¿Qué son los expedientes híbridos y cómo se gestionan?",
        "output": "Un expediente híbrido contiene documentos en soporte papel y electrónico:\n\n**Definición:**\nExpediente compuesto por documentos electrónicos y documentos en papel que no han sido digitalizados o cuyo original en papel debe conservarse.\n\n**Casos Comunes:**\n- Documentos históricos que deben conservarse en papel\n- Expedientes iniciados en papel, continuados electrónicamente\n- Documentos con firmas manuscritas de valor probatorio especial\n- Planos o documentos de gran formato\n\n**Gestión del Expediente Híbrido:**\n\n```\n┌─────────────────────────────────────────────────────────────┐\n│              EXPEDIENTE HÍBRIDO EXP-2024-00123              │\n├─────────────────────────────────────────────────────────────┤\n│                                                              │\n│  COMPONENTE ELECTRÓNICO (Sistema gestor)                    │\n│  ├── Índice electrónico completo                            │\n│  ├── Documentos nativos electrónicos                        │\n│  ├── Copias digitalizadas de documentos papel               │\n│  └── Metadatos de TODOS los documentos                      │\n│                                                              │\n│  COMPONENTE FÍSICO (Archivo papel)                          │\n│  ├── Documentos originales en papel                         │\n│  ├── Carpetilla con referencia al expediente electrónico    │\n│  └── Ubicación: Armario 5, Balda 3, Caja 12                 │\n│                                                              │\n│  VINCULACIÓN                                                 │\n│  ├── Documento electrónico → Referencia a original papel    │\n│  └── Documento papel → Copia digitalizada en sistema        │\n│                                                              │\n└─────────────────────────────────────────────────────────────┘\n```\n\n**Metadatos Adicionales para Híbridos:**\n```yaml\ndocumento:\n  identificador: \"DOC-003\"\n  titulo: \"Escritura notarial original\"\n  soporte: \"Papel\"  # Indicador clave\n  tiene_copia_digitalizada: true\n  copia_digitalizada: \"DOC-003-COPIA\"\n  ubicacion_fisica:\n    archivo: \"Archivo Central\"\n    deposito: \"D-05\"\n    estanteria: \"E-12\"\n    caja: \"C-045\"\n    expediente_fisico: \"EXP-2024-00123\"\n  motivo_conservacion_papel: \"Escritura pública original\"\n```\n\n**Recomendaciones:**\n1. Tender a la eliminación del papel cuando sea legal\n2. Digitalización certificada cuando sea posible\n3. Mantener índice electrónico único y completo\n4. Sincronizar ubicaciones físicas y electrónicas\n5. Plan de digitalización progresiva"
    },
    {
        "input": "¿Cómo se audita un expediente administrativo?",
        "output": "La auditoría del expediente garantiza trazabilidad y cumplimiento:\n\n**Elementos Auditados:**\n\n**1. Trazabilidad de Acciones:**\n```\n[REGISTRO DE AUDITORÍA - EXP-2024-00123]\n\nFecha/Hora          | Usuario      | Acción                | Detalle\n--------------------|--------------|----------------------|------------------\n2024-01-10 09:15:00 | MGARCÍA      | Apertura expediente  | Procedimiento: Licencia\n2024-01-10 09:16:30 | MGARCÍA      | Incorporar documento | DOC-001 (Solicitud)\n2024-01-10 09:17:00 | SISTEMA      | Validación firma     | DOC-001: Firma válida\n2024-01-12 11:30:00 | JLOPEZ       | Consulta expediente  | Vista completa\n2024-01-15 14:00:00 | ARUIZ        | Incorporar documento | DOC-002 (Informe)\n2024-01-15 14:01:00 | ARUIZ        | Firma documento      | DOC-002: XAdES-T\n2024-01-20 10:00:00 | MGARCÍA      | Cambio estado        | \"Pendiente resolución\"\n```\n\n**2. Integridad de Documentos:**\n```\n[VERIFICACIÓN DE INTEGRIDAD]\n\nDocumento           | Hash Original      | Hash Actual        | Estado\n--------------------|--------------------|--------------------|--------\nDOC-001 Solicitud   | SHA256:3a7bd3...   | SHA256:3a7bd3...   | ✓ OK\nDOC-002 Informe     | SHA256:8c2ef4...   | SHA256:8c2ef4...   | ✓ OK\nDOC-003 Resolución  | SHA256:1f5a92...   | SHA256:1f5a92...   | ✓ OK\n```\n\n**3. Validez de Firmas:**\n- Estado del certificado en momento de firma\n- Sello de tiempo asociado\n- Cadena de confianza completa\n\n**4. Cumplimiento de Plazos:**\n```\nProcedimiento: Licencia de apertura\nPlazo máximo: 3 meses\nFecha inicio: 10/01/2024\nFecha límite: 10/04/2024\nFecha resolución: 15/02/2024\nEstado: ✓ Dentro de plazo\n```\n\n**Informes de Auditoría:**\n- Informe de accesos por período\n- Informe de modificaciones\n- Verificación de integridad bajo demanda\n- Cumplimiento de retención documental\n\n**Conservación del Log:**\n- Mínimo igual al expediente\n- Inmutable (append-only)\n- Firmado periódicamente"
    },
]

# =============================================================================
# COMBINACIÓN DE TODOS LOS EJEMPLOS
# =============================================================================
ALL_DOCUMENT_EXPERT_EXAMPLES: List[Dict[str, str]] = (
    DOCUMENT_TYPES_EXAMPLES +
    METADATA_EXAMPLES +
    LIFECYCLE_EXAMPLES +
    RETENTION_EXAMPLES +
    WORKFLOW_EXAMPLES +
    VERSION_CONTROL_EXAMPLES +
    ACCESS_CONTROL_EXAMPLES +
    SEARCH_EXAMPLES +
    COMPLIANCE_EXAMPLES +
    DIGITIZATION_EXAMPLES +
    EXPEDIENTES_ADMINISTRATIVOS_EXAMPLES
)


def get_document_expert_examples(
    categories: List[str] = None,
    limit: int = None
) -> List[Dict[str, str]]:
    """
    Obtiene ejemplos del dataset de experto documental.

    Args:
        categories: Lista de categorías a incluir (None = todas)
                   Opciones: types, metadata, lifecycle, retention,
                            workflow, versions, access, search,
                            compliance, digitization
        limit: Número máximo de ejemplos (None = todos)

    Returns:
        Lista de ejemplos {input, output}
    """
    category_map = {
        "types": DOCUMENT_TYPES_EXAMPLES,
        "metadata": METADATA_EXAMPLES,
        "lifecycle": LIFECYCLE_EXAMPLES,
        "retention": RETENTION_EXAMPLES,
        "workflow": WORKFLOW_EXAMPLES,
        "versions": VERSION_CONTROL_EXAMPLES,
        "access": ACCESS_CONTROL_EXAMPLES,
        "search": SEARCH_EXAMPLES,
        "compliance": COMPLIANCE_EXAMPLES,
        "digitization": DIGITIZATION_EXAMPLES,
        "expedientes": EXPEDIENTES_ADMINISTRATIVOS_EXAMPLES,
    }

    if categories:
        examples = []
        for cat in categories:
            if cat in category_map:
                examples.extend(category_map[cat])
    else:
        examples = ALL_DOCUMENT_EXPERT_EXAMPLES.copy()

    if limit:
        examples = examples[:limit]

    return examples


# Estadísticas del dataset
DATASET_STATS = {
    "total_examples": len(ALL_DOCUMENT_EXPERT_EXAMPLES),
    "categories": {
        "types": len(DOCUMENT_TYPES_EXAMPLES),
        "metadata": len(METADATA_EXAMPLES),
        "lifecycle": len(LIFECYCLE_EXAMPLES),
        "retention": len(RETENTION_EXAMPLES),
        "workflow": len(WORKFLOW_EXAMPLES),
        "versions": len(VERSION_CONTROL_EXAMPLES),
        "access": len(ACCESS_CONTROL_EXAMPLES),
        "search": len(SEARCH_EXAMPLES),
        "compliance": len(COMPLIANCE_EXAMPLES),
        "digitization": len(DIGITIZATION_EXAMPLES),
        "expedientes": len(EXPEDIENTES_ADMINISTRATIVOS_EXAMPLES),
    },
    "avg_input_length": sum(len(e["input"]) for e in ALL_DOCUMENT_EXPERT_EXAMPLES) // len(ALL_DOCUMENT_EXPERT_EXAMPLES),
    "avg_output_length": sum(len(e["output"]) for e in ALL_DOCUMENT_EXPERT_EXAMPLES) // len(ALL_DOCUMENT_EXPERT_EXAMPLES),
}

export interface AgentUseCase {
  agentId: string
  title: string
  description: string
  examples: string[]
  icon?: string
  benefits: string[]
}

export const agentUseCases: Record<string, AgentUseCase> = {
  financial_analysis_agent: {
    agentId: 'financial_analysis_agent',
    title: 'Análisis Financiero',
    description: 'Analiza documentos financieros, facturas y pagos para proporcionar insights y recomendaciones.',
    examples: [
      'Muéstrame todas las facturas vencidas',
      '¿Cuál es mi flujo de caja este mes?',
      'Analiza los pagos pendientes por cliente',
      'Resume los gastos del último trimestre',
      'Identifica oportunidades de ahorro'
    ],
    icon: 'IconCurrencyDollar',
    benefits: [
      'Identifica pagos vencidos automáticamente',
      'Prioriza cobros según urgencia',
      'Analiza tendencias de gastos e ingresos',
      'Genera reportes financieros personalizados'
    ]
  },
  
  legal_compliance_agent: {
    agentId: 'legal_compliance_agent',
    title: 'Cumplimiento Legal',
    description: 'Revisa documentos para verificar cumplimiento normativo y requisitos legales.',
    examples: [
      'Verifica si este contrato cumple con GDPR',
      'Identifica cláusulas de riesgo en este acuerdo',
      'Revisa términos de confidencialidad',
      'Compara este contrato con nuestra plantilla estándar',
      '¿Qué obligaciones legales tenemos pendientes?'
    ],
    icon: 'IconScale',
    benefits: [
      'Detecta riesgos legales potenciales',
      'Asegura cumplimiento normativo',
      'Identifica cláusulas problemáticas',
      'Mantiene registro de obligaciones legales'
    ]
  },
  
  document_analyzer_agent: {
    agentId: 'document_analyzer_agent',
    title: 'Análisis de Documentos',
    description: 'Extrae información clave, genera resúmenes y analiza el contenido de documentos.',
    examples: [
      'Resume los puntos clave de este documento',
      'Extrae todas las fechas importantes',
      'Identifica las personas mencionadas',
      'Compara estos dos documentos',
      '¿Cuáles son las conclusiones principales?'
    ],
    icon: 'IconFileText',
    benefits: [
      'Ahorra tiempo en lectura de documentos largos',
      'Extrae información estructurada',
      'Identifica información crítica automáticamente',
      'Facilita la comparación entre documentos'
    ]
  },
  
  rag_assistant_agent: {
    agentId: 'rag_assistant_agent',
    title: 'Asistente RAG',
    description: 'Responde preguntas basándose en tu base de conocimiento de documentos.',
    examples: [
      '¿Cuál es nuestra política de devoluciones?',
      'Busca información sobre el proyecto X',
      '¿Qué dice el manual sobre este procedimiento?',
      'Encuentra todos los documentos relacionados con el cliente Y',
      '¿Cuáles son nuestros términos de servicio actuales?'
    ],
    icon: 'IconRobot',
    benefits: [
      'Acceso instantáneo a información en documentos',
      'Respuestas contextualizadas y precisas',
      'Búsqueda semántica avanzada',
      'Conecta información de múltiples fuentes'
    ]
  },
  
  digital_signature_agent: {
    agentId: 'digital_signature_agent',
    title: 'Firma Digital',
    description: 'Gestiona flujos de firma digital y seguimiento de documentos para firmar.',
    examples: [
      'Prepara este contrato para firma',
      'Muestra el estado de las firmas pendientes',
      'Envía recordatorio a los firmantes',
      'Verifica las firmas completadas',
      'Genera reporte de documentos firmados este mes'
    ],
    icon: 'IconSignature',
    benefits: [
      'Automatiza flujos de firma',
      'Seguimiento en tiempo real',
      'Recordatorios automáticos',
      'Validación de firmas digitales'
    ]
  }
}

export function getAgentUseCase(agentId: string): AgentUseCase | undefined {
  return agentUseCases[agentId]
}

export function getQuickPrompts(agentId: string): string[] {
  const useCase = agentUseCases[agentId]
  return useCase?.examples.slice(0, 3) || []
}
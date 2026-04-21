/**
 * Agent Builder — mock layer (frontend-only, localStorage)
 *
 * Persists user-created agents to localStorage so the UI is fully navigable
 * without any backend. Replace with real API calls once `/api/v1/agents` lands.
 */

const STORAGE_KEY = 'nouxcube.user_agents.v1'

export type ModelRole = 'PLANNER' | 'CHAT'
export type Visibility = 'private' | 'shared'

export interface UserAgentMock {
  id: string
  name: string
  description: string
  icon: string
  color: string
  system_prompt: string
  allowed_tools: string[]
  model_role: ModelRole
  temperature: number
  scope: {
    folders: string[]
    roles: string[]
  }
  visibility: Visibility
  usage_count: number
  created_at: string
  updated_at: string
}

export interface ToolMeta {
  id: string
  label: string
  description: string
  icon: string
  category: 'core' | 'knowledge' | 'external' | 'output' | 'advanced'
  featureGated?: boolean
}

export const TOOL_CATALOG: ToolMeta[] = [
  { id: 'smart_search',         label: 'Búsqueda en documentos',   description: 'Híbrida (Weaviate + grafo) sobre documentos indexados', icon: '📄', category: 'core' },
  { id: 'graph_rag',            label: 'Grafo de conocimiento',    description: 'Recuperación vía TrustGraph con citación de fuentes',   icon: '🕸️', category: 'knowledge' },
  { id: 'get_document_content', label: 'Leer documento',           description: 'Lee el contenido completo de un documento por ID',     icon: '📖', category: 'knowledge' },
  { id: 'structural_query',     label: 'Consulta estructural',     description: 'Contar, listar y filtrar sobre FalkorDB',              icon: '🔢', category: 'knowledge' },
  { id: 'analyze_domain',       label: 'Análisis por dominio',     description: 'Especialistas (fiscal, legal, médico, documental)',    icon: '🧪', category: 'advanced' },
  { id: 'search_jurisprudence', label: 'Jurisprudencia (CENDOJ)',  description: 'Busca sentencias en la base oficial CENDOJ',           icon: '⚖️', category: 'external', featureGated: true },
  { id: 'web_search',           label: 'Internet',                 description: 'Tavily + DuckDuckGo como fallback',                    icon: '🌐', category: 'external', featureGated: true },
  { id: 'list_sources',         label: 'Descubrir fuentes',        description: 'Enumera fuentes y conectores disponibles',             icon: '🗂️', category: 'core' },
  { id: 'query_connector',      label: 'Consultar conectores',     description: 'SharePoint, Drive, y otros conectores externos',       icon: '🔌', category: 'external', featureGated: true },
  { id: 'generate_document',    label: 'Generar documento',        description: 'Crea un documento desde plantilla',                    icon: '📝', category: 'output' },
  { id: 'forge_document',       label: 'Forjar PDF',               description: 'Exporta a PDF con estilo profesional',                 icon: '📎', category: 'output' },
  { id: 'send_email',           label: 'Enviar email',             description: 'Notificaciones por correo',                            icon: '✉️', category: 'output' },
  { id: 'verified_generation',  label: 'Generación verificada',    description: 'Verificación claim-by-claim con fuentes',              icon: '✅', category: 'advanced' },
  { id: 'predictive_analysis',  label: 'Análisis predictivo',      description: 'Sub-grafo de predicción con factores',                 icon: '🔮', category: 'advanced' },
  { id: 'generate_knowledge_report', label: 'Informe de conocimiento', description: 'Reporte estructurado con KPIs y citaciones',     icon: '📊', category: 'output' },
]

export const FOLDER_SUGGESTIONS = [
  'Legal/Laboral', 'Legal/Mercantil', 'Legal/Civil',
  'Fiscal/IVA', 'Fiscal/IRPF', 'Fiscal/Sociedades',
  'RRHH/Nóminas', 'RRHH/Contratos', 'RRHH/Formación',
  'Clínica/Historias', 'Clínica/Protocolos',
  'Financiero/Facturas', 'Financiero/Bancos',
]

export const ROLE_SUGGESTIONS = ['admin', 'legal', 'jurista', 'fiscal', 'rrhh', 'medico', 'financiero', 'direccion']

const SEED_AGENTS: UserAgentMock[] = [
  {
    id: 'seed-juridico-laboral',
    name: 'Jurídico Laboral',
    description: 'Contratos laborales, despidos, convenios y jurisprudencia laboral',
    icon: '⚖️',
    color: '#6366f1',
    system_prompt: 'Eres un asesor jurídico especializado en derecho laboral español. Cita siempre el Estatuto de los Trabajadores y jurisprudencia del Tribunal Supremo. Sé preciso con los artículos.',
    allowed_tools: ['smart_search', 'graph_rag', 'search_jurisprudence', 'generate_document'],
    model_role: 'CHAT',
    temperature: 0.3,
    scope: { folders: ['Legal/Laboral', 'RRHH/Contratos'], roles: ['jurista', 'legal'] },
    visibility: 'shared',
    usage_count: 14,
    created_at: '2026-04-10T09:30:00Z',
    updated_at: '2026-04-18T12:00:00Z',
  },
  {
    id: 'seed-analista-fiscal',
    name: 'Analista Fiscal',
    description: 'IVA, IRPF, modelos trimestrales y resoluciones de la AEAT',
    icon: '💰',
    color: '#10b981',
    system_prompt: 'Eres un asesor fiscal. Responde con referencias a la normativa tributaria vigente. Incluye siempre el modelo y plazo aplicable.',
    allowed_tools: ['smart_search', 'graph_rag', 'structural_query'],
    model_role: 'CHAT',
    temperature: 0.2,
    scope: { folders: ['Fiscal/IVA', 'Fiscal/IRPF', 'Financiero/Facturas'], roles: ['fiscal'] },
    visibility: 'shared',
    usage_count: 7,
    created_at: '2026-04-12T14:00:00Z',
    updated_at: '2026-04-19T10:15:00Z',
  },
  {
    id: 'seed-revisor-medico',
    name: 'Revisor Médico',
    description: 'Análisis de historias clínicas y protocolos médicos',
    icon: '🏥',
    color: '#ef4444',
    system_prompt: 'Eres un asistente clínico. Nunca sustituyas el juicio médico; tu rol es resumir y señalar aspectos relevantes en historias clínicas.',
    allowed_tools: ['smart_search', 'graph_rag', 'get_document_content', 'verified_generation'],
    model_role: 'CHAT',
    temperature: 0.4,
    scope: { folders: ['Clínica/Historias', 'Clínica/Protocolos'], roles: ['medico'] },
    visibility: 'private',
    usage_count: 3,
    created_at: '2026-04-15T08:00:00Z',
    updated_at: '2026-04-20T11:30:00Z',
  },
]

function now(): string {
  return new Date().toISOString()
}

function uid(): string {
  return `ua-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function readAll(): UserAgentMock[] {
  if (typeof window === 'undefined') return SEED_AGENTS
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(SEED_AGENTS))
      return SEED_AGENTS
    }
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : SEED_AGENTS
  } catch {
    return SEED_AGENTS
  }
}

function writeAll(agents: UserAgentMock[]): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(agents))
}

export const AgentsMock = {
  list(): UserAgentMock[] {
    return readAll().sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  },

  get(id: string): UserAgentMock | undefined {
    return readAll().find((a) => a.id === id)
  },

  create(partial: Omit<UserAgentMock, 'id' | 'created_at' | 'updated_at' | 'usage_count'>): UserAgentMock {
    const agent: UserAgentMock = {
      ...partial,
      id: uid(),
      usage_count: 0,
      created_at: now(),
      updated_at: now(),
    }
    writeAll([agent, ...readAll()])
    return agent
  },

  update(id: string, changes: Partial<UserAgentMock>): UserAgentMock | undefined {
    const all = readAll()
    const idx = all.findIndex((a) => a.id === id)
    if (idx === -1) return undefined
    const updated = { ...all[idx], ...changes, updated_at: now() }
    all[idx] = updated
    writeAll(all)
    return updated
  },

  remove(id: string): boolean {
    const all = readAll()
    const next = all.filter((a) => a.id !== id)
    if (next.length === all.length) return false
    writeAll(next)
    return true
  },

  duplicate(id: string): UserAgentMock | undefined {
    const src = readAll().find((a) => a.id === id)
    if (!src) return undefined
    return AgentsMock.create({
      ...src,
      name: `${src.name} (copia)`,
      visibility: 'private',
    })
  },

  reset(): void {
    if (typeof window === 'undefined') return
    window.localStorage.removeItem(STORAGE_KEY)
  },
}

export interface DraftConfig {
  system_prompt: string
  allowed_tools: string[]
  model_role: ModelRole
  temperature: number
}

export interface MockSSEEvent {
  type: 'thinking' | 'tool_call' | 'tool_result' | 'token' | 'done'
  content?: string
  tool?: string
  args?: Record<string, unknown>
  latency_ms?: number
}

/**
 * Simulates an SSE stream for the playground.
 * Produces a realistic-looking trace based on the query and the agent's tools.
 */
export async function* mockStreamResponse(
  query: string,
  draft: DraftConfig,
  signal?: AbortSignal,
): AsyncGenerator<MockSSEEvent> {
  const sleep = (ms: number) =>
    new Promise<void>((resolve, reject) => {
      const t = setTimeout(resolve, ms)
      signal?.addEventListener('abort', () => {
        clearTimeout(t)
        reject(new DOMException('aborted', 'AbortError'))
      })
    })

  yield { type: 'thinking', content: 'Clasificando consulta…' }
  await sleep(180)

  const q = query.toLowerCase()
  const tools = draft.allowed_tools

  const callable = tools.filter((t) => t !== 'terminate')
  const plan: string[] = []
  if (callable.includes('smart_search')) plan.push('smart_search')
  if (q.match(/\b(sentencia|jurisprudencia|tribunal|art[ií]culo)\b/) && callable.includes('search_jurisprudence')) plan.push('search_jurisprudence')
  if (q.match(/\b(relación|entidad|grafo|conexión)\b/) && callable.includes('graph_rag')) plan.push('graph_rag')
  if (q.match(/\b(redacta|genera|escribe|documento|contrato)\b/) && callable.includes('generate_document')) plan.push('generate_document')
  if (plan.length === 0 && callable.length > 0) plan.push(callable[0])

  for (const tool of plan) {
    yield { type: 'thinking', content: `Planificando uso de ${tool}…` }
    await sleep(120)
    yield { type: 'tool_call', tool, args: { query } }
    const latency = 150 + Math.floor(Math.random() * 400)
    await sleep(latency)
    yield { type: 'tool_result', tool, latency_ms: latency, content: `${tool} devolvió resultados` }
  }

  yield { type: 'thinking', content: 'Sintetizando respuesta…' }
  await sleep(250)

  const temperamentLabel = draft.temperature < 0.3 ? 'preciso' : draft.temperature > 0.7 ? 'creativo' : 'equilibrado'
  const response = [
    `Respuesta simulada (modo ${temperamentLabel}, rol ${draft.model_role}):`,
    ``,
    `Consulta: "${query}"`,
    ``,
    `Herramientas usadas: ${plan.join(' → ') || '(ninguna)'}`,
    ``,
    plan.length > 0
      ? `En producción, el agente ejecutaría este plan con el prompt definido:\n> ${draft.system_prompt.slice(0, 160)}${draft.system_prompt.length > 160 ? '…' : ''}`
      : `El agente no tiene herramientas compatibles con esta consulta; responderá desde el conocimiento del modelo.`,
  ].join('\n')

  for (const token of response.split(/(\s+)/)) {
    yield { type: 'token', content: token }
    await sleep(15 + Math.random() * 25)
  }

  yield { type: 'done' }
}

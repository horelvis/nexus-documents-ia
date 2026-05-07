export type AgentScope = {
  folders?: string[]
  semantic_types?: string[]
  person_filter?: string[]
  entity_filters?: string[]
  date_range?: { from?: string | null; to?: string | null } | null
  quality_min?: number | null
  connector_ids?: string[]
}

export type AgentPersona = {
  style: 'concise' | 'detailed' | 'conversational'
  language: 'es' | 'en' | 'auto'
  instructions: string
}

export type AgentModelRole = 'PLANNER' | 'CHAT'

export type Agent = {
  id: string
  name: string
  slug: string
  description: string | null
  icon: string
  color: string
  persona: AgentPersona
  scope: AgentScope
  is_active: boolean
  is_seed: boolean
  model_role: AgentModelRole
  temperature: number
  usage_count: number
  owner_id: string
  created_at: string
  updated_at: string
}

export type AgentCreatePayload = {
  name: string
  slug: string
  description?: string | null
  icon?: string
  color?: string
  persona?: AgentPersona
  scope?: AgentScope
  is_active?: boolean
  model_role?: AgentModelRole
  temperature?: number
}

export type AgentUpdatePayload = Partial<Omit<AgentCreatePayload, 'slug'>>

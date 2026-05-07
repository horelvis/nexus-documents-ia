/**
 * Real backend client for the admin-curated agents catalog.
 *
 * Follows the project's "Simple UI Pattern": every method returns
 * { data, error, status } via apiClient. Callers consume:
 *
 *   const response = await agentsService.list({ active: true })
 *   if (response.error) setError(response.error)
 *   else setAgents(response.data)
 */
import { apiClient } from '@/lib/api-client'
import type { Agent, AgentCreatePayload, AgentUpdatePayload } from '@/lib/types/agent'

// apiClient already prepends /api/v1 via its baseURL — paths here are relative.
const BASE = '/agents'

export const agentsService = {
  list(opts?: { active?: boolean; slug?: string; order_by?: 'name' | 'usage_count' }) {
    const params = new URLSearchParams()
    if (opts?.active !== undefined) params.set('active', String(opts.active))
    if (opts?.slug) params.set('slug', opts.slug)
    if (opts?.order_by) params.set('order_by', opts.order_by)
    // No trailing slash — backend route is defined as `""` so we don't trigger
    // the FastAPI redirect-with-absolute-Location that breaks the browser.
    const url = params.toString() ? `${BASE}?${params}` : BASE
    return apiClient.get<Agent[]>(url)
  },

  get(id: string) {
    return apiClient.get<Agent>(`${BASE}/${id}`)
  },

  create(payload: AgentCreatePayload) {
    return apiClient.post<Agent>(BASE, payload)
  },

  update(id: string, payload: AgentUpdatePayload) {
    return apiClient.put<Agent>(`${BASE}/${id}`, payload)
  },

  delete(id: string) {
    return apiClient.delete<void>(`${BASE}/${id}`)
  },

  duplicate(id: string) {
    return apiClient.post<Agent>(`${BASE}/${id}/duplicate`)
  },
}

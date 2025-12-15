import { useMemo } from 'react'
import { useApiClient } from '../api-client'

/**
 * Team member as returned by the backend
 */
export interface TeamMember {
  id: string
  email: string
  full_name: string | null
  is_team_member: boolean
  is_active: boolean
  created_at: string
  role: string
  subscription_plan: string
  invited_at: string | null
}

/**
 * Team information
 */
export interface TeamInfo {
  id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
  members_count: number
  storage_quota: number
  is_active: boolean
}

/**
 * Service for team (tenant) management operations.
 *
 * Provides methods to:
 * - Get team information
 * - List team members (users in the tenant)
 * - Search for team members by name or email
 */
export class TeamService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  /**
   * Get current team information
   */
  async getTeamInfo() {
    return this.apiClient.get<TeamInfo>('/teams')
  }

  /**
   * Get all team members (users in the tenant)
   *
   * @param search - Optional search query to filter by name or email
   * @param skip - Number of items to skip (pagination)
   * @param limit - Maximum number of items to return
   */
  async getTeamMembers(search?: string, skip: number = 0, limit: number = 100) {
    const params = new URLSearchParams()
    if (search) params.append('search', search)
    if (skip > 0) params.append('skip', skip.toString())
    if (limit !== 100) params.append('limit', limit.toString())

    const query = params.toString()
    const endpoint = `/teams/members${query ? `?${query}` : ''}`

    return this.apiClient.get<TeamMember[]>(endpoint)
  }

  /**
   * Search team members by name or email
   * Convenience method for autocomplete functionality
   */
  async searchMembers(query: string, limit: number = 10) {
    if (!query || query.length < 2) {
      return { data: [], status: 200 }
    }
    return this.getTeamMembers(query, 0, limit)
  }
}

/**
 * Hook to use the Team service.
 * Provides memoized instance that updates when apiClient changes.
 */
export function useTeamService() {
  const apiClient = useApiClient()
  return useMemo(() => new TeamService(apiClient), [apiClient])
}

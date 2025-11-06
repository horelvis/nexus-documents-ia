/**
 * Template Editor Service - API client for Google Docs editing
 * Following Alfresco ECM pattern
 */

export interface EditSession {
  id: string
  template_id: string
  template_name: string
  user_id: string
  user_email: string
  tenant_id: string
  google_doc_id: string
  google_doc_url: string
  google_doc_edit_url: string
  created_at: string
  expires_at: string
  last_activity: string
  completed_at?: string
  status: 'active' | 'completed' | 'expired' | 'error' | 'cancelled'
  changes_detected?: boolean
  original_content_hash?: string
  final_content_hash?: string
  error_message?: string
  cleanup_completed?: boolean
}

export interface CreateEditSessionRequest {
  template_id: string
  template_name: string
  template_content: string
  user_id: string
  user_email: string
  tenant_id: string
}

export interface FinishEditSessionRequest {
  user_id: string
  force_sync?: boolean
}

export interface ExtendSessionRequest {
  user_id: string
  hours: number
}

export interface EditSessionStats {
  total_sessions: number
  active_sessions: number
  completed_sessions: number
  expired_sessions: number
  cleanup_errors: number
  sessions_by_status?: Record<string, number>
  avg_session_duration_minutes?: number
  google_docs_deleted?: number
  successfully_cleaned?: number
}

class TemplateEditorService {
  private baseUrl = '/api/template-editor'

  /**
   * Create new editing session with temporary Google Doc
   */
  async createEditSession(request: CreateEditSessionRequest): Promise<EditSession> {
    const response = await fetch(`${this.baseUrl}/sessions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to create edit session')
    }

    return response.json()
  }

  /**
   * Get edit session details
   */
  async getEditSession(sessionId: string, userId?: string): Promise<EditSession> {
    const url = new URL(`${this.baseUrl}/sessions/${sessionId}`, window.location.origin)
    if (userId) {
      url.searchParams.set('user_id', userId)
    }

    const response = await fetch(url.toString())

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Edit session not found')
      }
      const error = await response.json()
      throw new Error(error.detail || 'Failed to get edit session')
    }

    return response.json()
  }

  /**
   * Finish editing session - sync changes and cleanup
   */
  async finishEditSession(
    sessionId: string,
    request: FinishEditSessionRequest
  ): Promise<{
    session_id: string
    status: string
    changes_detected: boolean
    sync_result: any
    cleanup_success: boolean
    completed_at: string
  }> {
    const response = await fetch(`${this.baseUrl}/sessions/${sessionId}/finish`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to finish edit session')
    }

    return response.json()
  }

  /**
   * Extend session expiration time
   */
  async extendSession(
    sessionId: string,
    request: ExtendSessionRequest
  ): Promise<EditSession> {
    const response = await fetch(`${this.baseUrl}/sessions/${sessionId}/extend`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to extend session')
    }

    return response.json()
  }

  /**
   * Cancel editing session and cleanup
   */
  async cancelEditSession(sessionId: string, userId: string): Promise<void> {
    const response = await fetch(
      `${this.baseUrl}/sessions/${sessionId}?user_id=${userId}`,
      {
        method: 'DELETE',
      }
    )

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to cancel edit session')
    }
  }

  /**
   * Get all sessions for a user
   */
  async getUserSessions(
    userId: string,
    tenantId: string,
    includeCompleted = false
  ): Promise<EditSession[]> {
    const url = new URL(`${this.baseUrl}/sessions/user/${userId}`, window.location.origin)
    url.searchParams.set('tenant_id', tenantId)
    if (includeCompleted) {
      url.searchParams.set('include_completed', 'true')
    }

    const response = await fetch(url.toString())

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to get user sessions')
    }

    return response.json()
  }

  /**
   * Get edit session statistics
   */
  async getStats(tenantId?: string): Promise<EditSessionStats> {
    const url = new URL(`${this.baseUrl}/sessions/stats`, window.location.origin)
    if (tenantId) {
      url.searchParams.set('tenant_id', tenantId)
    }

    const response = await fetch(url.toString())

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to get session stats')
    }

    return response.json()
  }

  /**
   * Manually trigger cleanup of expired sessions
   */
  async cleanupExpiredSessions(): Promise<EditSessionStats> {
    const response = await fetch(`${this.baseUrl}/sessions/cleanup`, {
      method: 'POST',
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to cleanup expired sessions')
    }

    return response.json()
  }

  /**
   * Get service health status
   */
  async getHealthStatus(): Promise<{
    status: string
    service: string
    version: string
    checks: Record<string, string>
  }> {
    const response = await fetch('/api/template-editor/health')

    if (!response.ok) {
      throw new Error('Template editor service is unhealthy')
    }

    return response.json()
  }

  /**
   * Get service information and capabilities
   */
  async getServiceInfo(): Promise<{
    service: string
    description: string
    version: string
    capabilities: string[]
    endpoints: Record<string, string>
    configuration: Record<string, any>
  }> {
    const response = await fetch('/api/template-editor/info')

    if (!response.ok) {
      throw new Error('Failed to get service info')
    }

    return response.json()
  }

  /**
   * Calculate time remaining for a session
   */
  calculateTimeRemaining(expiresAt: string): {
    hours: number
    minutes: number
    isExpired: boolean
    totalMinutes: number
  } {
    const now = new Date()
    const expiry = new Date(expiresAt)
    const diffMs = expiry.getTime() - now.getTime()
    
    if (diffMs <= 0) {
      return {
        hours: 0,
        minutes: 0,
        isExpired: true,
        totalMinutes: 0
      }
    }

    const totalMinutes = Math.floor(diffMs / (1000 * 60))
    const hours = Math.floor(totalMinutes / 60)
    const minutes = totalMinutes % 60

    return {
      hours,
      minutes,
      isExpired: false,
      totalMinutes
    }
  }

  /**
   * Format session duration for display
   */
  formatDuration(createdAt: string, completedAt?: string): string {
    const start = new Date(createdAt)
    const end = completedAt ? new Date(completedAt) : new Date()
    const diffMs = end.getTime() - start.getTime()
    const minutes = Math.floor(diffMs / (1000 * 60))

    if (minutes < 60) {
      return `${minutes}m`
    }

    const hours = Math.floor(minutes / 60)
    const remainingMinutes = minutes % 60

    if (hours < 24) {
      return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`
    }

    const days = Math.floor(hours / 24)
    const remainingHours = hours % 24
    return `${days}d ${remainingHours}h`
  }
}

// Export singleton instance
export const templateEditorService = new TemplateEditorService()
export default templateEditorService
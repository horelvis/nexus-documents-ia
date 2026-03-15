/**
 * Type stub for @/contexts/user-context.
 * Actual implementation lives in the consuming app (on-premise or saas).
 */
export interface BackendUser {
  id: string
  full_name?: string
  name?: string
  email?: string
  tenant_id?: string
  roles?: string[]
}

export declare function useBackendUser(): {
  backendUser: BackendUser | null
}

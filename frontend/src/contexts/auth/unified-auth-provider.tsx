'use client'

/**
 * Unified Authentication Provider
 *
 * On-premise auth provider for SSO (OIDC/SAML/LDAP).
 */

import { createContext, useContext, type ReactNode } from 'react'
import { SSOAuthProvider, useSSOAuth } from './sso-auth-context'
import type { UnifiedAuthContextType } from './types'

const UnifiedAuthContext = createContext<UnifiedAuthContextType | undefined>(undefined)

interface UnifiedAuthProviderProps {
  children: ReactNode
}

/**
 * Adapter that provides SSO context as UnifiedAuthContextType
 */
function SSOAuthAdapter({ children }: { children: ReactNode }) {
  const ssoAuth = useSSOAuth()

  return (
    <UnifiedAuthContext.Provider value={ssoAuth}>
      {children}
    </UnifiedAuthContext.Provider>
  )
}

/**
 * Unified Auth Provider
 *
 * Wraps the app and provides a consistent SSO auth interface.
 *
 * Usage:
 *   <UnifiedAuthProvider>
 *     <App />
 *   </UnifiedAuthProvider>
 */
export function UnifiedAuthProvider({ children }: UnifiedAuthProviderProps) {
  return (
    <SSOAuthProvider>
      <SSOAuthAdapter>{children}</SSOAuthAdapter>
    </SSOAuthProvider>
  )
}

/**
 * Hook to access unified auth context.
 *
 * Works with the on-premise SSO provider.
 */
export function useUnifiedAuth(): UnifiedAuthContextType {
  const context = useContext(UnifiedAuthContext)
  if (context === undefined) {
    throw new Error('useUnifiedAuth must be used within a UnifiedAuthProvider')
  }
  return context
}

/**
 * Convenience hooks
 */
export function useAuth() {
  return useUnifiedAuth()
}

export function useAuthState() {
  const { authState } = useUnifiedAuth()
  return authState
}

export function useIsAuthenticated() {
  const { isAuthenticated } = useUnifiedAuth()
  return isAuthenticated
}

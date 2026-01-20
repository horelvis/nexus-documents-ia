/**
 * Authentication Context Module
 *
 * Provides unified authentication for both SaaS (Clerk) and
 * on-premise (SSO) deployment modes.
 *
 * Usage:
 *   import { UnifiedAuthProvider, useAuth } from '@/contexts/auth'
 *
 *   // In root layout
 *   <UnifiedAuthProvider>
 *     <App />
 *   </UnifiedAuthProvider>
 *
 *   // In components
 *   const { isAuthenticated, backendUser, logout } = useAuth()
 */

// Types
export type {
  AuthProviderType,
  SSOTokens,
  AuthIdentity,
  AuthState,
  UnifiedAuthContextType,
  AuthGuardProps,
} from './types'

// Unified provider (main export)
export {
  UnifiedAuthProvider,
  useUnifiedAuth,
  useAuth,
  useAuthState,
  useIsAuthenticated,
} from './unified-auth-provider'

// SSO provider (for direct usage if needed)
export { SSOAuthProvider, useSSOAuth } from './sso-auth-context'

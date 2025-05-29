// frontend/app/utils/hooks/use-user-context.tsx
import { createContext, useContext, ReactNode } from 'react'
import { useUser as useClerkUser } from '@clerk/remix'

// Tipos para el usuario del backend
export interface BackendUser {
  id: string
  clerk_id: string
  username?: string
  email?: string
  roles?: Array<{ id: string; name: string }>
  is_superuser?: boolean
  tenant_id?: string
  created_at?: string
  updated_at?: string
}

// Tipos para el contexto completo del usuario
export interface UserContextData {
  // Usuario de Clerk (siempre disponible si está autenticado)
  clerkUser: any | null
  isSignedIn: boolean
  
  // Usuario del backend (puede no estar disponible en modo offline)
  backendUser: BackendUser | null
  backendConnected: boolean
  
  // Funciones de utilidad
  isAdmin: boolean
  planId: string
  hasUsername: boolean
  needsOnboarding: boolean
  
  // Estado de carga
  isLoading: boolean
  error?: string
}

const UserContext = createContext<UserContextData | null>(null)

// Hook para usar el contexto de usuario
export function useUserContext(): UserContextData {
  const context = useContext(UserContext)
  if (!context) {
    throw new Error('useUserContext must be used within a UserContextProvider')
  }
  return context
}

// Hook simplificado que siempre devuelve datos (fallback a Clerk)
export function useOptionalUser() {
  const context = useContext(UserContext)
  return context?.clerkUser || null
}

// Hook que requiere autenticación
export function useUser() {
  const user = useOptionalUser()
  if (!user) {
    throw new Error('User not authenticated')
  }
  return user
}

// Hook para datos del backend (puede ser null en modo offline)
export function useBackendUser() {
  const context = useUserContext()
  return context.backendUser
}

// Hook para verificar permisos
export function useUserPermissions() {
  const context = useUserContext()
  return {
    isAdmin: context.isAdmin,
    hasRole: (role: string) => {
      return context.backendUser?.roles?.some(r => r.name === role) || 
             context.backendUser?.is_superuser || 
             false
    },
    canAccess: (feature: string) => {
      // Lógica de permisos basada en plan/roles
      if (context.isAdmin) return true
      
      switch (feature) {
        case 'admin':
          return context.isAdmin
        case 'pro':
          return context.planId !== 'free'
        case 'enterprise':
          return context.planId === 'enterprise'
        default:
          return true
      }
    }
  }
}

// Proveedor del contexto
interface UserContextProviderProps {
  children: ReactNode
  userData: {
    backendUser: BackendUser | null
    backendConnected: boolean
    planId: string
    error?: string
  }
}

export function UserContextProvider({ children, userData }: UserContextProviderProps) {
  const { user: clerkUser, isSignedIn, isLoaded } = useClerkUser()
  
  const contextValue: UserContextData = {
    // Clerk data
    clerkUser,
    isSignedIn: isSignedIn && isLoaded,
    
    // Backend data
    backendUser: userData.backendUser,
    backendConnected: userData.backendConnected,
    
    // Computed values
    isAdmin: userData.backendUser?.is_superuser || 
             userData.backendUser?.roles?.some(r => r.name === 'admin') || 
             false,
    planId: userData.planId || 'free',
    hasUsername: Boolean(userData.backendUser?.username),
    needsOnboarding: userData.backendConnected && 
                     (!userData.backendUser?.username || !userData.backendUser?.tenant_id),
    
    // Loading state
    isLoading: !isLoaded,
    error: userData.error
  }
  
  return (
    <UserContext.Provider value={contextValue}>
      {children}
    </UserContext.Provider>
  )
}

// frontend/app/utils/backend.server.ts - FIXED VERSION
import { getAuth } from '@clerk/remix/ssr.server'
import type { LoaderFunctionArgs } from '@remix-run/node'
import { ApiService } from '#app/services/api.server'

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || 'http://localhost:8000'

/**
 * ✅ FIX: Crea una instancia del servicio API con manejo robusto de errores
 */
export async function createApiService(args: LoaderFunctionArgs): Promise<ApiService> {
  try {
    const { userId, getToken } = getAuth(args)
    
    // ✅ FIX: Verificar que el usuario esté autenticado
    if (!userId) {
      throw new Error('User not authenticated')
    }
    
    return new ApiService({
      baseUrl: BACKEND_BASE_URL,
      getToken: async () => {
        try {
          // ✅ FIX: Obtener token con manejo de errores
          const token = await getToken()
          if (!token) {
            console.warn('No token available from Clerk')
            return null
          }
          return token
        } catch (error) {
          console.error('Error obteniendo token de Clerk:', error)
          return null
        }
      },
    })
  } catch (error) {
    console.error('Error creating API service:', error)
    throw error
  }
}

/**
 * ✅ FIX: Alias para usar en acciones
 */
export async function getApiServiceForAction(args: LoaderFunctionArgs): Promise<ApiService> {
  return createApiService(args)
}

/**
 * ✅ FIX: Hook para crear el servicio API en el cliente con mejor error handling
 */
export function createClientApiService(getTokenFn: () => Promise<string | null>): ApiService {
  return new ApiService({
    baseUrl: BACKEND_BASE_URL,
    getToken: async () => {
      try {
        const token = await getTokenFn()
        return token
      } catch (error) {
        console.error('Error getting token for client API service:', error)
        return null
      }
    },
  })
}

/**
 * ✅ FIX: Utilidad para verificar conectividad del backend
 */
export async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/health`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      // ✅ FIX: Timeout corto para health check
      signal: AbortSignal.timeout(5000), // 5 segundos
    })
    
    return response.ok
  } catch (error) {
    console.warn('Backend health check failed:', error)
    return false
  }
}

/**
 * ✅ FIX: Utilidad para crear servicios con fallback
 */
export async function createApiServiceWithFallback(args: LoaderFunctionArgs): Promise<{
  apiService: ApiService | null
  isConnected: boolean
  error?: string
}> {
  try {
    const apiService = await createApiService(args)
    
    // ✅ FIX: Verificar conectividad
    const isConnected = await apiService.healthCheck()
    
    return {
      apiService: isConnected ? apiService : null,
      isConnected,
    }
  } catch (error) {
    console.error('Failed to create API service with fallback:', error)
    
    return {
      apiService: null,
      isConnected: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    }
  }
}

/**
 * ✅ FIX: Utilidad para manejar operaciones que pueden fallar gracefully
 */
export async function safeApiCall<T>(
  apiCall: () => Promise<T>,
  fallbackValue: T,
  errorMessage?: string
): Promise<{ data: T; success: boolean; error?: string }> {
  try {
    const data = await apiCall()
    return { data, success: true }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Unknown error'
    console.warn(errorMessage || 'API call failed:', errorMsg)
    
    return {
      data: fallbackValue,
      success: false,
      error: errorMsg,
    }
  }
}
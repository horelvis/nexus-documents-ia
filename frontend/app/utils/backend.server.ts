// frontend/app/utils/backend.server.ts
import { getAuth } from '@clerk/remix/ssr.server'
import type { LoaderFunctionArgs } from '@remix-run/node'
import { ApiService } from '#app/services/api.server'

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || 'http://localhost:8000'

/**
 * Crea una instancia del servicio API con el token del usuario actual
 */
export async function createApiService(args: LoaderFunctionArgs): Promise<ApiService> {
  const { userId, getToken } = getAuth(args)
  
  return new ApiService({
    baseUrl: BACKEND_BASE_URL,
    getToken: async () => {
      try {
        // Obtenemos el token JWT de Clerk
        const token = await getToken()
        return token
      } catch (error) {
        console.error('Error obteniendo token de Clerk:', error)
        return null
      }
    },
  })
}

/**
 * Utilidad para obtener el token del usuario en acciones
 */
export async function getApiServiceForAction(args: LoaderFunctionArgs): Promise<ApiService> {
  return createApiService(args)
}

/**
 * Hook personalizado para usar el servicio API en el cliente
 */
export function createClientApiService(getTokenFn: () => Promise<string | null>): ApiService {
  return new ApiService({
    baseUrl: BACKEND_BASE_URL,
    getToken: getTokenFn,
  })
}
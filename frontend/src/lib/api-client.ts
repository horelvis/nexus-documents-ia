"use client"

import { useEffect, useMemo } from 'react'
import { useAuth } from '@clerk/nextjs'
import { API_CONFIG } from './config'

export interface ApiResponse<T = any> {
  data?: T
  error?: string
  status: number
}

export interface ApiError {
  message: string
  status: number
  details?: any
}

type ApiClientError = Error & {
  response?: {
    status: number
    data: any
  }
}

const createError = (message: string, name = 'Error'): ApiClientError => {
  if (typeof Error === 'function') {
    const err = new Error(message) as ApiClientError
    err.name = name
    return err
  }
  return { name, message } as ApiClientError
}

type ApiClientError = Error & {
  response?: {
    status: number
    data: any
  }
}

class ApiClient {
  private baseURL: string

  constructor() {
    // API_CONFIG.BASE_URL incluye la base del servidor 
    // Agregamos el prefijo /api/v1 para todas las rutas
    this.baseURL = `${API_CONFIG.BASE_URL}${API_CONFIG.API_V1}`
  }

  private async getAuthToken(): Promise<string | null> {
    // En el cliente, necesitamos usar el hook de Clerk
    // Esta función será sobrescrita por el hook useApiClient
    return null
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    retryCount = 0
  ): Promise<ApiResponse<T>> {
    // Check for mock data in development/testing
    if (typeof window !== 'undefined' && endpoint === '/stripe/subscription') {
      const mockData = localStorage.getItem('mock_subscription')
      if (mockData) {
        try {
          const parsed = JSON.parse(mockData)
          const mockResponse = {
            id: 'mock_subscription_id',
            plan_id: parsed.plan_id,
            status: parsed.status,
            current_period_end: Date.now() / 1000 + 86400 * 30, // 30 days from now
            subscription_status: {
              plan_type: parsed.plan_id,
              status: parsed.status,
              is_active: parsed.status === 'active',
              is_limited: parsed.status !== 'active',
              current_period_end: null,
              can_reactivate: parsed.status === 'canceled' || parsed.status === 'past_due',
              permissions: {
                max_documents: parsed.plan_id === 'free' ? 10 : -1,
                max_monthly_uploads: parsed.plan_id === 'free' ? 5 : -1,
                can_upload_documents: true,
                can_view_documents: true,
                can_search_documents: true,
                can_use_chat: parsed.plan_id !== 'free',
                can_use_agents: parsed.plan_id !== 'free',
                can_export_documents: parsed.plan_id !== 'free',
                can_use_api: parsed.plan_id !== 'free',
                max_file_size_mb: parsed.plan_id === 'free' ? 10 : 100
              },
              message: 'Mock subscription for testing'
            }
          }
          
          console.log('🧪 Using mock subscription data:', mockResponse)
          return {
            data: mockResponse,
            status: 200
          }
        } catch (e) {
          console.error('Error parsing mock subscription data:', e)
        }
      }
    }

    try {
      const token = await this.getAuthToken()
      
      const defaultHeaders: HeadersInit = {
        'Content-Type': 'application/json',
      }

      if (token) {
        defaultHeaders.Authorization = `Bearer ${token}`
      }

      const config: RequestInit = {
        ...options,
        headers: {
          ...defaultHeaders,
          ...options.headers,
        },
      }

      const response = await fetch(`${this.baseURL}${endpoint}`, config)
      
      let data
      const contentType = response.headers.get('content-type')
      
      if (contentType && contentType.includes('application/json')) {
        data = await response.json()
      } else {
        data = await response.text()
      }

      if (!response.ok) {
        // Handle 401 Unauthorized specifically for token refresh
        if (response.status === 401 && retryCount === 0) {
          console.log('Token expired, attempting to refresh...')
          // Wait longer for Clerk to properly refresh the token
          await new Promise(resolve => setTimeout(resolve, 500))
          
          // Try the request again with retry count incremented
          return this.request<T>(endpoint, options, retryCount + 1)
        }

        const message =
          data?.detail?.message ||
          data?.detail ||
          data?.message ||
          `HTTP ${response.status}`

        return {
          error: typeof message === 'string' ? message : `HTTP ${response.status}`,
          status: response.status,
          data
        }
      }

      return {
        data,
        status: response.status,
      }
    } catch (error: any) {
      console.log('API request failed:', error)
      
      // Check if it's a network/connection error
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        // This is a connection error
        const connectionError = createError(
          'Unable to connect to the server. Please check if the backend is running.',
          'ConnectionError'
        )
        throw connectionError
      }
      
      // Check for other network errors
      if (error.code === 'ECONNREFUSED' || error.code === 'ERR_NETWORK' || error.code === 'ERR_INTERNET_DISCONNECTED') {
        const connectionError = createError(
          'Connection refused. The server may be down or unreachable.',
          'ConnectionError'
        )
        throw connectionError
      }
      
      // Otherwise, wrap it in a standard format
      return {
        error: error instanceof Error ? error.message : 'Unknown error',
        status: (error as ApiClientError)?.response?.status || 500,
      }
    }
  }

  async get<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'GET' })
  }

  async post<T>(endpoint: string, data?: any): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  async put<T>(endpoint: string, data?: any): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  async patch<T>(endpoint: string, data?: any): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  async delete<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'DELETE' })
  }

  async fetchRaw(endpoint: string, options: RequestInit = {}): Promise<Response> {
    const token = await this.getAuthToken()
    
    const defaultHeaders: HeadersInit = {}
    if (token) {
      defaultHeaders.Authorization = `Bearer ${token}`
    }

    const config: RequestInit = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    }

    return fetch(`${this.baseURL}${endpoint}`, config)
  }

  async upload<T>(endpoint: string, formData: FormData, onProgress?: (progress: number) => void): Promise<ApiResponse<T>> {
    return new Promise((resolve) => {
      const xhr = new XMLHttpRequest()
      
      // Setup progress tracking
      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            const percentComplete = Math.round((e.loaded / e.total) * 100)
            onProgress(percentComplete)
          }
        })
      }
      
      // Setup completion handlers
      xhr.addEventListener('load', async () => {
        try {
          const response = JSON.parse(xhr.responseText)
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve({ data: response, error: null })
          } else {
            resolve({ data: null, error: response.detail || 'Upload failed' })
          }
        } catch (error) {
          resolve({ data: null, error: 'Invalid response from server' })
        }
      })
      
      xhr.addEventListener('error', () => {
        resolve({ data: null, error: 'Network error during upload' })
      })
      
      xhr.addEventListener('abort', () => {
        resolve({ data: null, error: 'Upload cancelled' })
      })
      
      // Open request and set headers
      xhr.open('POST', `${this.baseURL}${endpoint}`)
      
      this.getAuthToken().then(token => {
        if (token) {
          xhr.setRequestHeader('Authorization', `Bearer ${token}`)
        }
        
        // Send the request
        xhr.send(formData)
      })
    })
  }

  // Keep the old upload method for backward compatibility
  async uploadWithoutProgress<T>(endpoint: string, formData: FormData): Promise<ApiResponse<T>> {
    try {
      const token = await this.getAuthToken()
      
      const headers: HeadersInit = {}
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }

      const response = await fetch(`${this.baseURL}${endpoint}`, {
        method: 'POST',
        headers,
        body: formData,
      })

      let data
      const contentType = response.headers.get('content-type')
      
      if (contentType && contentType.includes('application/json')) {
        data = await response.json()
      } else {
        data = await response.text()
      }

      if (!response.ok) {
        throw new Error(data?.detail || data?.message || `HTTP ${response.status}`)
      }

      return {
        data,
        status: response.status,
      }
    } catch (error) {
      console.error('Upload request failed:', error)
      return {
        error: error instanceof Error ? error.message : 'Upload failed',
        status: 500,
      }
    }
  }

  // Método para establecer el token de autenticación
  setAuthTokenGetter(tokenGetter: () => Promise<string | null>) {
    this.getAuthToken = tokenGetter
  }
}

// Hook para usar el cliente API con autenticación de Clerk
export function useApiClient() {
  const { getToken } = useAuth()
  
  const client = useMemo(() => new ApiClient(), [])
  
  useEffect(() => {
    client.setAuthTokenGetter(async () => {
      try {
        let token = await getToken()
        if (!token) {
          console.log('No token available, attempting to get fresh token...')
          token = await getToken({ template: 'nexus' })
        }
        if (token) {
          console.log('✅ Got Clerk token, length:', token.length)
        } else {
          console.log('❌ No Clerk token available')
        }
        return token
      } catch (error) {
        console.error('Failed to get auth token:', error)
        return null
      }
    })
  }, [client, getToken])
  
  return client
}

// Instancia singleton para uso en componentes que no pueden usar hooks
export const apiClient = new ApiClient()

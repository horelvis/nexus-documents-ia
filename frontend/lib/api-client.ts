"use client"

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

class ApiClient {
  private baseURL: string

  constructor() {
    this.baseURL = `${API_CONFIG.BASE_URL}${API_CONFIG.API_V1}`
  }

  private async getAuthToken(): Promise<string | null> {
    // En el cliente, necesitamos usar el hook de Clerk
    // Esta función será sobrescrita por el hook useApiClient
    return null
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
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
        throw new Error(data?.detail || data?.message || `HTTP ${response.status}`)
      }

      return {
        data,
        status: response.status,
      }
    } catch (error) {
      console.error('API request failed:', error)
      return {
        error: error instanceof Error ? error.message : 'Unknown error',
        status: 500,
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

  async delete<T>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>(endpoint, { method: 'DELETE' })
  }

  async upload<T>(endpoint: string, formData: FormData): Promise<ApiResponse<T>> {
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
  
  const client = new ApiClient()
  
  // Configurar el cliente para usar el token de Clerk
  client.setAuthTokenGetter(async () => {
    try {
      return await getToken()
    } catch (error) {
      console.error('Failed to get auth token:', error)
      return null
    }
  })
  
  return client
}

// Instancia singleton para uso en componentes que no pueden usar hooks
export const apiClient = new ApiClient()
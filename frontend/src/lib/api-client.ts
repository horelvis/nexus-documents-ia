/**
 * API Client for Emma On-Premise
 *
 * Simplified API client without Clerk dependencies.
 * Uses SSO tokens from sessionStorage.
 */

import axios, { AxiosInstance, AxiosRequestConfig, AxiosError } from 'axios'
import { refreshAccessToken } from '@/lib/oidc-config'

// Always use relative path to go through Next.js proxy (avoids CORS)
// The proxy forwards requests to the backend configured in next.config.ts
const API_BASE_URL = '/api/v1'
const SSO_TOKEN_KEY = 'nexus_sso_tokens'

interface SSOTokens {
  access_token: string
  refresh_token?: string
  id_token?: string
  expires_at?: number
}

interface ApiResponse<T = unknown> {
  data: T | null
  error: string | null
  status: number
}

class ApiClient {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Request interceptor - add auth token
    this.client.interceptors.request.use(
      async (config) => {
        const token = await this.getAccessToken()
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    // Response interceptor - handle auth errors
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }
        if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
          originalRequest._retry = true
          // Try to refresh token
          const refreshed = await this.refreshToken()
          if (refreshed) {
            // Retry the request with new token
            const token = await this.getAccessToken()
            originalRequest.headers = { ...originalRequest.headers, Authorization: `Bearer ${token}` }
            return this.client.request(originalRequest)
          }
          // Clear tokens and redirect to login
          this.clearTokens()
          window.location.href = '/auth/sign-in'
        }
        return Promise.reject(error)
      }
    )
  }

  private getStoredTokens(): SSOTokens | null {
    if (typeof window === 'undefined') return null
    const stored = sessionStorage.getItem(SSO_TOKEN_KEY)
    if (!stored) return null
    try {
      return JSON.parse(stored)
    } catch {
      return null
    }
  }

  private async getAccessToken(): Promise<string | null> {
    const tokens = this.getStoredTokens()
    if (!tokens?.access_token) return null

    // Check if token is expired
    if (tokens.expires_at && Date.now() >= tokens.expires_at - 60000) {
      // Token expiring soon, try refresh
      await this.refreshToken()
      const refreshedTokens = this.getStoredTokens()
      return refreshedTokens?.access_token || null
    }

    return tokens.access_token
  }

  private async refreshToken(): Promise<boolean> {
    const tokens = this.getStoredTokens()
    if (!tokens?.refresh_token) return false

    try {
      // Refresh directly against KeyCloak (same as auth-context)
      const response = await refreshAccessToken(tokens.refresh_token)

      const newTokens: SSOTokens = {
        access_token: response.access_token,
        refresh_token: response.refresh_token || tokens.refresh_token,
        id_token: tokens.id_token,
        expires_at: Date.now() + (response.expires_in || 3600) * 1000,
      }

      sessionStorage.setItem(SSO_TOKEN_KEY, JSON.stringify(newTokens))
      return true
    } catch {
      return false
    }
  }

  private clearTokens(): void {
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem(SSO_TOKEN_KEY)
    }
  }

  async get<T>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    try {
      const response = await this.client.get<T>(url, config)
      return { data: response.data, error: null, status: response.status }
    } catch (error) {
      return this.handleError<T>(error)
    }
  }

  async post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    try {
      const response = await this.client.post<T>(url, data, config)
      return { data: response.data, error: null, status: response.status }
    } catch (error) {
      return this.handleError<T>(error)
    }
  }

  async put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    try {
      const response = await this.client.put<T>(url, data, config)
      return { data: response.data, error: null, status: response.status }
    } catch (error) {
      return this.handleError<T>(error)
    }
  }

  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    try {
      const response = await this.client.delete<T>(url, config)
      return { data: response.data, error: null, status: response.status }
    } catch (error) {
      return this.handleError<T>(error)
    }
  }

  async patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    try {
      const response = await this.client.patch<T>(url, data, config)
      return { data: response.data, error: null, status: response.status }
    } catch (error) {
      return this.handleError<T>(error)
    }
  }

  async upload<T>(
    url: string,
    formData: FormData,
    onProgress?: (progress: number) => void
  ): Promise<ApiResponse<T>> {
    try {
      const response = await this.client.post<T>(url, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
          if (onProgress && progressEvent.total) {
            const progress = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            )
            onProgress(progress)
          }
        },
      })
      return { data: response.data, error: null, status: response.status }
    } catch (error) {
      return this.handleError<T>(error)
    }
  }

  /**
   * Download a file as a blob with authentication
   */
  async downloadBlob(url: string): Promise<{ blob: Blob | null; error: string | null }> {
    try {
      const response = await this.client.get(url, {
        responseType: 'blob',
      })
      return { blob: response.data, error: null }
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const axiosError = error as AxiosError
        return {
          blob: null,
          error: axiosError.message || 'Download failed',
        }
      }
      return { blob: null, error: 'Unknown error' }
    }
  }

  private handleError<T>(error: unknown): ApiResponse<T> {
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError<{ detail?: string; message?: string }>
      const message =
        axiosError.response?.data?.detail ||
        axiosError.response?.data?.message ||
        axiosError.message ||
        'Request failed'
      return {
        data: null,
        error: message,
        status: axiosError.response?.status || 500,
      }
    }
    return {
      data: null,
      error: 'Unknown error',
      status: 500,
    }
  }
}

export const apiClient = new ApiClient()
export type { ApiResponse }

/**
 * Hook wrapper for consistency with saas patterns
 * Services can use this hook to get the API client
 */
export function useApiClient() {
  return apiClient
}

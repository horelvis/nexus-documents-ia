import { useApiClient } from '@/lib/api-client'
import {
  SignatureProvider,
  CreateProviderData,
  SupportedProvider,
  SignatureRequest,
  CreateSignatureRequestData,
  UpdateSignatureRequestData,
} from './signature-service'

export function useSignatureService() {
  const apiClient = useApiClient()

  return {
    // Providers
    async getProviders(): Promise<SignatureProvider[]> {
      const response = await apiClient.get('/signatures/providers')
      return response.data
    },

    async getProvider(providerId: string): Promise<SignatureProvider> {
      const response = await apiClient.get(`/signatures/providers/${providerId}`)
      return response.data
    },

    async getActiveProvider(): Promise<SignatureProvider | null> {
      const providers = await this.getProviders()
      return providers.find(p => p.is_active && p.is_default) || providers.find(p => p.is_active) || null
    },

    async getSupportedProviders(): Promise<SupportedProvider[]> {
      const response = await apiClient.get('/signatures/providers/supported')
      return response.data
    },

    async createProvider(data: CreateProviderData): Promise<SignatureProvider> {
      const response = await apiClient.post('/signatures/providers', data)
      return response.data
    },

    async updateProvider(providerId: string, data: Partial<CreateProviderData>): Promise<SignatureProvider> {
      const response = await apiClient.put(`/signatures/providers/${providerId}`, data)
      return response.data
    },

    async deleteProvider(providerId: string): Promise<void> {
      await apiClient.delete(`/signatures/providers/${providerId}`)
    },

    async testConnection(providerId: string): Promise<{ success: boolean; message: string }> {
      const response = await apiClient.post(`/signatures/providers/${providerId}/test`)
      return response.data
    },

    async setDefaultProvider(providerId: string): Promise<SignatureProvider> {
      const response = await apiClient.post(`/signatures/providers/${providerId}/set-default`)
      return response.data
    },

    // Signature Requests
    async getRequests(filters?: {
      status?: string
      provider_id?: string
      limit?: number
      offset?: number
    }): Promise<SignatureRequest[]> {
      const params = new URLSearchParams()
      if (filters) {
        Object.entries(filters).forEach(([key, value]) => {
          if (value !== undefined) {
            params.append(key, String(value))
          }
        })
      }
      
      const endpoint = params.toString() ? `/signatures/requests?${params}` : '/signatures/requests'
      const response = await apiClient.get(endpoint)
      return response.data
    },

    async getRequest(requestId: string): Promise<SignatureRequest> {
      const response = await apiClient.get(`/signatures/requests/${requestId}`)
      return response.data
    },

    async createRequest(data: CreateSignatureRequestData): Promise<SignatureRequest> {
      const response = await apiClient.post('/signatures/requests', data)
      return response.data
    },

    async updateRequest(requestId: string, data: UpdateSignatureRequestData): Promise<SignatureRequest> {
      const response = await apiClient.put(`/signatures/requests/${requestId}`, data)
      return response.data
    },

    async sendRequest(requestId: string): Promise<SignatureRequest> {
      const response = await apiClient.post(`/signatures/requests/${requestId}/send`)
      return response.data
    },

    async cancelRequest(requestId: string): Promise<void> {
      await apiClient.post(`/signatures/requests/${requestId}/cancel`)
    },

    async updateStatus(requestId: string): Promise<SignatureRequest> {
      const response = await apiClient.post(`/signatures/requests/${requestId}/update-status`)
      return response.data
    },

    async getSigningUrl(requestId: string, signerEmail: string): Promise<{ url: string }> {
      const response = await apiClient.get(`/signatures/requests/${requestId}/signing-url/${signerEmail}`)
      return response.data
    },

    async downloadSignedDocument(requestId: string): Promise<Blob> {
      const response = await apiClient.get(`/signatures/requests/${requestId}/download`)
      return response.data
    },

    // Webhook management
    async getWebhookUrl(providerId: string): Promise<{ url: string }> {
      const response = await apiClient.get(`/signatures/webhooks/${providerId}/url`)
      return response.data
    },
  }
}
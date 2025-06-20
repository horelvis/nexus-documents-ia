import { apiClient } from '@/lib/api-client'

export interface SignatureProvider {
  id: string
  provider_name: 'docusign' | 'yousign' | 'signaturit'
  display_name: string
  is_active: boolean
  is_default: boolean
  configuration?: any
  created_at: string
  updated_at: string
}

export interface CreateProviderData {
  provider_name: 'docusign' | 'yousign' | 'signaturit'
  display_name: string
  credentials: DocuSignCredentials | YouSignCredentials | SignaturitCredentials
  is_active?: boolean
  is_default?: boolean
  configuration?: any
}

export interface DocuSignCredentials {
  integration_key: string
  secret_key: string
  account_id: string
  base_url: string
}

export interface YouSignCredentials {
  api_key: string
  environment: 'sandbox' | 'production'
}

export interface SignaturitCredentials {
  access_token: string
  environment: 'sandbox' | 'production'
}

export interface SupportedProvider {
  name: string
  display_name: string
  required_fields: string[]
  optional_fields: string[]
}

export interface SignatureRequestSigner {
  email: string
  name: string
  role: 'signer' | 'viewer' | 'approver'
  order: number
  status?: 'pending' | 'sent' | 'viewed' | 'signed' | 'declined'
  signed_at?: string
}

export interface SignatureRequest {
  id: string
  title: string
  message?: string
  document_id: string
  provider_id: string
  status: 'draft' | 'pending' | 'sent' | 'completed' | 'declined' | 'expired'
  signers: SignatureRequestSigner[]
  external_id?: string
  created_at: string
  updated_at: string
  sent_at?: string
  completed_at?: string
  expires_at?: string
}

export interface CreateSignatureRequestData {
  title: string
  message?: string
  document_id: string
  document_name: string
  provider_id: string
  signers: Omit<SignatureRequestSigner, 'status' | 'signed_at'>[]
  expires_in_days?: number
}

export interface UpdateSignatureRequestData {
  title?: string
  message?: string
  signers?: Omit<SignatureRequestSigner, 'status' | 'signed_at'>[]
}

class SignatureService {
  // Providers
  async getProviders(): Promise<SignatureProvider[]> {
    const response = await apiClient.get('/signatures/providers')
    return response.data
  }

  async getProvider(providerId: string): Promise<SignatureProvider> {
    const response = await apiClient.get(`/signatures/providers/${providerId}`)
    return response.data
  }

  async getActiveProvider(): Promise<SignatureProvider | null> {
    const providers = await this.getProviders()
    return providers.find(p => p.is_active) || null
  }

  async getDefaultProvider(): Promise<SignatureProvider | null> {
    const response = await apiClient.get('/signatures/providers/default')
    return response.data
  }

  async getSupportedProviders(): Promise<SupportedProvider[]> {
    const response = await apiClient.get('/signatures/providers/supported')
    return response.data
  }

  async createProvider(data: CreateProviderData): Promise<SignatureProvider> {
    const response = await apiClient.post('/signatures/providers', data)
    return response.data
  }

  async updateProvider(
    providerId: string, 
    data: Partial<CreateProviderData>
  ): Promise<SignatureProvider> {
    const response = await apiClient.put(`/signatures/providers/${providerId}`, data)
    return response.data
  }

  async deleteProvider(providerId: string): Promise<void> {
    await apiClient.delete(`/signatures/providers/${providerId}`)
  }

  async setDefaultProvider(providerId: string): Promise<SignatureProvider> {
    const response = await apiClient.put(`/signatures/providers/${providerId}/set-default`)
    return response.data
  }

  async testProvider(providerId: string): Promise<{ success: boolean; message: string }> {
    const response = await apiClient.post(`/signatures/providers/${providerId}/test`)
    return response.data
  }

  // Signature Requests
  async createRequest(data: CreateSignatureRequestData): Promise<SignatureRequest> {
    const response = await apiClient.post('/signatures/requests', data)
    return response.data
  }

  async getRequest(requestId: string): Promise<SignatureRequest> {
    const response = await apiClient.get(`/signatures/requests/${requestId}`)
    return response.data
  }

  async getRequests(params?: {
    status?: string
    skip?: number
    limit?: number
  }): Promise<{ items: SignatureRequest[]; total: number }> {
    const response = await apiClient.get('/signatures/requests', { params })
    return response.data
  }

  async updateRequest(
    requestId: string,
    data: UpdateSignatureRequestData
  ): Promise<SignatureRequest> {
    const response = await apiClient.put(`/signatures/requests/${requestId}`, data)
    return response.data
  }

  async sendRequest(requestId: string): Promise<SignatureRequest> {
    const response = await apiClient.post(`/signatures/requests/${requestId}/send`)
    return response.data
  }

  async cancelRequest(requestId: string): Promise<void> {
    await apiClient.post(`/signatures/requests/${requestId}/cancel`)
  }

  async downloadSignedDocument(requestId: string): Promise<string> {
    const response = await apiClient.get(`/signatures/requests/${requestId}/download`)
    return response.data.download_url
  }

  // Helper methods
  async getRequestsByDocument(documentId: string): Promise<SignatureRequest[]> {
    const response = await this.getRequests()
    return response.items.filter(req => req.document_id === documentId)
  }

  getStatusIcon(status: SignatureRequest['status']): string {
    const statusIcons = {
      draft: '📝',
      pending: '⏳',
      sent: '✉️',
      completed: '✅',
      declined: '❌',
      expired: '⏰'
    }
    return statusIcons[status] || '📄'
  }

  getStatusLabel(status: SignatureRequest['status']): string {
    const statusLabels = {
      draft: 'Draft',
      pending: 'Pending',
      sent: 'Sent',
      completed: 'Completed',
      declined: 'Declined',
      expired: 'Expired'
    }
    return statusLabels[status] || status
  }

  getStatusColor(status: SignatureRequest['status']): string {
    const statusColors = {
      draft: 'gray',
      pending: 'yellow',
      sent: 'blue',
      completed: 'green',
      declined: 'red',
      expired: 'orange'
    }
    return statusColors[status] || 'gray'
  }
}

export const signatureService = new SignatureService()
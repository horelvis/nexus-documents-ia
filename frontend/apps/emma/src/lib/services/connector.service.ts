/**
 * Connector Service for Emma On-Premise
 *
 * Handles connector authorization and document sync operations.
 */

import { apiClient } from '@/lib/api-client'

// Types
export interface ConnectorOnboardingItem {
  id: string
  name: string
  description: string | null
  connector_type: ConnectorType
  auth_type: ConnectorAuthType
  is_authorized: boolean
  is_syncing: boolean
  documents_indexed: number
}

export interface OnboardingStatus {
  available_connectors: ConnectorOnboardingItem[]
  has_completed_onboarding: boolean
  total_connectors: number
  connected_count: number
  syncing_count: number
}

export interface UserDocumentSync {
  id: string
  connector_id: string
  connector_name: string
  connector_type: ConnectorType
  sync_enabled: boolean
  include_paths: string[]
  exclude_paths: string[]
  status: SyncStatus
  status_message: string | null
  documents_total: number
  documents_indexed: number
  documents_failed: number
  total_size_bytes: number
  last_sync_started_at: string | null
  last_sync_completed_at: string | null
  next_sync_at: string | null
  last_error: string | null
}

export interface IndexedDocument {
  id: string
  connector_id: string | null
  external_id: string
  external_url: string | null
  external_path: string | null
  title: string
  description: string | null
  mime_type: string | null
  file_extension: string | null
  size_bytes: number
  is_tenant_public: boolean
  indexing_status: string
  indexing_error: string | null
  source_created_at: string | null
  source_modified_at: string | null
  indexed_at: string | null
}

export type ConnectorType =
  | 'sharepoint'
  | 'onedrive'
  | 'google_drive'
  | 'google_workspace'
  | 'dropbox'
  | 'box'
  | 's3'
  | 'azure_blob'
  | 'network_share'
  | 'alfresco'

export type ConnectorAuthType = 'delegated' | 'service_account' | 'api_key'

export type SyncStatus = 'pending' | 'syncing' | 'completed' | 'paused' | 'failed'

// Connector icons mapping
export const connectorIcons: Record<ConnectorType, string> = {
  sharepoint: '📁',
  onedrive: '☁️',
  google_drive: '📂',
  google_workspace: '🔷',
  dropbox: '📦',
  box: '📥',
  s3: '🪣',
  azure_blob: '💠',
  network_share: '🔗',
  alfresco: '🗄️',
}

export const connectorNames: Record<ConnectorType, string> = {
  sharepoint: 'SharePoint',
  onedrive: 'OneDrive',
  google_drive: 'Google Drive',
  google_workspace: 'Google Workspace',
  dropbox: 'Dropbox',
  box: 'Box',
  s3: 'Amazon S3',
  azure_blob: 'Azure Blob Storage',
  network_share: 'Network Share',
  alfresco: 'Alfresco',
}

// Connector descriptions for selection UI
export const connectorDescriptions: Record<ConnectorType, string> = {
  sharepoint: 'Conecta con sitios de SharePoint Online para sincronizar documentos y bibliotecas compartidas de tu organización.',
  onedrive: 'Sincroniza archivos personales y compartidos desde OneDrive for Business o cuentas personales de Microsoft.',
  google_drive: 'Accede a documentos almacenados en Google Drive, incluyendo archivos compartidos y carpetas de equipo.',
  google_workspace: 'Integración empresarial con Google Workspace para acceder a documentos de toda la organización.',
  dropbox: 'Conecta con Dropbox para sincronizar archivos y carpetas compartidas de tu espacio de trabajo.',
  box: 'Sincroniza contenido empresarial desde Box, incluyendo carpetas compartidas y colaboración de equipos.',
  s3: 'Conecta con buckets de Amazon S3 para indexar documentos almacenados en la nube de AWS.',
  azure_blob: 'Accede a contenedores de Azure Blob Storage para sincronizar documentos empresariales.',
  network_share: 'Conecta con carpetas compartidas en red (SMB/CIFS) de tu servidor de archivos local.',
  alfresco: 'Integración con Alfresco ECM para acceder a repositorios documentales y flujos de trabajo.',
}

// Connector categories for grouping in UI
export type ConnectorCategory = 'microsoft' | 'google' | 'cloud_storage' | 'enterprise' | 'file_systems'

export const connectorCategories: Record<ConnectorCategory, { name: string; types: ConnectorType[] }> = {
  microsoft: {
    name: 'Microsoft 365',
    types: ['sharepoint', 'onedrive'],
  },
  google: {
    name: 'Google',
    types: ['google_drive', 'google_workspace'],
  },
  cloud_storage: {
    name: 'Almacenamiento en la Nube',
    types: ['dropbox', 'box', 's3', 'azure_blob'],
  },
  enterprise: {
    name: 'ECM Empresarial',
    types: ['alfresco'],
  },
  file_systems: {
    name: 'Sistemas de Archivos',
    types: ['network_share'],
  },
}

// ============================================================================
// Admin Types (for connector management)
// ============================================================================

export type ConnectorHealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown'

export interface Connector {
  id: string
  tenant_id: string
  name: string
  description: string | null
  connector_type: ConnectorType
  auth_type: ConnectorAuthType
  config: Record<string, any>
  sync_enabled: boolean
  sync_interval_hours: number
  is_active: boolean
  health_status: ConnectorHealthStatus
  health_message: string | null
  last_health_check: string | null
  created_by_id: string | null
  created_at: string
  updated_at: string | null
  users_connected: number
  users_syncing: number
}

export interface ConnectorListResponse {
  items: Connector[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface CreateConnectorData {
  name: string
  description?: string
  connector_type: ConnectorType
  auth_type?: ConnectorAuthType
  config: Record<string, any>
  sync_enabled?: boolean
  sync_interval_hours?: number
}

export interface UpdateConnectorData {
  name?: string
  description?: string
  config?: Record<string, any>
  sync_enabled?: boolean
  sync_interval_hours?: number
  is_active?: boolean
}

// Config field definition for forms
export interface ConfigField {
  name: string
  label: string
  type: 'text' | 'password' | 'number' | 'select' | 'textarea'
  required: boolean
  placeholder?: string
  description?: string
  defaultValue?: string | number
  min?: number
  max?: number
}

// Connector type configurations for the form
// All connectors use service_account for automatic connection (no per-user OAuth)
export const connectorConfigs: Record<ConnectorType, { fields: ConfigField[] }> = {
  alfresco: {
    fields: [
      { name: 'url', label: 'URL de Alfresco', type: 'text', required: true, placeholder: 'https://alfresco.empresa.com' },
      { name: 'username', label: 'Usuario de Servicio', type: 'text', required: true, placeholder: 'admin' },
      { name: 'password', label: 'Contraseña', type: 'password', required: true },
      { name: 'default_site_id', label: 'Site ID por defecto', type: 'text', required: false, description: 'Sincronizar solo este site (dejar vacío para todos)' },
      { name: 'timeout_seconds', label: 'Timeout (segundos)', type: 'number', required: false, defaultValue: 60, min: 10, max: 300 },
      // AFTS Filter Fields
      { name: 'afts_type_filter', label: 'Tipos de Nodo (AFTS)', type: 'text', required: false, placeholder: 'cm:content, cm:document', description: 'Tipos de nodo separados por coma (ej: cm:content)' },
      { name: 'afts_aspect_filter', label: 'Filtro de Aspectos (AFTS)', type: 'text', required: false, placeholder: 'cm:titled, cm:versionable', description: 'Aspectos separados por coma' },
      { name: 'afts_path_filter', label: 'Filtro de Ruta (AFTS)', type: 'text', required: false, placeholder: '/app:company_home/st:sites/cm:mysite/cm:documentLibrary//*', description: 'Patrón de ruta AFTS para restringir sincronización' },
      { name: 'afts_mime_types', label: 'Tipos MIME', type: 'text', required: false, placeholder: 'application/pdf, application/msword', description: 'Tipos MIME separados por coma' },
      { name: 'afts_custom_query', label: 'Query AFTS Personalizado', type: 'textarea', required: false, placeholder: '@cm\\:author:"John Doe"', description: 'Fragmento de query AFTS (se combina con AND)' },
      { name: 'afts_exclude_paths', label: 'Rutas a Excluir', type: 'text', required: false, placeholder: '/app:company_home/st:sites/cm:archive//*', description: 'Rutas separadas por coma a excluir de la sincronización' },
    ],
  },
  sharepoint: {
    fields: [
      { name: 'tenant_id', label: 'Azure AD Tenant ID', type: 'text', required: true, description: 'ID del tenant de Azure AD' },
      { name: 'client_id', label: 'Application (Client) ID', type: 'text', required: true, description: 'ID de la aplicación registrada en Azure AD' },
      { name: 'client_secret', label: 'Client Secret', type: 'password', required: true, description: 'Secret de la aplicación' },
      { name: 'site_url', label: 'URL del Sitio', type: 'text', required: false, placeholder: 'https://company.sharepoint.com/sites/docs', description: 'Sincronizar solo este sitio (dejar vacío para todos)' },
    ],
  },
  onedrive: {
    fields: [
      { name: 'tenant_id', label: 'Azure AD Tenant ID', type: 'text', required: true },
      { name: 'client_id', label: 'Application (Client) ID', type: 'text', required: true },
      { name: 'client_secret', label: 'Client Secret', type: 'password', required: true },
      { name: 'user_principal_name', label: 'Usuario a Sincronizar', type: 'text', required: false, placeholder: 'user@company.com', description: 'Sincronizar solo este usuario (dejar vacío para todos)' },
    ],
  },
  google_drive: {
    fields: [
      { name: 'service_account_json', label: 'Service Account JSON', type: 'textarea', required: true, description: 'Contenido completo del archivo JSON de cuenta de servicio' },
      { name: 'domain', label: 'Dominio', type: 'text', required: true, placeholder: 'empresa.com', description: 'Dominio de Google Workspace' },
      { name: 'admin_email', label: 'Email del Admin', type: 'text', required: true, placeholder: 'admin@empresa.com', description: 'Email con permisos de admin para delegación de dominio' },
    ],
  },
  google_workspace: {
    fields: [
      { name: 'service_account_json', label: 'Service Account JSON', type: 'textarea', required: true, description: 'Contenido completo del archivo JSON de cuenta de servicio' },
      { name: 'domain', label: 'Dominio', type: 'text', required: true, placeholder: 'empresa.com' },
      { name: 'admin_email', label: 'Email del Admin', type: 'text', required: true, placeholder: 'admin@empresa.com', description: 'Email con permisos para delegación de dominio' },
    ],
  },
  dropbox: {
    fields: [
      { name: 'access_token', label: 'Access Token', type: 'password', required: true, description: 'Token de acceso de la app de Dropbox Business' },
      { name: 'team_member_id', label: 'Team Member ID', type: 'text', required: false, description: 'Sincronizar solo este miembro (dejar vacío para todo el equipo)' },
    ],
  },
  box: {
    fields: [
      { name: 'client_id', label: 'Client ID', type: 'text', required: true },
      { name: 'client_secret', label: 'Client Secret', type: 'password', required: true },
      { name: 'enterprise_id', label: 'Enterprise ID', type: 'text', required: true, description: 'ID de la empresa en Box' },
      { name: 'jwt_private_key', label: 'JWT Private Key', type: 'textarea', required: true, description: 'Clave privada para autenticación JWT' },
    ],
  },
  s3: {
    fields: [
      { name: 'bucket_name', label: 'Nombre del Bucket', type: 'text', required: true },
      { name: 'region', label: 'Región AWS', type: 'text', required: true, defaultValue: 'us-east-1' },
      { name: 'access_key_id', label: 'Access Key ID', type: 'text', required: true },
      { name: 'secret_access_key', label: 'Secret Access Key', type: 'password', required: true },
      { name: 'prefix', label: 'Prefijo', type: 'text', required: false, placeholder: 'documents/', description: 'Sincronizar solo archivos con este prefijo' },
    ],
  },
  azure_blob: {
    fields: [
      { name: 'storage_account', label: 'Storage Account', type: 'text', required: true },
      { name: 'container_name', label: 'Nombre del Container', type: 'text', required: true },
      { name: 'connection_string', label: 'Connection String', type: 'password', required: true },
      { name: 'prefix', label: 'Prefijo', type: 'text', required: false, description: 'Sincronizar solo blobs con este prefijo' },
    ],
  },
  network_share: {
    fields: [
      { name: 'server', label: 'Servidor', type: 'text', required: true, placeholder: 'fileserver.empresa.local' },
      { name: 'share_name', label: 'Nombre del Share', type: 'text', required: true },
      { name: 'domain', label: 'Dominio AD', type: 'text', required: false },
      { name: 'username', label: 'Usuario de Servicio', type: 'text', required: true },
      { name: 'password', label: 'Contraseña', type: 'password', required: true },
      { name: 'base_path', label: 'Ruta Base', type: 'text', required: false, description: 'Sincronizar solo esta carpeta' },
    ],
  },
}

class ConnectorService {
  /**
   * Get user's onboarding status with available connectors
   */
  async getOnboardingStatus(): Promise<{ data: OnboardingStatus | null; error: string | null }> {
    try {
      const response = await apiClient.get<OnboardingStatus>('/user-sync/onboarding')
      return { data: response.data, error: null }
    } catch (error) {
      console.error('[ConnectorService] getOnboardingStatus error:', error)
      return { data: null, error: 'Failed to get onboarding status' }
    }
  }

  /**
   * Get OAuth URL to authorize a connector
   */
  async getConnectorOAuthUrl(connectorId: string): Promise<{ data: { auth_url: string; state: string } | null; error: string | null }> {
    try {
      const response = await apiClient.get<{ auth_url: string; state: string }>(
        `/user-sync/connectors/${connectorId}/oauth-url`
      )
      return { data: response.data, error: null }
    } catch (error) {
      console.error('[ConnectorService] getConnectorOAuthUrl error:', error)
      return { data: null, error: 'Failed to get OAuth URL' }
    }
  }

  /**
   * Enable document sync for a connector
   */
  async enableSync(
    connectorId: string,
    config?: { include_paths?: string[]; exclude_paths?: string[] }
  ): Promise<{ data: UserDocumentSync | null; error: string | null }> {
    try {
      const response = await apiClient.post<UserDocumentSync>(
        `/user-sync/connectors/${connectorId}/sync`,
        {
          sync_enabled: true,
          include_paths: config?.include_paths || [],
          exclude_paths: config?.exclude_paths || [],
        }
      )
      return { data: response.data, error: null }
    } catch (error) {
      console.error('[ConnectorService] enableSync error:', error)
      return { data: null, error: 'Failed to enable sync' }
    }
  }

  /**
   * Get all user syncs
   */
  async getUserSyncs(): Promise<{ data: { items: UserDocumentSync[]; total: number } | null; error: string | null }> {
    try {
      const response = await apiClient.get<{ items: UserDocumentSync[]; total: number }>('/user-sync/syncs')
      return { data: response.data, error: null }
    } catch (error) {
      console.error('[ConnectorService] getUserSyncs error:', error)
      return { data: null, error: 'Failed to get syncs' }
    }
  }

  /**
   * Trigger manual sync
   */
  async triggerSync(syncId: string, fullResync = false): Promise<{ data: { status: string; message: string } | null; error: string | null }> {
    try {
      const response = await apiClient.post<{ status: string; message: string }>(
        `/user-sync/syncs/${syncId}/trigger`,
        { full_resync: fullResync }
      )
      return { data: response.data, error: null }
    } catch (error) {
      console.error('[ConnectorService] triggerSync error:', error)
      return { data: null, error: 'Failed to trigger sync' }
    }
  }

  /**
   * Get user's indexed documents
   */
  async getIndexedDocuments(params?: {
    connector_id?: string
    status?: string
    search?: string
    page?: number
    page_size?: number
  }): Promise<{ data: { items: IndexedDocument[]; total: number; page: number; total_pages: number } | null; error: string | null }> {
    try {
      const searchParams = new URLSearchParams()
      if (params?.connector_id) searchParams.append('connector_id', params.connector_id)
      if (params?.status) searchParams.append('status', params.status)
      if (params?.search) searchParams.append('search', params.search)
      if (params?.page) searchParams.append('page', params.page.toString())
      if (params?.page_size) searchParams.append('page_size', params.page_size.toString())

      const response = await apiClient.get<{ items: IndexedDocument[]; total: number; page: number; total_pages: number }>(
        `/user-sync/documents?${searchParams.toString()}`
      )
      return { data: response.data, error: null }
    } catch (error) {
      console.error('[ConnectorService] getIndexedDocuments error:', error)
      return { data: null, error: 'Failed to get documents' }
    }
  }

  /**
   * Revoke connector authorization
   */
  async revokeAuth(connectorId: string): Promise<{ error: string | null }> {
    try {
      await apiClient.delete(`/user-sync/connectors/${connectorId}/auth`)
      return { error: null }
    } catch (error) {
      console.error('[ConnectorService] revokeAuth error:', error)
      return { error: 'Failed to revoke authorization' }
    }
  }

  // ==========================================================================
  // Admin Functions (connector CRUD)
  // ==========================================================================

  /**
   * List all connectors (admin)
   */
  async getConnectors(): Promise<{ data: ConnectorListResponse | null; error: string | null }> {
    const response = await apiClient.get<ConnectorListResponse>('/connectors')
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Get single connector (admin)
   */
  async getConnector(connectorId: string): Promise<{ data: Connector | null; error: string | null }> {
    const response = await apiClient.get<Connector>(`/connectors/${connectorId}`)
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Create connector (admin)
   */
  async createConnector(data: CreateConnectorData): Promise<{ data: Connector | null; error: string | null }> {
    const response = await apiClient.post<Connector>('/connectors', data)
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Update connector (admin)
   */
  async updateConnector(connectorId: string, data: UpdateConnectorData): Promise<{ data: Connector | null; error: string | null }> {
    const response = await apiClient.put<Connector>(`/connectors/${connectorId}`, data)
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Delete connector (admin)
   */
  async deleteConnector(connectorId: string): Promise<{ error: string | null }> {
    const response = await apiClient.delete(`/connectors/${connectorId}`)
    if (response.error) {
      return { error: response.error }
    }
    return { error: null }
  }

  /**
   * Test connector health (admin)
   */
  async testConnector(connectorId: string): Promise<{ data: HealthCheckResponse | null; error: string | null }> {
    const response = await apiClient.post<HealthCheckResponse>(`/connectors/${connectorId}/health-check`)
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }
}

// Health check response type
export interface HealthCheckResponse {
  connector_id: string
  status: ConnectorHealthStatus
  message: string
  checked_at: string
  details: Record<string, any> | null
}

export const connectorService = new ConnectorService()

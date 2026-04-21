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
  | 'onedrive'
  | 'google_drive'
  | 'dropbox'
  | 'box'
  | 'network_share'
  | 'alfresco'
  | 'database'

export type ConnectorAuthType = 'delegated' | 'service_account' | 'api_key'

export type SyncStatus = 'pending' | 'syncing' | 'completed' | 'paused' | 'failed'

// Connector icons mapping
export const connectorIcons: Record<ConnectorType, string> = {
  onedrive: '☁️',
  google_drive: '📂',
  dropbox: '📦',
  box: '📥',
  network_share: '🔗',
  alfresco: '🗄️',
  database: '🗃️',
}

export const connectorNames: Record<ConnectorType, string> = {
  onedrive: 'OneDrive',
  google_drive: 'Google Drive',
  dropbox: 'Dropbox',
  box: 'Box',
  network_share: 'Network Share',
  alfresco: 'Alfresco',
  database: 'Base de Datos',
}

// Connector descriptions for selection UI
export const connectorDescriptions: Record<ConnectorType, string> = {
  onedrive: 'Sincroniza archivos personales y compartidos desde OneDrive for Business o cuentas personales de Microsoft.',
  google_drive: 'Accede a documentos almacenados en Google Drive, incluyendo archivos compartidos y carpetas de equipo.',
  dropbox: 'Conecta con Dropbox para sincronizar archivos y carpetas compartidas de tu espacio de trabajo.',
  box: 'Sincroniza contenido empresarial desde Box, incluyendo carpetas compartidas y colaboración de equipos.',
  network_share: 'Conecta con carpetas compartidas en red (SMB/CIFS) de tu servidor de archivos local.',
  alfresco: 'Integración con Alfresco ECM para acceder a repositorios documentales y flujos de trabajo.',
  database: 'Conecta con bases de datos SQL (PostgreSQL, MySQL, MariaDB, SQL Server, Oracle, SQLite) para indexar documentos almacenados como BLOBs o referencias a archivos.',
}

// Connector types that use OAuth popup flow (no manual credentials)
export const OAUTH_CONNECTOR_TYPES: ConnectorType[] = ['google_drive', 'onedrive']

// Connector categories for grouping in UI
export type ConnectorCategory = 'microsoft' | 'google' | 'cloud_storage' | 'enterprise' | 'file_systems' | 'databases'

export const connectorCategories: Record<ConnectorCategory, { name: string; types: ConnectorType[] }> = {
  microsoft: {
    name: 'Microsoft 365',
    types: ['onedrive'],
  },
  google: {
    name: 'Google',
    types: ['google_drive'],
  },
  cloud_storage: {
    name: 'Almacenamiento en la Nube',
    types: ['dropbox', 'box'],
  },
  enterprise: {
    name: 'ECM Empresarial',
    types: ['alfresco'],
  },
  file_systems: {
    name: 'Sistemas de Archivos',
    types: ['network_share'],
  },
  databases: {
    name: 'Bases de Datos',
    types: ['database'],
  },
}

// ============================================================================
// Admin Types (for connector management)
// ============================================================================

export type ConnectorHealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown'

export interface Connector {
  id: string
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
  // Document processing stats
  documents_total: number
  documents_pending: number
  documents_indexed: number
  documents_failed: number
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
  onedrive: {
    fields: [],  // OAuth flow handles auth, like google_drive
  },
  google_drive: {
    fields: [],
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
  database: {
    fields: [
      { name: 'engine', label: 'Motor de Base de Datos', type: 'select', required: true, description: 'Tipo de base de datos a conectar' },
      { name: 'host', label: 'Host', type: 'text', required: true, placeholder: 'localhost', description: 'Nombre de host o IP del servidor' },
      { name: 'port', label: 'Puerto', type: 'number', required: false, description: 'Puerto (dejar vacío para usar el puerto por defecto del motor)' },
      { name: 'database', label: 'Base de Datos', type: 'text', required: true, placeholder: 'documents_db', description: 'Nombre de la base de datos' },
      { name: 'username', label: 'Usuario', type: 'text', required: true, placeholder: 'db_user' },
      { name: 'password', label: 'Contraseña', type: 'password', required: true },
      { name: 'storage_type', label: 'Tipo de Almacenamiento', type: 'select', required: true, description: 'Cómo se almacenan los documentos en la BD' },
      { name: 'table_name', label: 'Nombre de Tabla', type: 'text', required: false, placeholder: 'documents', description: 'Tabla que contiene los documentos (usar si no hay query personalizada)' },
      { name: 'custom_query', label: 'Query SQL Personalizado', type: 'textarea', required: false, placeholder: 'SELECT id, content, filename FROM documents WHERE status = \'active\'', description: 'Query personalizada (ignora table_name si se proporciona)' },
      { name: 'id_column', label: 'Columna ID', type: 'text', required: false, placeholder: 'id', description: 'Columna con el identificador único del documento' },
      { name: 'content_column', label: 'Columna Contenido', type: 'text', required: false, placeholder: 'content', description: 'Columna con BLOB, ruta de archivo o URL según storage_type' },
      { name: 'filename_column', label: 'Columna Nombre de Archivo', type: 'text', required: false, placeholder: 'filename', description: 'Columna con el nombre del archivo' },
      { name: 'mime_type_column', label: 'Columna Tipo MIME', type: 'text', required: false, placeholder: 'mime_type', description: 'Columna con el tipo MIME (opcional)' },
      { name: 'size_column', label: 'Columna Tamaño', type: 'text', required: false, placeholder: 'size_bytes', description: 'Columna con el tamaño en bytes (opcional)' },
      { name: 'created_at_column', label: 'Columna Fecha Creación', type: 'text', required: false, placeholder: 'created_at', description: 'Columna con fecha de creación (opcional)' },
      { name: 'modified_at_column', label: 'Columna Fecha Modificación', type: 'text', required: false, placeholder: 'modified_at', description: 'Columna con fecha de modificación (opcional)' },
      { name: 'where_clause', label: 'Filtro WHERE', type: 'text', required: false, placeholder: 'status = \'active\' AND deleted_at IS NULL', description: 'Condición WHERE adicional para filtrar documentos' },
      { name: 'base_file_path', label: 'Ruta Base de Archivos', type: 'text', required: false, placeholder: '/var/documents/', description: 'Ruta base si storage_type es file_path (prefijo para rutas relativas)' },
      { name: 'ssl_mode', label: 'Modo SSL', type: 'select', required: false, description: 'Modo de conexión SSL' },
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

  /**
   * Force sync connector (admin)
   * Triggers immediate synchronization of documents from the external source
   */
  async syncConnector(connectorId: string, fullSync = false): Promise<{ data: SyncTriggerResponse | null; error: string | null }> {
    const response = await apiClient.post<SyncTriggerResponse>(
      `/connectors/${connectorId}/sync?full_sync=${fullSync}`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Index pending documents (admin)
   * Processes documents that have been synced but not yet indexed
   */
  async indexPending(connectorId: string, batchSize = 10, maxDocuments?: number): Promise<{ data: IndexPendingResponse | null; error: string | null }> {
    let url = `/connectors/${connectorId}/index-pending?batch_size=${batchSize}`
    if (maxDocuments) {
      url += `&max_documents=${maxDocuments}`
    }
    const response = await apiClient.post<IndexPendingResponse>(url)
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Get pending documents list (admin)
   */
  async getPendingDocuments(connectorId: string, page = 1, pageSize = 20): Promise<{ data: PendingDocumentsResponse | null; error: string | null }> {
    const response = await apiClient.get<PendingDocumentsResponse>(
      `/connectors/${connectorId}/pending-documents?page=${page}&page_size=${pageSize}`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Get connector stats with error breakdown (admin)
   */
  async getConnectorStats(connectorId: string): Promise<{ data: ConnectorStats | null; error: string | null }> {
    const response = await apiClient.get<ConnectorStats>(`/connectors/${connectorId}/stats`)
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Get failed documents with details (admin)
   */
  async getFailedDocuments(
    connectorId: string,
    params?: { limit?: number; offset?: number; error_filter?: string }
  ): Promise<{ data: FailedDocumentsResponse | null; error: string | null }> {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.append('limit', params.limit.toString())
    if (params?.offset) searchParams.append('offset', params.offset.toString())
    if (params?.error_filter) searchParams.append('error_filter', params.error_filter)

    const url = `/connectors/${connectorId}/failed-documents?${searchParams.toString()}`
    const response = await apiClient.get<FailedDocumentsResponse>(url)
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Retry failed documents (admin)
   */
  async retryFailedDocuments(
    connectorId: string,
    params?: { document_ids?: string[]; error_filter?: string }
  ): Promise<{ data: RetryFailedResponse | null; error: string | null }> {
    const response = await apiClient.post<RetryFailedResponse>(
      `/connectors/${connectorId}/retry-failed`,
      {
        document_ids: params?.document_ids || null,
        error_filter: params?.error_filter || null,
      }
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Index pending with retry failed option (admin)
   */
  async indexPendingWithRetry(
    connectorId: string,
    options?: { batchSize?: number; maxDocuments?: number; retryFailed?: boolean }
  ): Promise<{ data: IndexPendingResponse | null; error: string | null }> {
    const params = new URLSearchParams()
    params.append('batch_size', (options?.batchSize || 10).toString())
    if (options?.maxDocuments) params.append('max_documents', options.maxDocuments.toString())
    if (options?.retryFailed) params.append('retry_failed', 'true')

    const response = await apiClient.post<IndexPendingResponse>(
      `/connectors/${connectorId}/index-pending?${params.toString()}`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  // ==========================================================================
  // OAuth & Folder methods (Google Drive, OneDrive)
  // ==========================================================================

  /**
   * Get the OAuth authorize URL from the backend (authenticated request)
   */
  async getOAuthAuthorizeUrl(connectorId: string): Promise<{ data: { auth_url: string } | null; error: string | null }> {
    const response = await apiClient.get<{ auth_url: string }>(`/connectors/${connectorId}/oauth/authorize`)
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Check OAuth status for a Google Drive connector
   */
  async getOAuthStatus(connectorId: string): Promise<{ data: OAuthStatus | null; error: string | null }> {
    const response = await apiClient.get<OAuthStatus>(`/connectors/${connectorId}/oauth/status`)
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Revoke OAuth authorization for a Google Drive connector
   */
  async revokeOAuth(connectorId: string): Promise<{ error: string | null }> {
    const response = await apiClient.post(`/connectors/${connectorId}/oauth/revoke`)
    if (response.error) {
      return { error: response.error }
    }
    return { error: null }
  }

  /**
   * List Google Drive folders
   */
  async listFolders(connectorId: string, parentId = 'root'): Promise<{ data: DriveFolder[] | null; error: string | null }> {
    const response = await apiClient.get<DriveFolder[]>(
      `/connectors/${connectorId}/folders?parent_id=${encodeURIComponent(parentId)}`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Update connector config (e.g., to set folder_id)
   */
  async updateConnectorConfig(connectorId: string, config: Record<string, any>): Promise<{ data: Connector | null; error: string | null }> {
    return this.updateConnector(connectorId, { config })
  }
}

// OAuth types (Google Drive, OneDrive)
export interface OAuthStatus {
  connected: boolean
  google_email?: string
  microsoft_email?: string
  email?: string  // generic field
  folder_id?: string
}

export interface DriveFolder {
  id: string
  name: string
}

// Health check response type
export interface HealthCheckResponse {
  connector_id: string
  status: ConnectorHealthStatus
  message: string
  checked_at: string
  details: Record<string, any> | null
}

// Sync trigger response type
export interface SyncTriggerResponse {
  status: string
  task_id: string
  connector_id: string
  message: string
  pending_count?: number
  failed_reset?: number
}

// Index pending response type
export interface IndexPendingResponse {
  status: string
  task_id: string
  connector_id: string
  pending_count: number
  message: string
}

// Pending document type
export interface PendingDocument {
  id: string
  connector_id: string
  external_id: string
  external_path: string | null
  title: string
  mime_type: string | null
  indexing_status: string
  indexing_error: string | null
  created_at: string
}

// Pending documents list response
export interface PendingDocumentsResponse {
  items: PendingDocument[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// Failed document with full details
export interface FailedDocument {
  id: string
  title: string
  external_id: string | null
  external_path: string | null
  external_url: string | null
  file_extension: string | null
  mime_type: string | null
  size_bytes: number | null
  indexing_error: string | null
  updated_at: string | null
  source_modified_at: string | null
  actions: {
    can_retry: boolean
    can_skip: boolean
    can_preview: boolean
  }
}

// Failed documents list response
export interface FailedDocumentsResponse {
  connector_id: string
  total_count: number
  offset: number
  limit: number
  items: FailedDocument[]
}

// Retry failed response
export interface RetryFailedResponse {
  success: boolean
  reset_count: number
  message: string
}

// Error breakdown type
export interface ErrorBreakdown {
  count: number
  error: string
}

// Enhanced connector stats with error breakdown
export interface ConnectorStats {
  connector_id: string
  authorizations: {
    total: number
    valid: number
  }
  syncs: {
    total_users: number
    users_enabled: number
    documents_total: number
    documents_indexed: number
    documents_failed: number
    total_size_bytes: number
  }
  documents: {
    total: number
    pending: number
    processing: number
    indexed: number
    failed: number
    total_size_bytes: number
    last_indexed_at: string | null
    avg_indexing_seconds: number | null  // Historical average time per document
    errors_by_type: ErrorBreakdown[]
  }
}

export const connectorService = new ConnectorService()

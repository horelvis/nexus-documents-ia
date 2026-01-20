/**
 * Connector Service - Types and API hooks for external data source connectors
 *
 * Connectors are admin-managed integrations that allow users to sync documents
 * from external sources like SharePoint, Google Drive, Alfresco, etc.
 */

import { useApiClient } from '@/lib/api-client'

// =============================================================================
// Enums
// =============================================================================

export enum ConnectorType {
  SHAREPOINT = 'sharepoint',
  ONEDRIVE = 'onedrive',
  GOOGLE_DRIVE = 'google_drive',
  GOOGLE_WORKSPACE = 'google_workspace',
  DROPBOX = 'dropbox',
  BOX = 'box',
  S3 = 's3',
  AZURE_BLOB = 'azure_blob',
  NETWORK_SHARE = 'network_share',
  ALFRESCO = 'alfresco',
}

export enum ConnectorAuthType {
  DELEGATED = 'delegated',
  SERVICE_ACCOUNT = 'service_account',
  API_KEY = 'api_key',
}

export enum ConnectorHealthStatus {
  HEALTHY = 'healthy',
  DEGRADED = 'degraded',
  UNHEALTHY = 'unhealthy',
  UNKNOWN = 'unknown',
}

// =============================================================================
// Connector Types
// =============================================================================

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
  // Document processing counts
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

export interface HealthCheckResponse {
  connector_id: string
  status: ConnectorHealthStatus
  message: string
  checked_at: string
  details: Record<string, any> | null
}

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
  // Real document processing stats from IndexedDocument table
  documents: {
    total: number
    pending: number
    processing: number
    indexed: number
    failed: number
    total_size_bytes: number
    last_indexed_at: string | null
  }
}

// =============================================================================
// Sync & Index Response Types
// =============================================================================

export interface SyncTriggerResponse {
  status: 'queued' | 'error'
  task_id: string
  connector_id: string
  message: string
}

export interface IndexPendingResponse {
  status: 'queued' | 'no_pending' | 'error'
  task_id?: string
  connector_id: string
  pending_count: number
  message: string
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
  indexing_status: 'pending' | 'processing' | 'indexed' | 'failed' | 'orphaned'
  indexing_error: string | null
  source_created_at: string | null
  source_modified_at: string | null
  indexed_at: string | null
}

export interface PendingDocumentsResponse {
  items: IndexedDocument[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// =============================================================================
// Config Types for each Connector
// =============================================================================

export interface SharePointConfig {
  tenant_id: string
  client_id: string
  client_secret?: string
  site_url?: string
  drive_id?: string
}

export interface OneDriveConfig {
  tenant_id: string
  client_id: string
  client_secret?: string
}

export interface GoogleWorkspaceConfig {
  client_id: string
  client_secret: string
  domain?: string
  service_account_json?: string
}

export interface S3Config {
  bucket_name: string
  region?: string
  access_key_id?: string
  secret_access_key?: string
  prefix?: string
  role_arn?: string
}

export interface AzureBlobConfig {
  storage_account: string
  container_name: string
  connection_string?: string
  prefix?: string
}

export interface NetworkShareConfig {
  server: string
  share_name: string
  domain?: string
  username?: string
  password?: string
  base_path?: string
}

export interface AlfrescoConfig {
  url: string
  username: string
  password: string
  api_path?: string
  search_api_path?: string
  default_site_id?: string
  default_folder_id?: string
  timeout_seconds?: number
  download_timeout_seconds?: number
  max_results?: number
  max_upload_size_mb?: number
  // AFTS Sync Filters
  afts_type_filter?: string[]
  afts_aspect_filter?: string[]
  afts_path_filter?: string
  afts_mime_types?: string[]
  afts_custom_query?: string
  afts_exclude_paths?: string[]
}

export type ConnectorConfig =
  | SharePointConfig
  | OneDriveConfig
  | GoogleWorkspaceConfig
  | S3Config
  | AzureBlobConfig
  | NetworkShareConfig
  | AlfrescoConfig

// =============================================================================
// Connector Metadata (for UI)
// =============================================================================

export interface ConnectorTypeInfo {
  type: ConnectorType
  name: string
  description: string
  icon: string
  color: string
  authTypes: ConnectorAuthType[]
  configFields: ConfigField[]
}

export interface ConfigField {
  name: string
  label: string
  type: 'text' | 'password' | 'number' | 'select' | 'textarea'
  required: boolean
  placeholder?: string
  description?: string
  defaultValue?: string | number
  options?: { value: string; label: string }[]
  min?: number
  max?: number
}

export const CONNECTOR_TYPE_INFO: Record<ConnectorType, ConnectorTypeInfo> = {
  [ConnectorType.SHAREPOINT]: {
    type: ConnectorType.SHAREPOINT,
    name: 'SharePoint',
    description: 'Microsoft SharePoint Online document libraries',
    icon: 'sharepoint',
    color: 'blue',
    authTypes: [ConnectorAuthType.DELEGATED, ConnectorAuthType.SERVICE_ACCOUNT],
    configFields: [
      { name: 'tenant_id', label: 'Azure AD Tenant ID', type: 'text', required: true, placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
      { name: 'client_id', label: 'App Client ID', type: 'text', required: true, placeholder: 'Azure AD application client ID' },
      { name: 'client_secret', label: 'Client Secret', type: 'password', required: false, description: 'Required for service account auth' },
      { name: 'site_url', label: 'Site URL', type: 'text', required: false, placeholder: 'https://company.sharepoint.com/sites/documents' },
      { name: 'drive_id', label: 'Drive ID', type: 'text', required: false, placeholder: 'Optional: specific drive ID' },
    ],
  },
  [ConnectorType.ONEDRIVE]: {
    type: ConnectorType.ONEDRIVE,
    name: 'OneDrive',
    description: 'OneDrive for Business personal storage',
    icon: 'onedrive',
    color: 'blue',
    authTypes: [ConnectorAuthType.DELEGATED, ConnectorAuthType.SERVICE_ACCOUNT],
    configFields: [
      { name: 'tenant_id', label: 'Azure AD Tenant ID', type: 'text', required: true },
      { name: 'client_id', label: 'App Client ID', type: 'text', required: true },
      { name: 'client_secret', label: 'Client Secret', type: 'password', required: false },
    ],
  },
  [ConnectorType.GOOGLE_DRIVE]: {
    type: ConnectorType.GOOGLE_DRIVE,
    name: 'Google Drive',
    description: 'Google Drive personal and shared drives',
    icon: 'google-drive',
    color: 'yellow',
    authTypes: [ConnectorAuthType.DELEGATED],
    configFields: [
      { name: 'client_id', label: 'OAuth Client ID', type: 'text', required: true },
      { name: 'client_secret', label: 'OAuth Client Secret', type: 'password', required: true },
    ],
  },
  [ConnectorType.GOOGLE_WORKSPACE]: {
    type: ConnectorType.GOOGLE_WORKSPACE,
    name: 'Google Workspace',
    description: 'Google Workspace with domain-wide delegation',
    icon: 'google',
    color: 'red',
    authTypes: [ConnectorAuthType.SERVICE_ACCOUNT],
    configFields: [
      { name: 'client_id', label: 'OAuth Client ID', type: 'text', required: true },
      { name: 'client_secret', label: 'OAuth Client Secret', type: 'password', required: true },
      { name: 'domain', label: 'G Suite Domain', type: 'text', required: false, placeholder: 'company.com' },
      { name: 'service_account_json', label: 'Service Account JSON', type: 'textarea', required: false, description: 'Paste the full service account JSON' },
    ],
  },
  [ConnectorType.DROPBOX]: {
    type: ConnectorType.DROPBOX,
    name: 'Dropbox',
    description: 'Dropbox Business file storage',
    icon: 'dropbox',
    color: 'blue',
    authTypes: [ConnectorAuthType.DELEGATED],
    configFields: [
      { name: 'client_id', label: 'App Key', type: 'text', required: true },
      { name: 'client_secret', label: 'App Secret', type: 'password', required: true },
    ],
  },
  [ConnectorType.BOX]: {
    type: ConnectorType.BOX,
    name: 'Box',
    description: 'Box cloud content management',
    icon: 'box',
    color: 'blue',
    authTypes: [ConnectorAuthType.DELEGATED, ConnectorAuthType.SERVICE_ACCOUNT],
    configFields: [
      { name: 'client_id', label: 'Client ID', type: 'text', required: true },
      { name: 'client_secret', label: 'Client Secret', type: 'password', required: true },
    ],
  },
  [ConnectorType.S3]: {
    type: ConnectorType.S3,
    name: 'Amazon S3',
    description: 'AWS S3 bucket storage',
    icon: 'aws',
    color: 'orange',
    authTypes: [ConnectorAuthType.SERVICE_ACCOUNT, ConnectorAuthType.API_KEY],
    configFields: [
      { name: 'bucket_name', label: 'Bucket Name', type: 'text', required: true },
      { name: 'region', label: 'AWS Region', type: 'text', required: false, defaultValue: 'us-east-1' },
      { name: 'access_key_id', label: 'Access Key ID', type: 'text', required: false },
      { name: 'secret_access_key', label: 'Secret Access Key', type: 'password', required: false },
      { name: 'prefix', label: 'Key Prefix', type: 'text', required: false, placeholder: 'documents/' },
      { name: 'role_arn', label: 'IAM Role ARN', type: 'text', required: false, description: 'For assumed role access' },
    ],
  },
  [ConnectorType.AZURE_BLOB]: {
    type: ConnectorType.AZURE_BLOB,
    name: 'Azure Blob Storage',
    description: 'Azure Blob Storage containers',
    icon: 'azure',
    color: 'blue',
    authTypes: [ConnectorAuthType.SERVICE_ACCOUNT],
    configFields: [
      { name: 'storage_account', label: 'Storage Account', type: 'text', required: true },
      { name: 'container_name', label: 'Container Name', type: 'text', required: true },
      { name: 'connection_string', label: 'Connection String', type: 'password', required: false },
      { name: 'prefix', label: 'Blob Prefix', type: 'text', required: false },
    ],
  },
  [ConnectorType.NETWORK_SHARE]: {
    type: ConnectorType.NETWORK_SHARE,
    name: 'Network Share',
    description: 'SMB/CIFS network file shares',
    icon: 'server',
    color: 'gray',
    authTypes: [ConnectorAuthType.SERVICE_ACCOUNT],
    configFields: [
      { name: 'server', label: 'Server', type: 'text', required: true, placeholder: 'fileserver.company.local' },
      { name: 'share_name', label: 'Share Name', type: 'text', required: true, placeholder: 'documents$' },
      { name: 'domain', label: 'AD Domain', type: 'text', required: false },
      { name: 'username', label: 'Username', type: 'text', required: false },
      { name: 'password', label: 'Password', type: 'password', required: false },
      { name: 'base_path', label: 'Base Path', type: 'text', required: false, placeholder: '/department/files' },
    ],
  },
  [ConnectorType.ALFRESCO]: {
    type: ConnectorType.ALFRESCO,
    name: 'Alfresco',
    description: 'Alfresco Content Services (7.x)',
    icon: 'alfresco',
    color: 'green',
    authTypes: [ConnectorAuthType.SERVICE_ACCOUNT],
    configFields: [
      { name: 'url', label: 'Alfresco URL', type: 'text', required: true, placeholder: 'https://alfresco.company.com' },
      { name: 'username', label: 'Username', type: 'text', required: true, placeholder: 'admin' },
      { name: 'password', label: 'Password', type: 'password', required: true },
      { name: 'api_path', label: 'API Path', type: 'text', required: false, defaultValue: '/alfresco/api/-default-/public/alfresco/versions/1' },
      { name: 'search_api_path', label: 'Search API Path', type: 'text', required: false, defaultValue: '/alfresco/api/-default-/public/search/versions/1' },
      { name: 'default_site_id', label: 'Default Site ID', type: 'text', required: false, placeholder: 'mysite', description: 'Filter by Alfresco site' },
      { name: 'default_folder_id', label: 'Default Folder ID', type: 'text', required: false, description: 'Start sync from this folder (node UUID)' },
      { name: 'timeout_seconds', label: 'Timeout (seconds)', type: 'number', required: false, defaultValue: 60, min: 10, max: 300 },
      { name: 'max_results', label: 'Max Search Results', type: 'number', required: false, defaultValue: 100, min: 10, max: 1000 },
      // AFTS Filter Fields
      { name: 'afts_type_filter', label: 'Node Types (AFTS)', type: 'text', required: false, placeholder: 'cm:content, cm:document', description: 'Comma-separated node types to sync (e.g., cm:content)' },
      { name: 'afts_aspect_filter', label: 'Aspects Filter (AFTS)', type: 'text', required: false, placeholder: 'cm:titled, cm:versionable', description: 'Comma-separated aspects to filter by' },
      { name: 'afts_path_filter', label: 'Path Filter (AFTS)', type: 'text', required: false, placeholder: '/app:company_home/st:sites/cm:mysite/cm:documentLibrary//*', description: 'AFTS path pattern to restrict sync scope' },
      { name: 'afts_mime_types', label: 'MIME Types', type: 'text', required: false, placeholder: 'application/pdf, application/msword', description: 'Comma-separated MIME types to sync' },
      { name: 'afts_custom_query', label: 'Custom AFTS Query', type: 'textarea', required: false, placeholder: '@cm\\:author:"John Doe"', description: 'Custom AFTS query fragment (combined with AND)' },
      { name: 'afts_exclude_paths', label: 'Exclude Paths', type: 'text', required: false, placeholder: '/app:company_home/st:sites/cm:archive//*', description: 'Comma-separated paths to exclude from sync' },
    ],
  },
}

// =============================================================================
// Service Hook
// =============================================================================

export function useConnectorService() {
  const apiClient = useApiClient()

  return {
    // List all connectors
    async getConnectors(filters?: {
      connector_type?: ConnectorType
      is_active?: boolean
      page?: number
      page_size?: number
    }): Promise<ConnectorListResponse> {
      const params = new URLSearchParams()
      if (filters) {
        if (filters.connector_type) params.append('connector_type', filters.connector_type)
        if (filters.is_active !== undefined) params.append('is_active', String(filters.is_active))
        if (filters.page) params.append('page', String(filters.page))
        if (filters.page_size) params.append('page_size', String(filters.page_size))
      }
      const endpoint = params.toString() ? `/connectors?${params}` : '/connectors'
      const response = await apiClient.get(endpoint)
      return response.data
    },

    // Get single connector
    async getConnector(connectorId: string): Promise<Connector> {
      const response = await apiClient.get(`/connectors/${connectorId}`)
      return response.data
    },

    // Create connector
    async createConnector(data: CreateConnectorData): Promise<Connector> {
      const response = await apiClient.post('/connectors', data)
      return response.data
    },

    // Update connector
    async updateConnector(connectorId: string, data: UpdateConnectorData): Promise<Connector> {
      const response = await apiClient.put(`/connectors/${connectorId}`, data)
      return response.data
    },

    // Delete connector
    async deleteConnector(connectorId: string): Promise<void> {
      await apiClient.delete(`/connectors/${connectorId}`)
    },

    // Health check
    async checkHealth(connectorId: string): Promise<HealthCheckResponse> {
      const response = await apiClient.post(`/connectors/${connectorId}/health-check`)
      return response.data
    },

    // Get statistics
    async getStats(connectorId: string): Promise<ConnectorStats> {
      const response = await apiClient.get(`/connectors/${connectorId}/stats`)
      return response.data
    },

    // Trigger manual sync (sync + index)
    async triggerSync(connectorId: string, fullSync: boolean = false): Promise<SyncTriggerResponse> {
      const response = await apiClient.post(`/connectors/${connectorId}/sync?full_sync=${fullSync}`)
      return response.data
    },

    // Trigger indexing of pending documents only
    async triggerIndexPending(
      connectorId: string,
      options?: { batch_size?: number; max_documents?: number }
    ): Promise<IndexPendingResponse> {
      const params = new URLSearchParams()
      if (options?.batch_size) params.append('batch_size', String(options.batch_size))
      if (options?.max_documents) params.append('max_documents', String(options.max_documents))
      const endpoint = params.toString()
        ? `/connectors/${connectorId}/index-pending?${params}`
        : `/connectors/${connectorId}/index-pending`
      const response = await apiClient.post(endpoint)
      return response.data
    },

    // Get pending documents
    async getPendingDocuments(
      connectorId: string,
      options?: { page?: number; page_size?: number }
    ): Promise<PendingDocumentsResponse> {
      const params = new URLSearchParams()
      if (options?.page) params.append('page', String(options.page))
      if (options?.page_size) params.append('page_size', String(options.page_size))
      const endpoint = params.toString()
        ? `/connectors/${connectorId}/pending-documents?${params}`
        : `/connectors/${connectorId}/pending-documents`
      const response = await apiClient.get(endpoint)
      return response.data
    },
  }
}

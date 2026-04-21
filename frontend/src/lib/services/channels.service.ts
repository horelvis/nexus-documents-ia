/**
 * Service for Information Channels API.
 * Handles Gmail, Google Drive, and External Database channels for RAG.
 */
import { useMemo } from "react"
import { useApiClient } from "@/lib/api-client"

// =============================================================================
// Types
// =============================================================================

export type ChannelType = "gmail" | "google_drive" | "external_db"
export type ChannelVisibility = "personal" | "tenant"
export type SyncStatus = "success" | "partial" | "failed" | "running"

export interface GmailConfig {
  labels: string[]
  max_age_days: number
  include_attachments: boolean
  attachment_types: string[]
  max_emails_per_sync: number
}

export interface GoogleDriveConfig {
  folder_id: string
  folder_name: string
  include_subfolders: boolean
  file_types: string[]
  max_file_size_mb: number
}

export interface ExternalDBConfig {
  db_type: "postgresql" | "mysql" | "sqlserver"
  host: string
  port: number
  database: string
  query: string
  id_column: string
  content_columns: string[]
  metadata_columns: string[]
  max_rows: number
}

export interface Channel {
  id: string
  created_by: string
  name: string
  description: string | null
  channel_type: ChannelType
  visibility: ChannelVisibility
  configuration: GmailConfig | GoogleDriveConfig | ExternalDBConfig | Record<string, any>
  is_active: boolean
  last_sync_at: string | null
  last_sync_status: SyncStatus | null
  last_sync_error: string | null
  documents_indexed: number
  sync_interval_minutes: number
  next_sync_at: string | null
  created_at: string
  updated_at: string
  oauth_email: string | null
  has_credentials: boolean
}

export interface ChannelListResponse {
  items: Channel[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface SyncLog {
  id: string
  channel_id: string
  started_at: string
  completed_at: string | null
  status: string
  trigger_type: string
  items_found: number
  items_new: number
  items_updated: number
  items_deleted: number
  items_failed: number
  error_message: string | null
}

export interface SyncHistoryResponse {
  items: SyncLog[]
  total: number
}

export interface ChannelDocument {
  id: string
  channel_id: string
  external_id: string
  external_url: string | null
  title: string | null
  weaviate_id: string | null
  status: string
  error_message: string | null
  source_created_at: string | null
  source_modified_at: string | null
  first_indexed_at: string | null
  last_indexed_at: string | null
}

export interface ChannelDocumentsResponse {
  items: ChannelDocument[]
  total: number
  page: number
  page_size: number
}

export interface CreateChannelParams {
  name: string
  description?: string
  channel_type: ChannelType
  visibility: ChannelVisibility
  configuration: Record<string, any>
  sync_interval_minutes?: number
}

export interface UpdateChannelParams {
  name?: string
  description?: string
  visibility?: ChannelVisibility
  configuration?: Record<string, any>
  is_active?: boolean
  sync_interval_minutes?: number
}

export interface OAuthUrlResponse {
  auth_url: string
  state: string
}

export interface SyncTriggerResponse {
  sync_id: string
  channel_id: string
  status: string
  message: string
}

// =============================================================================
// Service Class
// =============================================================================

export class ChannelsService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  /**
   * List channels accessible to the current user.
   */
  async listChannels(params: {
    channel_type?: ChannelType
    is_active?: boolean
    page?: number
    page_size?: number
  } = {}) {
    const searchParams = new URLSearchParams()
    if (params.channel_type) searchParams.append("channel_type", params.channel_type)
    if (params.is_active !== undefined) searchParams.append("is_active", String(params.is_active))
    if (params.page) searchParams.append("page", String(params.page))
    if (params.page_size) searchParams.append("page_size", String(params.page_size))

    const query = searchParams.toString()
    return this.apiClient.get<ChannelListResponse>(`/channels${query ? `?${query}` : ""}`)
  }

  /**
   * Get a single channel by ID.
   */
  async getChannel(channelId: string) {
    return this.apiClient.get<Channel>(`/channels/${channelId}`)
  }

  /**
   * Create a new channel.
   */
  async createChannel(params: CreateChannelParams) {
    return this.apiClient.post<Channel>("/channels", params)
  }

  /**
   * Update a channel.
   */
  async updateChannel(channelId: string, params: UpdateChannelParams) {
    return this.apiClient.put<Channel>(`/channels/${channelId}`, params)
  }

  /**
   * Delete a channel.
   */
  async deleteChannel(channelId: string) {
    return this.apiClient.delete(`/channels/${channelId}`)
  }

  /**
   * Get OAuth authorization URL for Google channels.
   */
  async getOAuthUrl(channelId: string) {
    return this.apiClient.get<OAuthUrlResponse>(`/channels/${channelId}/oauth-url`)
  }

  /**
   * Trigger manual sync for a channel.
   */
  async triggerSync(channelId: string, fullSync: boolean = false) {
    return this.apiClient.post<SyncTriggerResponse>(`/channels/${channelId}/sync`, {
      full_sync: fullSync,
    })
  }

  /**
   * Get sync history for a channel.
   */
  async getSyncHistory(channelId: string, limit: number = 20) {
    return this.apiClient.get<SyncHistoryResponse>(
      `/channels/${channelId}/sync-history?limit=${limit}`
    )
  }

  /**
   * Get documents indexed from a channel.
   */
  async getChannelDocuments(
    channelId: string,
    params: { status?: string; page?: number; page_size?: number } = {}
  ) {
    const searchParams = new URLSearchParams()
    if (params.status) searchParams.append("status", params.status)
    if (params.page) searchParams.append("page", String(params.page))
    if (params.page_size) searchParams.append("page_size", String(params.page_size))

    const query = searchParams.toString()
    return this.apiClient.get<ChannelDocumentsResponse>(
      `/channels/${channelId}/documents${query ? `?${query}` : ""}`
    )
  }

  /**
   * Set database credentials for external DB channel.
   */
  async setDBCredentials(channelId: string, username: string, password: string) {
    return this.apiClient.post(`/channels/${channelId}/db-credentials`, {
      username,
      password,
    })
  }

  /**
   * Test connection for external DB channel.
   */
  async testConnection(channelId: string) {
    return this.apiClient.post<{ success: boolean; message: string; row_count?: number }>(
      `/channels/${channelId}/test-connection`,
      {}
    )
  }
}

// =============================================================================
// Hook
// =============================================================================

export function useChannelsService() {
  const apiClient = useApiClient()
  return useMemo(() => new ChannelsService(apiClient), [apiClient])
}

// =============================================================================
// Helpers
// =============================================================================

export const CHANNEL_TYPE_LABELS: Record<ChannelType, string> = {
  gmail: "Gmail",
  google_drive: "Google Drive",
  external_db: "External Database",
}

export const CHANNEL_TYPE_ICONS: Record<ChannelType, string> = {
  gmail: "mail",
  google_drive: "folder-cloud",
  external_db: "database",
}

export const VISIBILITY_LABELS: Record<ChannelVisibility, string> = {
  personal: "Personal",
  tenant: "Shared with Team",
}

export const SYNC_STATUS_COLORS: Record<SyncStatus, string> = {
  success: "text-green-600",
  partial: "text-yellow-600",
  failed: "text-red-600",
  running: "text-blue-600",
}

export const DEFAULT_GMAIL_CONFIG: GmailConfig = {
  labels: ["INBOX"],
  max_age_days: 90,
  include_attachments: true,
  attachment_types: ["pdf", "docx", "doc", "xlsx", "xls", "txt"],
  max_emails_per_sync: 100,
}

export const DEFAULT_DRIVE_CONFIG: Partial<GoogleDriveConfig> = {
  folder_id: "",
  folder_name: "",
  include_subfolders: true,
  file_types: ["pdf", "docx", "doc", "xlsx", "xls", "txt", "pptx", "ppt"],
  max_file_size_mb: 50,
}

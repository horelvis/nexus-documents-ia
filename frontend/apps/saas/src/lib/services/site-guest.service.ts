import { useApiClient } from '../api-client'
import { API_CONFIG } from '../config'

// =====================================
// TYPE DEFINITIONS
// =====================================

export interface SiteGuest {
  id: string
  tenant_id: string
  email: string
  name: string | null
  is_active: boolean
  can_view: boolean
  can_download: boolean
  can_upload: boolean
  expires_at: string | null
  invited_by_user_id: string | null
  invited_at: string
  last_access_at: string | null
  access_count: number
  created_at: string
  updated_at: string
  is_expired: boolean
  is_valid: boolean
}

export interface SiteGuestListResponse {
  guests: SiteGuest[]
  total: number
  page: number
  per_page: number
}

export interface SiteGuestCreate {
  email: string
  name?: string
  can_view?: boolean
  can_download?: boolean
  can_upload?: boolean
  expires_at?: string
  send_invitation?: boolean
}

export interface SiteGuestUpdate {
  name?: string
  is_active?: boolean
  can_view?: boolean
  can_download?: boolean
  can_upload?: boolean
  expires_at?: string
}

export interface SiteGuestPermission {
  id: string
  guest_id: string
  document_id: string | null
  folder_path: string | null
  permission_type: 'view' | 'download' | 'upload'
  granted_by_user_id: string | null
  granted_at: string
  expires_at: string | null
  created_at: string
  document_title: string | null
  document_filename: string | null
}

export interface SiteGuestPermissionList {
  permissions: SiteGuestPermission[]
  total: number
}

export interface DocumentPermissionCreate {
  document_id: string
  permission_type: 'view' | 'download' | 'upload'
  expires_at?: string
}

export interface FolderPermissionCreate {
  folder_path: string
  permission_type: 'view' | 'download' | 'upload'
  expires_at?: string
}

export interface SiteGuestAccessLog {
  id: string
  guest_id: string
  session_id: string | null
  action: string
  success: boolean
  error_message: string | null
  document_id: string | null
  folder_path: string | null
  ip_address: string | null
  user_agent: string | null
  details: Record<string, any> | null
  created_at: string
  document_title: string | null
}

export interface SiteGuestAccessLogList {
  logs: SiteGuestAccessLog[]
  total: number
  page: number
  per_page: number
}

export interface SiteSiteSettings {
  site_enabled: boolean
  site_logo_url: string | null
  site_welcome_message: string | null
  slug: string | null
  guest_count: number
  active_guest_count: number
}

export interface SiteSettingsUpdate {
  site_enabled?: boolean
  site_logo_url?: string
  site_welcome_message?: string
  slug?: string
}

export interface SiteGuestStatistics {
  total_guests: number
  active_guests: number
  inactive_guests: number
  expired_guests: number
  total_access_count: number
  recent_accesses: number
  documents_shared: number
  folders_shared: number
  access_by_action: Record<string, number>
  access_by_date: Record<string, number>
}

// =====================================
// SHARE/COLLECTION TYPES (Virtual Folders)
// =====================================

export interface CreateGuestWithShareRequest {
  email: string
  name?: string
  share_name: string
  share_description?: string
  document_ids: string[]
  permission_type: 'view' | 'download' | 'upload'
  expires_at?: string
  send_invitation: boolean
}

export interface SiteGuestShare {
  id: string
  name: string
  description: string | null
  permission_type: string
  document_count: number
  created_at: string
  expires_at: string | null
}

export interface SiteGuestShareDocument {
  id: string
  title: string
  filename: string
  file_type: string
  file_size: number
  mime_type: string | null
  created_at: string
}

export interface SiteGuestShareDetail extends SiteGuestShare {
  documents: SiteGuestShareDocument[]
}

export interface CreateGuestWithShareResponse {
  guest: SiteGuest
  share: SiteGuestShare
  is_new_guest: boolean
  message: string
}

export interface SiteGuestShareList {
  shares: SiteGuestShare[]
  total: number
}

// =====================================
// ADMIN SERVICE CLASS
// =====================================

export class SiteGuestService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  // --- Site Settings ---

  async getSiteSettings() {
    return this.apiClient.get<SiteSiteSettings>(API_CONFIG.ENDPOINTS.SITE_GUESTS_SETTINGS)
  }

  async updateSiteSettings(settings: SiteSettingsUpdate) {
    return this.apiClient.put<SiteSiteSettings>(API_CONFIG.ENDPOINTS.SITE_GUESTS_SETTINGS, settings)
  }

  async getSiteStatistics() {
    return this.apiClient.get<SiteGuestStatistics>(API_CONFIG.ENDPOINTS.SITE_GUESTS_STATISTICS)
  }

  // --- Guest Management ---

  async listGuests(params: { page?: number; per_page?: number; include_inactive?: boolean } = {}) {
    const searchParams = new URLSearchParams()
    if (params.page) searchParams.set('page', params.page.toString())
    if (params.per_page) searchParams.set('per_page', params.per_page.toString())
    if (params.include_inactive) searchParams.set('include_inactive', 'true')

    const query = searchParams.toString() ? `?${searchParams.toString()}` : ''
    return this.apiClient.get<SiteGuestListResponse>(`${API_CONFIG.ENDPOINTS.SITE_GUESTS}${query}`)
  }

  async createGuest(data: SiteGuestCreate) {
    return this.apiClient.post<SiteGuest>(API_CONFIG.ENDPOINTS.SITE_GUESTS, data)
  }

  async getGuest(guestId: string) {
    return this.apiClient.get<SiteGuest>(API_CONFIG.ENDPOINTS.SITE_GUEST_BY_ID(guestId))
  }

  async updateGuest(guestId: string, data: SiteGuestUpdate) {
    return this.apiClient.put<SiteGuest>(API_CONFIG.ENDPOINTS.SITE_GUEST_BY_ID(guestId), data)
  }

  async deactivateGuest(guestId: string) {
    return this.apiClient.delete<{ message: string }>(API_CONFIG.ENDPOINTS.SITE_GUEST_BY_ID(guestId))
  }

  async resendInvitation(guestId: string, customMessage?: string) {
    return this.apiClient.post<{ message: string }>(
      API_CONFIG.ENDPOINTS.SITE_GUEST_INVITE(guestId),
      customMessage ? { custom_message: customMessage } : {}
    )
  }

  // --- Permission Management ---

  async listGuestPermissions(guestId: string) {
    return this.apiClient.get<SiteGuestPermissionList>(API_CONFIG.ENDPOINTS.SITE_GUEST_PERMISSIONS(guestId))
  }

  async grantDocumentPermission(guestId: string, data: DocumentPermissionCreate) {
    return this.apiClient.post<SiteGuestPermission>(
      API_CONFIG.ENDPOINTS.SITE_GUEST_PERMISSION_DOCUMENT(guestId),
      data
    )
  }

  async grantFolderPermission(guestId: string, data: FolderPermissionCreate) {
    return this.apiClient.post<SiteGuestPermission>(
      API_CONFIG.ENDPOINTS.SITE_GUEST_PERMISSION_FOLDER(guestId),
      data
    )
  }

  async revokePermission(guestId: string, permissionId: string) {
    return this.apiClient.delete<{ message: string }>(
      API_CONFIG.ENDPOINTS.SITE_GUEST_REVOKE_PERMISSION(guestId, permissionId)
    )
  }

  // --- Access Logs ---

  async getGuestAccessLogs(guestId: string, params: { page?: number; per_page?: number } = {}) {
    const searchParams = new URLSearchParams()
    if (params.page) searchParams.set('page', params.page.toString())
    if (params.per_page) searchParams.set('per_page', params.per_page.toString())

    const query = searchParams.toString() ? `?${searchParams.toString()}` : ''
    return this.apiClient.get<SiteGuestAccessLogList>(
      `${API_CONFIG.ENDPOINTS.SITE_GUEST_ACCESS_LOGS(guestId)}${query}`
    )
  }

  // --- Share/Collection Management ---

  /**
   * Create a new guest (or reuse existing by email) and share documents with them.
   * This is the simplified flow from the Documents page.
   */
  async createGuestWithShare(data: CreateGuestWithShareRequest) {
    return this.apiClient.post<CreateGuestWithShareResponse>(
      API_CONFIG.ENDPOINTS.SITE_GUEST_WITH_SHARE,
      data
    )
  }

  /**
   * List all shares/collections for a specific guest.
   */
  async listGuestShares(guestId: string) {
    return this.apiClient.get<SiteGuestShareList>(
      API_CONFIG.ENDPOINTS.SITE_GUEST_SHARES(guestId)
    )
  }
}

// =====================================
// PORTAL SERVICE CLASS (Public - No Auth)
// =====================================

export interface TenantSiteInfo {
  tenant_id: string
  tenant_name: string
  slug: string
  site_enabled: boolean
  logo_url: string | null
  welcome_message: string | null
}

export interface OTPRequestResponse {
  success: boolean
  message: string
  expires_in_seconds: number
}

export interface OTPVerifyResponse {
  success: boolean
  session_token: string | null
  expires_at: string | null
  guest: SiteGuest | null
  error: string | null
}

export interface GuestMeResponse {
  guest: SiteGuest
  tenant_name: string
  tenant_logo_url: string | null
  session_expires_at: string
}

export interface PortalDocument {
  id: string
  title: string
  filename: string
  file_type: string
  file_size: number
  mime_type: string | null
  folder_path: string | null
  created_at: string
  updated_at: string
  can_view: boolean
  can_download: boolean
}

export interface PortalFolder {
  path: string
  name: string
  document_count: number
  can_view: boolean
  can_download: boolean
  can_upload: boolean
}

export interface PortalShare {
  id: string
  name: string
  description: string | null
  permission_type: 'view' | 'download' | 'upload'
  document_count: number
  created_at: string
  expires_at: string | null
}

export interface PortalShareDocumentsResponse {
  share: PortalShare
  documents: PortalDocument[]
  total_documents: number
}

export interface PortalContentResponse {
  shares: PortalShare[]
  total_shares: number
  documents: PortalDocument[]
  folders: PortalFolder[]
  total_documents: number
  total_folders: number
}

export interface DocumentViewResponse {
  view_url: string
  content_type: string
}

/**
 * Portal service for guest access (uses session token instead of Clerk auth)
 */
export class SitePortalService {
  private baseUrl: string
  private sessionToken: string | null = null

  constructor() {
    this.baseUrl = `${API_CONFIG.BASE_URL}${API_CONFIG.API_V1}`
  }

  setSessionToken(token: string | null) {
    this.sessionToken = token
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<{ data?: T; error?: string }> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {})
    }

    if (this.sessionToken) {
      headers['Authorization'] = `Bearer ${this.sessionToken}`
    }

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        return { error: errorData.detail || `Request failed: ${response.status}` }
      }

      const data = await response.json()
      return { data }
    } catch (error) {
      return { error: error instanceof Error ? error.message : 'Network error' }
    }
  }

  // --- Public (No Auth) ---

  async getTenantBySlug(slug: string) {
    return this.request<TenantSiteInfo>(API_CONFIG.ENDPOINTS.SITE_PORTAL_TENANT(slug))
  }

  async requestOTP(slug: string, email: string) {
    return this.request<OTPRequestResponse>(API_CONFIG.ENDPOINTS.SITE_PORTAL_REQUEST_OTP(slug), {
      method: 'POST',
      body: JSON.stringify({ email })
    })
  }

  async verifyOTP(slug: string, email: string, otpCode: string) {
    return this.request<OTPVerifyResponse>(API_CONFIG.ENDPOINTS.SITE_PORTAL_VERIFY_OTP(slug), {
      method: 'POST',
      body: JSON.stringify({ email, otp_code: otpCode })
    })
  }

  // --- Authenticated (Requires Session Token) ---

  async logout() {
    return this.request<{ message: string }>(API_CONFIG.ENDPOINTS.SITE_PORTAL_LOGOUT, {
      method: 'POST'
    })
  }

  async getMe() {
    return this.request<GuestMeResponse>(API_CONFIG.ENDPOINTS.SITE_PORTAL_ME)
  }

  async getContent() {
    return this.request<PortalContentResponse>(API_CONFIG.ENDPOINTS.SITE_PORTAL_CONTENT)
  }

  async getShareDocuments(shareId: string) {
    return this.request<PortalShareDocumentsResponse>(
      API_CONFIG.ENDPOINTS.SITE_PORTAL_SHARE_DOCUMENTS(shareId)
    )
  }

  async getDocument(documentId: string) {
    return this.request<PortalDocument>(API_CONFIG.ENDPOINTS.SITE_PORTAL_DOCUMENT(documentId))
  }

  async getDocumentViewUrl(documentId: string) {
    return this.request<DocumentViewResponse>(API_CONFIG.ENDPOINTS.SITE_PORTAL_DOCUMENT_VIEW(documentId))
  }

  getDocumentDownloadUrl(documentId: string) {
    // Returns the direct download URL (will redirect to signed GCS URL)
    return `${this.baseUrl}${API_CONFIG.ENDPOINTS.SITE_PORTAL_DOCUMENT_DOWNLOAD(documentId)}`
  }
}

// =====================================
// HOOKS
// =====================================

import { useMemo } from 'react'

export function useSiteGuestService() {
  const apiClient = useApiClient()
  return useMemo(() => new SiteGuestService(apiClient), [apiClient])
}

export function useSitePortalService() {
  return useMemo(() => new SitePortalService(), [])
}

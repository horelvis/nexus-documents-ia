import { z } from 'zod'

export const EditUserProfileSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  email: z.string().email('Invalid email address'),
})

export const UploadDocumentSchema = z.object({
  category: z.string().optional(),
  tags: z.string().optional(),
  description: z.string().optional(),
  files: z.array(z.instanceof(File)).min(1, 'At least one file is required'),
})

export type UploadDocumentFormData = z.infer<typeof UploadDocumentSchema>

// API Response Types
export interface User {
  id: string
  email: string
  full_name?: string
  is_active: boolean
  is_superuser: boolean
  created_at: string
  updated_at: string
}

export interface Tenant {
  id: string
  name: string
  domain?: string
  is_active: boolean
  created_at: string
  updated_at: string
  settings?: Record<string, unknown>
}

// Tipos para entidades extraídas
export interface ExtractedEntity {
  class: string
  text: string
  attributes: Record<string, any>
  source_indices?: [number, number] | null
}

// Tipos para metadata estructurada del documento
export interface DocumentMetadata {
  categorization?: {
    timestamp?: string
    confidence?: number
    reasoning?: string
    method?: string
    alternative_types?: Array<{ type: string; confidence: number }>
    visualization_html?: string
  }
  extraction_summary?: {
    // Para nóminas
    trabajador?: string
    periodo?: string
    liquido_total?: string
    salario_base?: string
    // Para facturas
    invoice_number?: string
    customer?: string
    total_amount?: string
    dates?: Record<string, string>
    // Para contratos
    parties?: string[]
    // Otros campos dinámicos
    [key: string]: any
  }
  text_preview?: string
  summary?: string
  [key: string]: any
}

export interface Document {
  id: string
  filename: string
  original_filename?: string
  title?: string
  description?: string
  file_size: number
  file_type: string
  mime_type?: string
  category?: string
  tags: string[]
  indexed: string
  status?: 'uploading' | 'processing' | 'processed' | 'error' | 'active' // Keep for backward compatibility
  summary?: string
  language?: string
  created_by: string | any // Allow object for populated user
  user_id?: string // Keep for backward compatibility
  created_at: string
  updated_at: string
  processed_at?: string
  gcs_path?: string
  storage_path?: string
  download_url?: string
  error_message?: string
  search_matches?: { text: string; score: number }[] | string[]
  file_hash?: string
  version?: number
  document_metadata?: DocumentMetadata
  content?: string
  extracted_entities?: ExtractedEntity[]
  ocr_status?: string
  ocr_completed_at?: string
  signature_fields?: unknown
}

export interface DocumentUploadResponse {
  id: string
  filename: string
  status: string
  message: string
}

export interface SearchResult {
  id: string
  filename: string
  title?: string
  content_snippet: string
  similarity_score: number
  category?: string
  tags: string[]
  created_at: string
}

export interface SearchResponse {
  results: SearchResult[]
  total: number
  query: string
  took_ms: number
}

export interface ChatMessage {
  id: string
  content: string
  role: 'user' | 'assistant'
  created_at: string
  sources?: {
    document_id: string
    filename: string
    snippet: string
  }[]
}

export interface ChatResponse {
  message: ChatMessage
  sources: SearchResult[]
}

export interface Agent {
  id: string
  name: string
  description: string
  type: string
  status: 'active' | 'inactive'
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface DigitalSignature {
  id: string
  document_id: string
  status: 'pending' | 'signed' | 'rejected'
  signer_email: string
  signature_data?: string
  created_at: string
  signed_at?: string
}

// User Context Types
export interface BackendUser {
  id: string
  email: string
  full_name?: string
  is_active: boolean
  is_superuser: boolean
  is_team_member?: boolean
  is_admin?: boolean
  onboarding_completed: boolean
  clerk_user_id?: string
  stripe_customer_id?: string
  created_at: string
  updated_at: string
  // Subscription info from Stripe (populated dynamically)
  subscription_plan?: string
  subscription_status?: string
  trial_ends_at?: string
  selected_plan?: string
}

/**
 * Subscription information from Stripe (returned by POST /auth/login)
 */
export interface SubscriptionInfo {
  plan: string                        // trial, basic, pro, enterprise
  status: string                      // active, trialing, past_due, canceled
  can_use_agents: boolean
  can_use_advanced_features: boolean
  limits: Record<string, number>      // { documents: 500, storage_mb: 10240 }
  needs_upgrade: boolean              // True if trial expired without paid plan
  trial_days_remaining: number | null
  current_period_end: string | null
  subscription_id: string | null
  cancel_at_period_end: boolean
}

/**
 * User permissions based on subscription and roles (returned by POST /auth/login)
 */
export interface UserPermissions {
  is_admin: boolean
  is_team_member: boolean
  can_upload_documents: boolean
  can_use_agents: boolean
  can_invite_members: boolean
  can_access_api: boolean
  can_export: boolean
}

/**
 * Response from POST /auth/login
 */
export interface LoginResponse {
  user: BackendUser
  subscription: SubscriptionInfo
  permissions: UserPermissions
}

export interface OnboardingStatus {
  needsOnboarding: boolean
  isNewUser: boolean
  hasCompletedSync: boolean
  loading: boolean
  error: string | null
}

export interface UserContextType {
  // Clerk user data
  clerkUser: any // TODO: Replace with proper Clerk user type
  isClerkLoaded: boolean
  isSignedIn: boolean

  // Backend user data
  backendUser: BackendUser | null
  userLoading: boolean
  userError: string | null

  // Subscription & Permissions (from POST /auth/login)
  subscription: SubscriptionInfo | null
  permissions: UserPermissions | null

  // Onboarding
  onboarding: OnboardingStatus

  // Actions
  markOnboardingComplete: (onboardingData?: any) => Promise<boolean>
  resetOnboarding: () => Promise<boolean>
  checkOnboardingStatus: () => Promise<void>
  refetchUser: () => Promise<void>
  handleLogout: () => Promise<void>

  // Subscription helpers
  hasValidTrial: () => boolean
  hasPaidSubscription: () => boolean
  needsPayment: () => boolean
}

export interface UserProviderProps {
  children: React.ReactNode
}

// Component Props Types
export interface AuthGuardProps {
  children: React.ReactNode
  fallback?: React.ReactNode
}

export interface SiteHeaderProps {
}

export interface AppSidebarProps {
  variant?: "sidebar" | "floating" | "inset"
  side?: "left" | "right"
  collapsible?: "offcanvas" | "icon" | "none"
  className?: string
}

export interface DigitalSignatureAssistantProps {
  agent: Agent
  onBack: () => void
}

// Upload Context Types
export interface UploadContextType {
  uploadDialogOpen: boolean
  setUploadDialogOpen: (open: boolean) => void
  openUploadDialog: () => void
  closeUploadDialog: () => void
  onUploadComplete?: (files: File[]) => void
  setOnUploadComplete: (callback?: (files: File[]) => void) => void
}

// Notifications Types
export interface Notification {
  id: string
  type: 'upload' | 'document' | 'user' | 'system' | 'success' | 'error' | 'info' | 'warning'
  title: string
  message: string
  timestamp: Date
  read: boolean
  action?: {
    label: string
    href: string
  }
  fileCount?: number
  autoHide?: boolean
}

export interface NotificationsContextType {
  notifications: Notification[]
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => void
  markAsRead: (id: string) => void
  markAllAsRead: () => void
  removeNotification: (id: string) => void
  clearAll: () => void
  unreadCount: number
}

// UI Component Props
export interface LoadingProps {
  className?: string
  size?: "sm" | "md" | "lg"
  text?: string
}

// Upload Types
export interface UploadNotification {
  id: string
  type: 'success' | 'error' | 'info'
  title: string
  message: string
  timestamp: Date
  fileCount?: number
  autoHide?: boolean
}

export interface UploadNotificationsProps {
  notifications: UploadNotification[]
  onDismiss: (id: string) => void
}

export interface UploadFile {
  file: File
  id: string
  progress: number
  status: 'pending' | 'uploading' | 'success' | 'error'
  error?: string
}

export interface UploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onUploadComplete?: (files: UploadFile[]) => void
}

// Onboarding Types
export interface OnboardingStep {
  id: string
  title: string
  description: string
  icon: React.ReactNode
  completed: boolean
  action?: () => Promise<void>
}

export interface UserOnboardingProps {
  onComplete?: () => void
}

export interface CompanyData {
  companyName: string
  cif: string
  address?: string
  phone?: string
  website?: string
  logo?: File | null
}

export interface OnboardingWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onComplete: () => void
}

// Agent Health Check Types
export interface ServiceStatus {
  name: string
  status: 'healthy' | 'unhealthy' | 'warning' | 'unknown'
  response_time?: number
  last_check?: string
  details?: Record<string, unknown>
  error?: string
}

// Document Preview Types
export interface DocumentPreviewResponse {
  type: 'office_preview' | 'text_preview' | 'pdf_preview' | 'image_preview' | 'text_fallback' | 'unsupported_fallback'
  conversion_method: 'gotenberg' | 'pil' | 'fallback' | 'none'
  pdf_available: boolean
  pdf_storage_path?: string
  pdf_local_path?: string
  thumbnail_path?: string
  thumbnails: string[]
  original_format: string
  original_dimensions?: [number, number]
  original_image_format?: string
  cached: boolean
  generated_at: number
  file_size: number
  text_preview?: string
  message?: string
  filename?: string
  supported_formats?: {
    office: string[]
    text: string[]
    already_pdf: string[]
    images: string[]
  }
}

export interface DocumentPreviewInfo {
  has_preview: boolean
  preview_info?: DocumentPreviewResponse
  message?: string
  error?: string
}

// ========================================
// Document ACL Types
// ========================================

/**
 * Types of grantees for document ACL
 */
export type GranteeType = 'user' | 'role' | 'everyone'

/**
 * Permission types for document ACL
 */
export type Permission = 'view' | 'edit' | 'delete' | 'share'

/**
 * ACL action types for audit log
 */
export type ACLAction = 'granted' | 'revoked' | 'modified' | 'expired'

/**
 * Source of ACL grant
 */
export type ACLSource = 'manual' | 'share_link' | 'inherited' | 'migration'

/**
 * Permission set for granting/displaying permissions
 */
export interface PermissionSet {
  can_view: boolean
  can_edit: boolean
  can_delete: boolean
  can_share: boolean
}

/**
 * Document ACL entry
 */
export interface DocumentACL {
  id: string
  document_id: string
  grantee_type: GranteeType
  grantee_id?: string
  can_view: boolean
  can_edit: boolean
  can_delete: boolean
  can_share: boolean
  granted_by: string
  granted_at: string
  expires_at?: string
  source: ACLSource
  created_at: string
  updated_at?: string
  // Resolved names (from API response)
  grantee_name?: string
  granter_name?: string
  is_expired: boolean
}

/**
 * List of ACLs for a document
 */
export interface DocumentACLListResponse {
  document_id: string
  document_title: string
  owner_id: string
  owner_name?: string
  acls: DocumentACL[]
  total: number
}

/**
 * Effective permissions for current user on a document
 */
export interface EffectivePermissions {
  can_view: boolean
  can_edit: boolean
  can_delete: boolean
  can_share: boolean
  is_owner: boolean
  is_admin: boolean
  from_user_acl: boolean
  from_role_acl: boolean
  from_everyone_acl: boolean
  applicable_acl_ids: string[]
}

/**
 * Request to grant permissions
 */
export interface GrantPermissionRequest {
  grantee_type: GranteeType
  grantee_id?: string
  permissions: PermissionSet
  expires_at?: string
  source?: ACLSource
}

/**
 * Request to revoke permissions
 */
export interface RevokePermissionRequest {
  grantee_type: GranteeType
  grantee_id?: string
}

/**
 * Check permission response
 */
export interface CheckPermissionResponse {
  document_id: string
  user_id: string
  permission: Permission
  allowed: boolean
  reason: string
}

/**
 * ACL Audit log entry
 */
export interface DocumentACLAudit {
  id: string
  document_id: string
  acl_id?: string
  action: ACLAction
  grantee_type: GranteeType
  grantee_id?: string
  permissions_before?: PermissionSet
  permissions_after?: PermissionSet
  performed_by: string
  source?: string
  ip_address?: string
  user_agent?: string
  created_at: string
  // Resolved names
  grantee_name?: string
  performer_name?: string
  document_title?: string
}

/**
 * Audit log list response
 */
export interface DocumentACLAuditListResponse {
  document_id?: string
  audits: DocumentACLAudit[]
  total: number
  page: number
  page_size: number
}

/**
 * Bulk ACL update request
 */
export interface BulkACLUpdateRequest {
  document_ids: string[]
  grant_permissions?: GrantPermissionRequest[]
  revoke_permissions?: RevokePermissionRequest[]
}

/**
 * Bulk ACL update response
 */
export interface BulkACLUpdateResponse {
  success_count: number
  failure_count: number
  failures: Array<{ document_id: string; error: string }>
}

/**
 * Document with ACL information (extended Document type)
 */
export interface DocumentWithACL extends Document {
  current_user_permissions?: EffectivePermissions
  visibility?: 'private' | 'shared' | 'public'
  acl_count?: number
}

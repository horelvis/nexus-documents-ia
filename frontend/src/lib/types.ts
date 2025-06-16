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
  tenant_id: string
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
  indexed: 'PENDING' | 'PROCESSING' | 'INDEXED' | 'INDEXING_ERROR'
  status?: 'uploading' | 'processing' | 'processed' | 'error' // Keep for backward compatibility
  summary?: string
  language?: string
  tenant_id: string
  created_by: string
  user_id?: string // Keep for backward compatibility
  created_at: string
  updated_at: string
  processed_at?: string
  gcs_path?: string
  storage_path?: string
  download_url?: string
  error_message?: string
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
  onboarding_completed: boolean
  tenant_id: string
  clerk_user_id?: string
  stripe_customer_id?: string
  created_at: string
  updated_at: string
  // Subscription info from Stripe (populated dynamically)
  subscription_plan?: string
  subscription_status?: string
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
  
  // Onboarding
  onboarding: OnboardingStatus
  
  // Actions
  syncUserWithBackend: () => Promise<void>
  markOnboardingComplete: (onboardingData?: any) => Promise<boolean>
  resetOnboarding: () => Promise<boolean>
  checkOnboardingStatus: () => Promise<void>
  refetchUser: () => Promise<void>
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
  tenantId?: string
}

export interface AppSidebarProps {
  tenantId?: string
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
  type: 'upload' | 'document' | 'user' | 'system' | 'success' | 'error' | 'info'
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
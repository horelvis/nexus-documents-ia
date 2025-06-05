import { z } from 'zod'

export const EditUserProfileSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  email: z.string().email('Invalid email address'),
})

export const UploadDocumentSchema = z.object({
  category: z.string().min(1, 'Category is required'),
  tags: z.string().optional(),
  description: z.string().optional(),
  files: z.array(z.any()).min(1, 'At least one file is required'),
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
  settings?: Record<string, any>
}

export interface Document {
  id: string
  filename: string
  original_filename: string
  title?: string
  description?: string
  file_size: number
  mime_type: string
  category?: string
  tags: string[]
  status: 'uploading' | 'processing' | 'processed' | 'error'
  summary?: string
  language?: string
  tenant_id: string
  user_id: string
  created_at: string
  updated_at: string
  processed_at?: string
  gcs_path?: string
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
  config: Record<string, any>
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
/**
 * NexusLM Notebook Service
 *
 * Service for managing NexusLM notebooks - an on-premise NotebookLM alternative.
 * Handles CRUD operations, source management, chat Q&A, and audio generation.
 */

import { apiClient, ApiResponse } from '@/lib/api-client'

// =====================================
// Types
// =====================================

export interface NotebookSettings {
  language: string
  default_voice_a?: string
  default_voice_b?: string
}

export interface Notebook {
  id: string
  tenant_id: string
  user_id: string
  title: string
  description?: string
  emoji: string
  settings: NotebookSettings
  source_count: number
  total_words: number
  chat_count: number
  audio_count: number
  is_archived: boolean
  last_activity_at: string
  created_at: string
  updated_at: string
}

export interface NotebookListResponse {
  notebooks: Notebook[]
  total: number
  page: number
  per_page: number
  total_pages: number
}

export interface NotebookSource {
  id: string
  notebook_id: string
  document_id?: string
  indexed_document_id?: string
  title: string
  source_type: string
  word_count: number
  is_processed: boolean
  processing_error?: string
  key_points?: { point: string; importance: number }[]
  summary?: string
  added_at: string
  processed_at?: string
  status: 'processing' | 'ready' | 'error'
}

export interface NotebookAudio {
  id: string
  notebook_id: string
  config: AudioConfig
  status: AudioStatus
  status_message?: string
  progress_percent: number
  script?: ScriptSegment[]
  audio_url?: string
  audio_format: string
  duration_ms?: number
  file_size_bytes?: number
  transcript?: TranscriptSegment[]
  error_message?: string
  generation_started_at?: string
  generation_completed_at?: string
  created_at: string
  updated_at: string
  duration_formatted?: string
}

export interface AudioConfig {
  tone: 'conversational' | 'formal' | 'educational'
  length: 'short' | 'standard' | 'long'
  language: string
  focus_topics?: string[]
  voice_a?: { id: string; name: string }
  voice_b?: { id: string; name: string }
}

export type AudioStatus =
  | 'pending'
  | 'generating_script'
  | 'generating_audio'
  | 'stitching'
  | 'completed'
  | 'failed'

export interface ScriptSegment {
  speaker: 'A' | 'B'
  text: string
  segment_id: number
}

export interface TranscriptSegment {
  speaker: 'A' | 'B'
  text: string
  start_ms: number
  end_ms: number
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  citations?: Citation[]
}

export interface Citation {
  source_id: string
  source_title: string
  text: string
  page?: number
}

export interface NotebookChat {
  id: string
  notebook_id: string
  user_id: string
  title?: string
  messages: ChatMessage[]
  message_count: number
  is_archived: boolean
  last_message_at: string
  created_at: string
  updated_at: string
}

export interface NotebookStats {
  total_notebooks: number
  total_sources: number
  total_words: number
  total_audios: number
  total_chats: number
  recent_activity: Notebook[]
}

// =====================================
// Notebook Service
// =====================================

export const notebookService = {
  /**
   * List all notebooks for the current user
   */
  async list(params?: {
    page?: number
    per_page?: number
    search?: string
    include_archived?: boolean
  }): Promise<ApiResponse<NotebookListResponse>> {
    const searchParams = new URLSearchParams()
    if (params?.page) searchParams.set('page', params.page.toString())
    if (params?.per_page) searchParams.set('per_page', params.per_page.toString())
    if (params?.search) searchParams.set('search', params.search)
    if (params?.include_archived) searchParams.set('include_archived', 'true')

    return apiClient.get<NotebookListResponse>(
      `/notebooks?${searchParams.toString()}`
    )
  },

  /**
   * Get notebook statistics
   */
  async getStats(): Promise<ApiResponse<NotebookStats>> {
    return apiClient.get<NotebookStats>('/notebooks/stats')
  },

  /**
   * Get a specific notebook with details
   */
  async get(notebookId: string): Promise<ApiResponse<Notebook & {
    sources: NotebookSource[]
    recent_audios: NotebookAudio[]
    recent_chats: NotebookChat[]
  }>> {
    return apiClient.get(`/notebooks/${notebookId}`)
  },

  /**
   * Create a new notebook
   */
  async create(data: {
    title: string
    description?: string
    emoji?: string
    settings?: NotebookSettings
  }): Promise<ApiResponse<Notebook>> {
    return apiClient.post<Notebook>('/notebooks', data)
  },

  /**
   * Update a notebook
   */
  async update(
    notebookId: string,
    data: Partial<{
      title: string
      description: string
      emoji: string
      settings: NotebookSettings
      is_archived: boolean
    }>
  ): Promise<ApiResponse<Notebook>> {
    return apiClient.patch<Notebook>(`/notebooks/${notebookId}`, data)
  },

  /**
   * Delete a notebook
   */
  async delete(notebookId: string): Promise<ApiResponse<{ message: string }>> {
    return apiClient.delete(`/notebooks/${notebookId}`)
  },

  // =====================================
  // Source Management
  // =====================================

  /**
   * List sources in a notebook
   */
  async listSources(notebookId: string): Promise<ApiResponse<NotebookSource[]>> {
    return apiClient.get<NotebookSource[]>(`/notebooks/${notebookId}/sources`)
  },

  /**
   * Add a source to a notebook
   */
  async addSource(
    notebookId: string,
    data: {
      document_id?: string
      indexed_document_id?: string
    }
  ): Promise<ApiResponse<NotebookSource>> {
    return apiClient.post<NotebookSource>(`/notebooks/${notebookId}/sources`, data)
  },

  /**
   * Remove a source from a notebook
   */
  async removeSource(
    notebookId: string,
    sourceId: string
  ): Promise<ApiResponse<{ message: string }>> {
    return apiClient.delete(`/notebooks/${notebookId}/sources/${sourceId}`)
  },

  // =====================================
  // Audio Generation
  // =====================================

  /**
   * Generate podcast audio for a notebook
   */
  async generateAudio(
    notebookId: string,
    config?: AudioConfig
  ): Promise<ApiResponse<NotebookAudio>> {
    return apiClient.post<NotebookAudio>(`/notebooks/${notebookId}/audio`, {
      config: config || {
        tone: 'conversational',
        length: 'standard',
        language: 'es-ES',
      },
    })
  },

  /**
   * List all audios for a notebook
   */
  async listAudios(notebookId: string): Promise<ApiResponse<NotebookAudio[]>> {
    return apiClient.get<NotebookAudio[]>(`/notebooks/${notebookId}/audio`)
  },

  /**
   * Get a specific audio
   */
  async getAudio(
    notebookId: string,
    audioId: string
  ): Promise<ApiResponse<NotebookAudio>> {
    return apiClient.get<NotebookAudio>(`/notebooks/${notebookId}/audio/${audioId}`)
  },

  /**
   * Get audio generation status
   */
  async getAudioStatus(
    notebookId: string,
    audioId: string
  ): Promise<ApiResponse<{
    id: string
    status: AudioStatus
    status_message?: string
    progress_percent: number
    error_message?: string
  }>> {
    return apiClient.get(`/notebooks/${notebookId}/audio/${audioId}/status`)
  },

  /**
   * Delete an audio
   */
  async deleteAudio(
    notebookId: string,
    audioId: string
  ): Promise<ApiResponse<{ message: string }>> {
    return apiClient.delete(`/notebooks/${notebookId}/audio/${audioId}`)
  },

  // =====================================
  // Chat Q&A
  // =====================================

  /**
   * Create a new chat in a notebook
   */
  async createChat(
    notebookId: string,
    data?: { title?: string }
  ): Promise<ApiResponse<NotebookChat>> {
    return apiClient.post<NotebookChat>(`/notebooks/${notebookId}/chats`, data || {})
  },

  /**
   * List all chats in a notebook
   */
  async listChats(
    notebookId: string,
    include_archived?: boolean
  ): Promise<ApiResponse<NotebookChat[]>> {
    const params = include_archived ? '?include_archived=true' : ''
    return apiClient.get<NotebookChat[]>(`/notebooks/${notebookId}/chats${params}`)
  },

  /**
   * Get a specific chat
   */
  async getChat(
    notebookId: string,
    chatId: string
  ): Promise<ApiResponse<NotebookChat>> {
    return apiClient.get<NotebookChat>(`/notebooks/${notebookId}/chats/${chatId}`)
  },

  /**
   * Send a message to a chat
   */
  async sendMessage(
    notebookId: string,
    chatId: string,
    content: string
  ): Promise<ApiResponse<{
    message: ChatMessage
    sources_used: number
  }>> {
    return apiClient.post(`/notebooks/${notebookId}/chats/${chatId}/messages`, {
      content,
    })
  },

  /**
   * Delete a chat
   */
  async deleteChat(
    notebookId: string,
    chatId: string
  ): Promise<ApiResponse<{ message: string }>> {
    return apiClient.delete(`/notebooks/${notebookId}/chats/${chatId}`)
  },
}

export default notebookService

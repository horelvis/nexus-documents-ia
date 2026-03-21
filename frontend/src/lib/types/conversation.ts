/**
 * Conversation Types for Emma Chat History
 *
 * Defines the structure for storing and managing chat conversations.
 */

import { EmmaMessage } from './emma'

export interface Conversation {
  id: string
  title: string
  messages: EmmaMessage[]
  createdAt: Date
  updatedAt: Date
  /** First message preview for sidebar display */
  preview?: string
  /** Whether this conversation is pinned */
  pinned?: boolean
  /** Tags for organization */
  tags?: string[]
  /** Number of messages in conversation */
  messageCount: number
}

export interface ConversationListItem {
  id: string
  title: string
  preview: string
  updatedAt: Date
  pinned: boolean
  messageCount: number
}

export interface ConversationState {
  conversations: ConversationListItem[]
  activeConversationId: string | null
  isLoading: boolean
  error: string | null
}

export type ConversationSortBy = 'updatedAt' | 'createdAt' | 'title'
export type ConversationSortOrder = 'asc' | 'desc'

export interface ConversationFilters {
  search?: string
  pinned?: boolean
  sortBy: ConversationSortBy
  sortOrder: ConversationSortOrder
}

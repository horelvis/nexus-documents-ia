/**
 * Conversation Storage Service
 *
 * Manages conversation persistence using localStorage with optional backend sync.
 * Provides CRUD operations for Emma chat history.
 */

import { Conversation, ConversationListItem, ConversationFilters } from '@/lib/types/conversation'
import { EmmaMessage } from '@/lib/types/emma'

const STORAGE_KEY = 'emma_conversations'
const MAX_CONVERSATIONS = 100 // Limit to prevent localStorage overflow

/**
 * Generate a unique conversation ID
 */
function generateId(): string {
  return `conv_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
}

/**
 * Generate a title from the first user message
 */
function generateTitle(messages: EmmaMessage[]): string {
  const firstUserMessage = messages.find((m) => m.type === 'user')
  if (firstUserMessage) {
    const content = firstUserMessage.content
    // Truncate to 50 chars and add ellipsis if needed
    return content.length > 50 ? content.slice(0, 50) + '...' : content
  }
  return 'Nueva conversación'
}

/**
 * Generate a preview from the last assistant message
 */
function generatePreview(messages: EmmaMessage[]): string {
  const lastAssistantMessage = [...messages]
    .reverse()
    .find((m) => m.type === 'result' || m.type === 'text')
  if (lastAssistantMessage) {
    const content = lastAssistantMessage.content
    return content.length > 80 ? content.slice(0, 80) + '...' : content
  }
  return ''
}

/**
 * Get all conversations from localStorage
 */
function getAllConversations(): Conversation[] {
  if (typeof window === 'undefined') return []

  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return []

    const parsed = JSON.parse(stored)
    // Convert date strings back to Date objects
    return parsed.map((conv: any) => ({
      ...conv,
      createdAt: new Date(conv.createdAt),
      updatedAt: new Date(conv.updatedAt),
      messages: conv.messages.map((msg: any) => ({
        ...msg,
        timestamp: new Date(msg.timestamp),
      })),
    }))
  } catch (error) {
    console.error('[ConversationService] Error reading conversations:', error)
    return []
  }
}

/**
 * Save all conversations to localStorage
 */
function saveAllConversations(conversations: Conversation[]): void {
  if (typeof window === 'undefined') return

  try {
    // Limit number of conversations
    const limitedConversations = conversations.slice(0, MAX_CONVERSATIONS)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(limitedConversations))
  } catch (error) {
    console.error('[ConversationService] Error saving conversations:', error)
    // If localStorage is full, try removing oldest conversations
    if (error instanceof DOMException && error.name === 'QuotaExceededError') {
      const reduced = conversations.slice(0, Math.floor(conversations.length / 2))
      localStorage.setItem(STORAGE_KEY, JSON.stringify(reduced))
    }
  }
}

/**
 * Conversation Service - CRUD operations for chat history
 */
export const conversationService = {
  /**
   * Get list of conversations for sidebar display
   */
  getList(filters?: ConversationFilters): ConversationListItem[] {
    let conversations = getAllConversations()

    // Apply search filter
    if (filters?.search) {
      const searchLower = filters.search.toLowerCase()
      conversations = conversations.filter(
        (c) =>
          c.title.toLowerCase().includes(searchLower) ||
          c.preview?.toLowerCase().includes(searchLower)
      )
    }

    // Apply pinned filter
    if (filters?.pinned !== undefined) {
      conversations = conversations.filter((c) => c.pinned === filters.pinned)
    }

    // Sort
    const sortBy = filters?.sortBy || 'updatedAt'
    const sortOrder = filters?.sortOrder || 'desc'
    conversations.sort((a, b) => {
      // Pinned items always first
      if (a.pinned && !b.pinned) return -1
      if (!a.pinned && b.pinned) return 1

      let comparison = 0
      if (sortBy === 'updatedAt') {
        comparison = new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      } else if (sortBy === 'createdAt') {
        comparison = new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
      } else if (sortBy === 'title') {
        comparison = a.title.localeCompare(b.title)
      }

      return sortOrder === 'desc' ? comparison : -comparison
    })

    // Map to list items
    return conversations.map((c) => ({
      id: c.id,
      title: c.title,
      preview: c.preview || '',
      updatedAt: c.updatedAt,
      pinned: c.pinned || false,
      messageCount: c.messageCount,
    }))
  },

  /**
   * Get a single conversation by ID
   */
  get(id: string): Conversation | null {
    const conversations = getAllConversations()
    return conversations.find((c) => c.id === id) || null
  },

  /**
   * Create a new conversation
   */
  create(messages: EmmaMessage[] = []): Conversation {
    const now = new Date()
    const conversation: Conversation = {
      id: generateId(),
      title: generateTitle(messages) || 'Nueva conversación',
      messages,
      createdAt: now,
      updatedAt: now,
      preview: generatePreview(messages),
      pinned: false,
      tags: [],
      messageCount: messages.length,
    }

    const conversations = getAllConversations()
    conversations.unshift(conversation) // Add to beginning
    saveAllConversations(conversations)

    return conversation
  },

  /**
   * Update an existing conversation
   */
  update(id: string, updates: Partial<Omit<Conversation, 'id' | 'createdAt'>>): Conversation | null {
    const conversations = getAllConversations()
    const index = conversations.findIndex((c) => c.id === id)

    if (index === -1) return null

    const updated: Conversation = {
      ...conversations[index],
      ...updates,
      updatedAt: new Date(),
      // Recalculate derived fields if messages changed
      ...(updates.messages && {
        title: updates.title || generateTitle(updates.messages),
        preview: generatePreview(updates.messages),
        messageCount: updates.messages.length,
      }),
    }

    conversations[index] = updated
    saveAllConversations(conversations)

    return updated
  },

  /**
   * Add messages to a conversation
   */
  addMessages(id: string, newMessages: EmmaMessage[]): Conversation | null {
    const conversation = this.get(id)
    if (!conversation) return null

    const updatedMessages = [...conversation.messages, ...newMessages]
    return this.update(id, { messages: updatedMessages })
  },

  /**
   * Update the last message in a conversation (for streaming updates)
   */
  updateLastMessage(id: string, updatedMessage: EmmaMessage): Conversation | null {
    const conversation = this.get(id)
    if (!conversation || conversation.messages.length === 0) return null

    const messages = [...conversation.messages]
    messages[messages.length - 1] = updatedMessage

    return this.update(id, { messages })
  },

  /**
   * Delete a conversation
   */
  delete(id: string): boolean {
    const conversations = getAllConversations()
    const filtered = conversations.filter((c) => c.id !== id)

    if (filtered.length === conversations.length) return false

    saveAllConversations(filtered)
    return true
  },

  /**
   * Toggle pin status
   */
  togglePin(id: string): Conversation | null {
    const conversation = this.get(id)
    if (!conversation) return null

    return this.update(id, { pinned: !conversation.pinned })
  },

  /**
   * Rename a conversation
   */
  rename(id: string, newTitle: string): Conversation | null {
    return this.update(id, { title: newTitle })
  },

  /**
   * Clear all conversations
   */
  clearAll(): void {
    if (typeof window === 'undefined') return
    localStorage.removeItem(STORAGE_KEY)
  },

  /**
   * Get conversation count
   */
  getCount(): number {
    return getAllConversations().length
  },

  /**
   * Export conversations as JSON
   */
  export(): string {
    const conversations = getAllConversations()
    return JSON.stringify(conversations, null, 2)
  },

  /**
   * Import conversations from JSON
   */
  import(json: string): number {
    try {
      const imported = JSON.parse(json)
      if (!Array.isArray(imported)) throw new Error('Invalid format')

      const existing = getAllConversations()
      const existingIds = new Set(existing.map((c) => c.id))

      // Only import conversations that don't already exist
      const newConversations = imported.filter((c: any) => !existingIds.has(c.id))
      const merged = [...existing, ...newConversations]

      saveAllConversations(merged)
      return newConversations.length
    } catch (error) {
      console.error('[ConversationService] Import error:', error)
      return 0
    }
  },
}

export default conversationService

import { useMemo } from 'react'
import { useApiClient } from '../api-client'

/**
 * Folder structure as returned by the backend
 */
export interface FolderInfo {
  path: string
  name: string
  document_count: number
  children: FolderInfo[]
}

/**
 * Backend folder tree response structure
 */
export interface BackendFolderTreeResponse {
  root: FolderInfo
}

/**
 * Folder tree response (normalized for frontend use)
 */
export interface FolderTreeResponse {
  folders: FolderInfo[]
  total_folders: number
  total_documents: number
}

/**
 * Move document request
 */
export interface MoveDocumentRequest {
  target_folder: string
}

/**
 * Move document response
 */
export interface MoveDocumentResponse {
  document_id: string
  old_folder: string
  new_folder: string
  message: string
}

/**
 * Create folder request (creates a folder marker)
 */
export interface CreateFolderRequest {
  folder_path: string
}

/**
 * Service for folder management operations.
 *
 * Provides methods to:
 * - Get folder tree structure
 * - Move documents between folders
 * - Create empty folders
 */
export class FolderService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  /**
   * Get folder tree for the current tenant
   * Normalizes backend response to frontend format
   */
  async getFolderTree(): Promise<{ data?: FolderTreeResponse; error?: string }> {
    const response = await this.apiClient.get<BackendFolderTreeResponse>('/folders/tree')

    if (response.error || !response.data) {
      return { error: response.error || 'Failed to load folders' }
    }

    // Flatten the tree to get all folders
    const flattenFolders = (node: FolderInfo): FolderInfo[] => {
      const result: FolderInfo[] = []
      if (node.path) {  // Skip root node itself
        result.push(node)
      }
      for (const child of node.children || []) {
        result.push(...flattenFolders(child))
      }
      return result
    }

    // Count total documents recursively
    const countDocuments = (node: FolderInfo): number => {
      let count = node.document_count || 0
      for (const child of node.children || []) {
        count += countDocuments(child)
      }
      return count
    }

    const root = response.data.root
    const folders = root.children || []  // Get direct children of root
    const allFolders = flattenFolders(root)

    return {
      data: {
        folders: folders,
        total_folders: allFolders.length,
        total_documents: countDocuments(root)
      }
    }
  }

  /**
   * Move a document to a different folder
   *
   * @param documentId - Document to move
   * @param targetFolder - Destination folder path (e.g., '/Contracts/2024')
   */
  async moveDocument(documentId: string, targetFolder: string) {
    return this.apiClient.put<MoveDocumentResponse>(
      `/folders/${documentId}/move`,
      { new_folder_path: targetFolder }  // Backend expects new_folder_path
    )
  }

  /**
   * Move multiple documents to a folder
   *
   * @param documentIds - Documents to move
   * @param targetFolder - Destination folder path
   */
  async moveDocuments(documentIds: string[], targetFolder: string) {
    const results = await Promise.all(
      documentIds.map(id => this.moveDocument(id, targetFolder))
    )
    return {
      data: results.map(r => r.data).filter(Boolean),
      errors: results.filter(r => r.error).map(r => r.error)
    }
  }

  /**
   * Create an empty folder (folder marker)
   *
   * @param folderPath - Full folder path (e.g., '/Contracts/2024')
   */
  async createFolder(folderPath: string) {
    return this.apiClient.post<{ success: boolean; message: string; path: string }>(
      '/folders',
      { path: folderPath }  // Backend expects 'path' not 'folder_path'
    )
  }

  /**
   * Delete an empty folder marker
   *
   * @param folderPath - Folder path to delete
   */
  async deleteFolder(folderPath: string) {
    const encodedPath = encodeURIComponent(folderPath)
    return this.apiClient.delete<{ message: string }>(`/folders/${encodedPath}`)
  }
}

/**
 * Hook to use the Folder service.
 * Provides memoized instance that updates when apiClient changes.
 */
export function useFolderService() {
  const apiClient = useApiClient()
  return useMemo(() => new FolderService(apiClient), [apiClient])
}

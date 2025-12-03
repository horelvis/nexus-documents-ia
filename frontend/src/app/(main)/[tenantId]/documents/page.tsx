"use client"

import { useState, useEffect, useCallback, useRef, useMemo } from "react"
import { useParams, useRouter } from "next/navigation"
import { DocumentList } from "@/components/documents/document-list"
import {
  IconPlus,
  IconSearch,
  IconFilter,
  IconFile,
  IconFileText,
  IconFileTypeDoc,
  IconFileTypePdf,
  IconClock,
  IconEye,
  IconDownload,
  IconTrash,
  IconEdit,
  IconLoader2,
  IconChevronLeft,
  IconChevronRight,
  IconLayoutGrid,
  IconLayoutList,
  IconShare2,
  IconSignature,
  IconDotsVertical,
  IconBrain,
  IconRefresh,
  IconAlertTriangle,
  IconX
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { RichTextInput } from "@/components/ui/rich-text-input"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator
} from "@/components/ui/dropdown-menu"
import { useUpload } from "@/contexts/upload-context"
import { useDocumentEvent, useDocumentEvents, DocumentsUpdatedPayload } from "@/contexts/document-events-context"
import { useNotifications } from "@/contexts/app-state-context"
import { useUserContext } from "@/contexts/user-context"
import { useDocumentService } from "@/lib/services/document.service"
import { useSearchService } from "@/lib/services/search.service"
import { useDocumentInsightsService, type RecentDocument } from "@/lib/services/document-insights.service"
import { useApiClient } from "@/lib/api-client"
import { Document as ApiDocument } from "@/lib/types"
import type { Entity as SearchEntity } from "@/lib/services/entity.service"
import {
  EditDocumentDialog,
  DeleteDocumentDialog,
  DocumentsDataTable
} from "@/components/documents"
import { ShareDocumentDialog } from "@/components/documents/share-document-dialog"
import { getFileIcon, formatFileSize } from "@/lib/document-utils"
import { useTranslation } from "@/lib/i18n/hooks"
import { createEntityTag } from "@/components/ui/entity-renderer"

type DocumentFilterOption = 'all' | 'recent';

const isDocumentFilterOption = (value: unknown): value is DocumentFilterOption =>
  ['all', 'recent'].includes(value as string)

const mapRecentDocumentToApiDocument = (doc: RecentDocument): ApiDocument => ({
  id: doc.id,
  filename: doc.filename,
  original_filename: doc.filename,
  title: doc.title || doc.filename || 'Untitled',
  description: doc.description || '',
  file_size: doc.file_size || 0,
  file_type: doc.file_type || 'unknown',
  mime_type: doc.mime_type || 'application/octet-stream',
  category: doc.category || '',
  tags: doc.tags || [],
  indexed: doc.indexed ? 'INDEXED' : 'PENDING',
  status: 'processed',
  tenant_id: doc.tenant_id,
  created_by: (doc as any).created_by || {},
  user_id: (doc as any).user_id,
  created_at: doc.created_at,
  updated_at: doc.updated_at || doc.created_at,
  processed_at: doc.updated_at || doc.created_at,
})

export default function DocumentsPage() {
  const params = useParams()
  const router = useRouter()
  const tenantId = params.tenantId as string
  const { t } = useTranslation()
  const { backendUser } = useUserContext()
  const apiClient = useApiClient()

  const DOCUMENT_FILTERS = useMemo(() => [
    { value: 'all' as const, label: t('documentsPage.filters.all') },
    { value: 'recent' as const, label: t('documentsPage.filters.recent') },
  ], [t]);

  const [documents, setDocuments] = useState<ApiDocument[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [convertingDocumentId, setConvertingDocumentId] = useState<string | null>(null)

  const isTenantAdmin = useMemo(() => {
    if (!backendUser) return false
    if (backendUser.is_superuser) return true
    if (backendUser.is_team_member === false) return true
    try {
      const roles = (backendUser as any)?.roles
      if (Array.isArray(roles)) {
        return roles.some(
          (role: any) => typeof role?.name === 'string' && role.name.toLowerCase() === 'admin'
        )
      }
    } catch {
      return false
    }
    return false
  }, [backendUser])
  // Pagination state
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalDocuments, setTotalDocuments] = useState(0)
  const [perPage] = useState(50)

  // Load user preferences from localStorage
  const getStoredPreference = (key: string, defaultValue: any) => {
    if (typeof window === 'undefined') return defaultValue
    try {
      const stored = localStorage.getItem(`documents_${tenantId}_${key}`)
      return stored ? JSON.parse(stored) : defaultValue
    } catch {
      return defaultValue
    }
  }

  // Store user preference
  const storePreference = useCallback((key: string, value: any) => {
    if (typeof window === 'undefined') return
    try {
      localStorage.setItem(`documents_${tenantId}_${key}`, JSON.stringify(value))
    } catch {
      // Ignore localStorage errors
    }
  }, [tenantId])

  // Initialize states with stored preferences
  const [selectedFilter, setSelectedFilter] = useState<DocumentFilterOption>(() => {
    const storedFilter = getStoredPreference('filter', 'all')
    return isDocumentFilterOption(storedFilter) ? storedFilter : 'all'
  })
  const [viewMode, setViewMode] = useState<'grid' | 'table'>(() =>
    getStoredPreference('viewMode', 'grid')
  )
  const selectedFilterLabel = useMemo(() => {
    return DOCUMENT_FILTERS.find(option => option.value === selectedFilter)?.label ?? t('documentsPage.filters.all')
  }, [selectedFilter, DOCUMENT_FILTERS, t])
  // Siempre usar búsqueda semántica por contenido
  const useDeepSearch = true

  // Local state for search input
  const [localSearchQuery, setLocalSearchQuery] = useState(searchQuery)
  const [selectedEntities, setSelectedEntities] = useState<SearchEntity[]>([])

  const handleFilterChange = (value: DocumentFilterOption) => {
    setSelectedFilter(value)
    storePreference('filter', value)
  }

  const handleSearchConfirm = () => {
    const mentionQuery = selectedEntities
      .map(entity => createEntityTag({
        type: entity.type || 'entity',
        id: entity.id,
        name: entity.name
      }))
      .join(' ')

    const combinedQuery = [localSearchQuery.trim(), mentionQuery]
      .filter(Boolean)
      .join(' ')
      .trim()

    setSearchQuery(combinedQuery)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearchConfirm()
    }
  }

  // Dialog states
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [shareDialogOpen, setShareDialogOpen] = useState(false)
  const [selectedDocument, setSelectedDocument] = useState<ApiDocument | null>(null)

  const { openUploadDialog, closeUploadDialog } = useUpload()
  const { emitDocumentEvent } = useDocumentEvents()
  const { addNotification } = useNotifications()
  const documentService = useDocumentService()
  const searchService = useSearchService()
  const documentInsightsService = useDocumentInsightsService()
  const documentServiceRef = useRef(documentService)
  const searchServiceRef = useRef(searchService)
  const documentInsightsServiceRef = useRef(documentInsightsService)

  useEffect(() => {
    documentServiceRef.current = documentService
  }, [documentService])

  useEffect(() => {
    searchServiceRef.current = searchService
  }, [searchService])

  useEffect(() => {
    documentInsightsServiceRef.current = documentInsightsService
  }, [documentInsightsService])




  // Load documents from API - simple pattern
  const loadDocuments = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      if (selectedFilter === 'recent') {
        const limit = viewMode === 'table' ? 100 : perPage
        const insightsResponse = await documentInsightsServiceRef.current.getRecentlyViewedDocuments(limit, true)

        if (insightsResponse?.error) {
          setError(insightsResponse.error)
          setDocuments([])
          setTotalDocuments(0)
          setTotalPages(1)
          return
        }

        const rawRecentDocuments = insightsResponse?.data || []
        const normalizedQuery = searchQuery.trim().toLowerCase()
        const filteredRecentDocuments = normalizedQuery
          ? rawRecentDocuments.filter(doc => {
            const haystack = [
              doc.title || '',
              doc.filename || '',
              doc.description || '',
              (doc.tags || []).join(' ')
            ].join(' ').toLowerCase()
            return haystack.includes(normalizedQuery)
          })
          : rawRecentDocuments

        const mappedRecentDocuments = filteredRecentDocuments.map(mapRecentDocumentToApiDocument)
        setDocuments(mappedRecentDocuments)
        setTotalDocuments(mappedRecentDocuments.length)
        setTotalPages(1)
        return
      }

      let response;
      const statusFilter = selectedFilter !== 'all' && selectedFilter !== 'recent' ? selectedFilter : undefined
      const trimmedQuery = searchQuery.trim()
      const shouldSearch = useDeepSearch && trimmedQuery.length >= 3

      // Usar búsqueda semántica por contenido cuando hay un query de búsqueda válido (>= 3 chars)
      if (shouldSearch) {
        // Use semantic search for content
        const searchResults = await searchServiceRef.current.searchDocuments({
          query: trimmedQuery,
          limit: viewMode === 'table' ? 100 : perPage
        })

        if (searchResults.error) {
          console.warn('Semantic search failed, falling back to regular search:', searchResults.error)
          // Fallback to regular document search instead of showing error
          response = await documentServiceRef.current.getDocuments({
            search: trimmedQuery,
            status: statusFilter,
            per_page: viewMode === 'table' ? 100 : perPage,
            page: viewMode === 'table' ? 1 : currentPage
          })
        } else {

          const documents = searchResults.data?.map(result => {
            const doc = result.document || result || {}
            const docAny = doc as any
            // Map matches from search result (sibling to document) or use existing search_matches
            const matches = result.matches || docAny.search_matches || docAny.matches || []

            return {
              ...doc,
              id: doc.id || '',
              title: doc.title || doc.filename || 'Untitled',
              filename: doc.filename || 'unknown',
              status: 'active' as const,
              created_by: docAny.created_by || {},
              tenant_id: tenantId,
              indexed: doc.indexed || 'INDEXED',
              file_hash: docAny.file_hash || '',
              version: docAny.version || 1,
              category: docAny.category || '',
              document_metadata: docAny.document_metadata || {},
              content: docAny.content || '',
              extracted_entities: docAny.extracted_entities || null,
              ocr_status: docAny.ocr_status || null,
              ocr_completed_at: docAny.ocr_completed_at || null,
              signature_fields: docAny.signature_fields || null,
              file_type: doc.file_type || 'unknown',
              mime_type: doc.mime_type || 'application/octet-stream',
              file_size: doc.file_size || 0,
              created_at: doc.created_at || new Date().toISOString(),
              updated_at: doc.updated_at || new Date().toISOString(),
              tags: doc.tags || [],
              description: doc.description || '',
              search_matches: matches
            }
          }) || []
          response = {
            data: {
              items: documents,
              total: documents.length,
              page: 1,
              per_page: documents.length,
              pages: 1
            }
          }
        }
      } else {
        // Use regular document listing (or fallback if query too short)
        // Only pass search param if it meets the length requirement (logic for SQL fallback)
        // If < 3 chars, effectiveSearch is undefined, so we load all docs.
        const effectiveSearch = trimmedQuery.length >= 3 ? trimmedQuery : undefined
        const itemsPerPage = viewMode === 'table' ? 100 : perPage

        response = await documentServiceRef.current.getDocuments({
          search: effectiveSearch,
          status: statusFilter,
          per_page: itemsPerPage,
          page: viewMode === 'table' ? 1 : currentPage
        })
      }

      if (response?.error) {
        setError(response.error)
      } else if (response?.data) {
        // Ensure all documents have required fields to prevent undefined errors
        const safeDocuments = (response.data.items || []).map(doc => ({
          ...doc,
          indexed: doc.indexed || 'INDEXED',
          status: doc.status || 'active',
          created_by: doc.created_by || {},
          tags: doc.tags || [],
          file_type: doc.file_type || 'unknown',
          mime_type: doc.mime_type || 'application/octet-stream',
          file_size: doc.file_size || 0
        }))

        setDocuments(safeDocuments)
        setTotalPages(response.data.pages || 1)
        setTotalDocuments(response.data.total || 0)
      } else {
        setError('Invalid response from server')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load documents')
    } finally {
      setIsLoading(false)
    }
  }, [searchQuery, useDeepSearch, viewMode, perPage, selectedFilter, currentPage])

  // Reload when dependencies change
  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  // Reset to page 1 when filter or search query changes
  useEffect(() => {
    setCurrentPage(1)
  }, [selectedFilter, searchQuery, viewMode])


  // Documents are already filtered server-side
  const filteredDocuments = documents || []

  const isOdtDocument = useCallback((document: ApiDocument) => {
    const fileType = (document.file_type || '').toLowerCase()
    const mimeType = (document.mime_type || '').toLowerCase()
    return fileType === 'odt' || mimeType.includes('opendocument')
  }, [])

  const handleDocumentsUpdated = useCallback((payload?: DocumentsUpdatedPayload) => {
    if (payload?.tenantId && payload.tenantId !== tenantId) {
      return
    }

    if (payload?.source === 'upload') {
      const uploadedFiles = payload.files || []
      const successfulUploads = uploadedFiles.filter(file => file.status === 'success')
      if (!successfulUploads.length) {
        return
      }

      const message = successfulUploads.length > 1
        ? t('documentsPage.notifications.uploadComplete.message_other', { count: successfulUploads.length })
        : t('documentsPage.notifications.uploadComplete.message_one', { count: 1 });

      addNotification({
        type: 'upload',
        title: t('documentsPage.notifications.uploadComplete.title'),
        message: message,
        fileCount: successfulUploads.length,
        action: {
          label: t('documentsPage.notifications.viewDocumentsAction'),
          href: `/${tenantId}/documents`
        }
      })

      setSearchQuery('')
      setSelectedFilter('all')
      storePreference('filter', 'all')
      setCurrentPage(1)
      loadDocuments()
      return
    }

    loadDocuments()
  }, [addNotification, loadDocuments, tenantId, t, storePreference])

  useDocumentEvent("documents:updated", handleDocumentsUpdated)

  // Document operations
  const handleViewDocument = (document: ApiDocument) => {
    router.push(`/${tenantId}/documents/${document.id}/preview`)
  }

  const handleEditDocument = (document: ApiDocument) => {
    setSelectedDocument(document)
    setEditDialogOpen(true)
  }

  const handleDeleteDocument = (document: ApiDocument) => {
    setSelectedDocument(document)
    setDeleteDialogOpen(true)
  }

  const handleShareDocument = (document: ApiDocument) => {
    setSelectedDocument(document)
    setShareDialogOpen(true)
  }

  const openTemplateInGoogleDocs = useCallback(
    async (templateId: string, templateName: string) => {
      try {
        const response = await apiClient.post(`/engine-templates/${templateId}/edit-sessions`, {
          reason: 'Template created from document conversion'
        })

        if (response.error || !response.data) {
          throw new Error(response.error || 'Failed to start Google Docs session')
        }

        const editUrl = (response.data as any).google_doc_edit_url
        if (!editUrl) {
          throw new Error('Google Docs URL not available yet')
        }

        const editorWindow = window.open(
          editUrl,
          'googledocs',
          'width=1200,height=800,scrollbars=yes,resizable=yes'
        )

        if (editorWindow) {
          addNotification({
            type: 'success',
            title: 'Google Docs',
            message: `Abriendo Google Docs para "${templateName}".`
          })
        } else {
          addNotification({
            type: 'warning',
            title: 'Permite ventanas emergentes',
            message: 'Activa los pop-ups para abrir Google Docs.'
          })
        }
      } catch (error) {
        addNotification({
          type: 'error',
          title: 'Google Docs no disponible',
          message: error instanceof Error ? error.message : 'No pudimos abrir Google Docs.'
        })
      }
    },
    [apiClient, addNotification]
  )

  const handleConvertToTemplate = useCallback(async (document: ApiDocument) => {
    if (!isTenantAdmin) return
    if (!isOdtDocument(document)) {
      addNotification({
        type: 'error',
        title: t('documentsPage.notifications.convertToTemplate.unsupported.title'),
        message: t('documentsPage.notifications.convertToTemplate.unsupported.message')
      })
      return
    }

    setConvertingDocumentId(document.id)
    try {
      const response = await documentService.convertDocumentToTemplate(document.id, {
        name: document.title || document.filename,
        description: document.description,
        category: document.category,
        tags: document.tags
      })

      if (response.error || !response.data) {
        throw new Error(response.error || 'No se pudo crear la plantilla')
      }

      const template = response.data as any
      if (!template?.id) {
        throw new Error('Invalid template response')
      }
      addNotification({
        type: 'success',
        title: t('documentsPage.notifications.convertToTemplate.success.title'),
        message: t('documentsPage.notifications.convertToTemplate.success.message', { templateName: template.name })
      })

      try {
        await openTemplateInGoogleDocs(template.id, template.name || document.title || document.filename)
      } catch (docError) {
        console.warn('Failed to open Google Docs:', docError)
        addNotification({
          type: 'warning',
          title: 'Edición no disponible',
          message: 'La plantilla se creó, pero no pudimos abrir Google Docs. Asegúrate de conectar tu cuenta de Google Drive en Configuración.'
        })
      }
    } catch (error) {
      addNotification({
        type: 'error',
        title: t('documentsPage.notifications.convertToTemplate.error.title'),
        message: error instanceof Error ? error.message : t('documentsPage.notifications.convertToTemplate.error.message')
      })
    } finally {
      setConvertingDocumentId(null)
    }
  }, [isTenantAdmin, documentService, addNotification, openTemplateInGoogleDocs, isOdtDocument, t])

  const handleRequestSignature = (document: ApiDocument) => {
    router.push(`/${tenantId}/documents/${document.id}/signature-request`)
  }

  const handleFullPagePreview = (document: ApiDocument) => {
    router.push(`/${tenantId}/documents/${document.id}/preview`)
  }

  const handleAskEmma = (document: ApiDocument) => {
    // Navigate to chat with document context
    const documentName = encodeURIComponent(document.title || document.filename)
    router.push(`/${tenantId}/chat?documentId=${document.id}&documentName=${documentName}`)
  }

  const handleDownloadDocument = async (document: ApiDocument) => {
    try {
      addNotification({
        type: 'info',
        title: t('documentsPage.notifications.downloading.title'),
        message: t('documentsPage.notifications.downloading.message', { filename: document.filename })
      })

      const result = await documentService.downloadDocument(document.id)

      if ('error' in result) {
        addNotification({
          type: 'error',
          title: t('documentsPage.notifications.downloadFailed.title'),
          message: t('documentsPage.notifications.downloadFailed.message', { error: result.error })
        })
        return
      }

      if (!result.blob || !(result.blob instanceof Blob)) {
        addNotification({
          type: 'error',
          title: t('documentsPage.notifications.invalidFile.title'),
          message: t('documentsPage.notifications.invalidFile.message')
        })
        return
      }

      const url = URL.createObjectURL(result.blob)
      const a = window.document.createElement('a')
      a.href = url
      a.download = result.filename || document.filename || 'document'
      a.style.display = 'none'
      window.document.body.appendChild(a)
      a.click()

      setTimeout(() => {
        window.document.body.removeChild(a)
        URL.revokeObjectURL(url)
      }, 100)

      addNotification({
        type: 'success',
        title: t('documentsPage.notifications.downloadComplete.title'),
        message: t('documentsPage.notifications.downloadComplete.message', { filename: document.filename })
      })
    } catch (error) {
      console.error('Download exception:', error)
      addNotification({
        type: 'error',
        title: t('documentsPage.notifications.downloadFailed.title'),
        message: t('documentsPage.notifications.downloadFailed.message', { error: error instanceof Error ? error.message : 'Unknown error' })
      })
    }
  }

  const handleSaveDocument = async (id: string, updates: Partial<Pick<ApiDocument, 'title' | 'description' | 'tags' | 'category'>>) => {
    try {
      const response = await documentService.updateDocument(id, updates)

      if (response.error) {
        addNotification({
          type: 'error',
          title: t('documentsPage.notifications.updateFailed.title'),
          message: t('documentsPage.notifications.updateFailed.message', { error: response.error })
        })
        return
      }

      setDocuments(prev => prev.map(doc =>
        doc.id === id ? { ...doc, ...updates } : doc
      ))

      addNotification({
        type: 'success',
        title: t('documentsPage.notifications.updateSuccess.title'),
        message: t('documentsPage.notifications.updateSuccess.message')
      })
    } catch (error) {
      addNotification({
        type: 'error',
        title: t('documentsPage.notifications.updateFailed.title'),
        message: t('documentsPage.notifications.updateFailed.message', { error: error instanceof Error ? error.message : 'Unknown error' })
      })
      throw error
    }
  }

  const handleConfirmDelete = async (id: string) => {
    try {
      const response = await documentService.deleteDocument(id)

      if (response.error) {
        addNotification({
          type: 'error',
          title: t('documentsPage.notifications.deleteFailed.title'),
          message: t('documentsPage.notifications.deleteFailed.message', { error: response.error })
        })
        return
      }

      setDocuments(prev => prev.filter(doc => doc.id !== id))

      addNotification({
        type: 'success',
        title: t('documentsPage.notifications.deleteSuccess.title'),
        message: t('documentsPage.notifications.deleteSuccess.message')
      })

      emitDocumentEvent("documents:updated", {
        tenantId,
        source: "delete"
      })
    } catch (error) {
      addNotification({
        type: 'error',
        title: t('documentsPage.notifications.deleteFailed.title'),
        message: t('documentsPage.notifications.deleteFailed.message', { error: error instanceof Error ? error.message : 'Unknown error' })
      })
      throw error
    }
  }

  return (
    <div className="flex flex-col gap-4 p-6 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
          <div>
            <h1 className="text-3xl font-bold mb-2">{t('documentsPage.title')}</h1>
            <p className="text-muted-foreground">
              {t('documentsPage.subtitle')}
            </p>
          </div>
          <Button onClick={openUploadDialog}>
            <IconPlus className="mr-2 h-4 w-4" />
            {t('documentsPage.uploadButton')}
          </Button>
        </div>


        {/* Main content */}
        <div className="mb-6">
          {/* Search and Filter */}
          <Card className="mb-6">
            <CardContent className="p-6">
              <div className="flex flex-col gap-4">
                {/* Search Bar Row */}
                <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
                  <div className="flex-1 relative">
                    <IconSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4 z-10" />
                    <RichTextInput
                      placeholder={t('documentsPage.searchPlaceholder')}
                      value={localSearchQuery}
                      onChange={setLocalSearchQuery}
                      onKeyDown={handleKeyDown}
                      className="pl-10 border bg-background shadow-sm"
                      documentId="general"
                      autoInsertEntityTag={false}
                      onEntitySelect={(entity) => {
                        handleEntitySelectForSearch(entity)
                      }}
                    />
                    {selectedEntities.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {selectedEntities.map(entity => (
                          <Badge key={entity.id} variant="secondary" className="flex items-center gap-1">
                            <span>{entity.name}</span>
                            <button
                              type="button"
                              className="hover:text-destructive"
                              onClick={() => handleRemoveSearchEntity(entity.id)}
                            >
                              <IconX className="h-3 w-3" />
                            </button>
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <Button onClick={handleSearchConfirm} variant="outline" className="flex-shrink-0">
                      {t('documentsPage.searchButton')}
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="outline">
                          <IconFilter className="mr-2 h-4 w-4" />
                          {t('documentsPage.filterButton', { filter: selectedFilterLabel })}
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        {DOCUMENT_FILTERS.map(option => (
                          <DropdownMenuItem
                            key={option.value}
                            onClick={() => handleFilterChange(option.value)}
                          >
                            {option.label}
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>


                    {/* View Toggle */}
                    <div className="flex items-center rounded-md border">
                      <Button
                        variant={viewMode === 'grid' ? 'default' : 'ghost'}
                        size="sm"
                        onClick={() => {
                          setViewMode('grid')
                          storePreference('viewMode', 'grid')
                        }}
                        className="rounded-r-none"
                      >
                        <IconLayoutGrid className="h-4 w-4" />
                      </Button>
                      <Button
                        variant={viewMode === 'table' ? 'default' : 'ghost'}
                        size="sm"
                        onClick={() => {
                          setViewMode('table')
                          storePreference('viewMode', 'table')
                        }}
                        className="rounded-l-none"
                      >
                        <IconLayoutList className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                  <IconBrain className="h-4 w-4" />
                  <span>{t('documentsPage.smartSearch')}</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Loading State */}
          {isLoading && (
            <div className="flex justify-center items-center py-12">
              <IconLoader2 className="h-8 w-8 animate-spin" />
              <span className="ml-2">{t('documentsPage.loading')}</span>
            </div>
          )}

          {/* Error State */}
          {error && (
            <Card className="text-center py-12">
              <CardContent>
                <p className="text-red-600 mb-4">{error}</p>
                <Button onClick={loadDocuments} variant="outline">
                  {t('documentsPage.tryAgainButton')}
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Documents Grid View */}
          {!isLoading && !error && viewMode === 'grid' && filteredDocuments.length > 0 && (
            <DocumentList
              documents={filteredDocuments}
              viewMode="grid"
              showHighlights={true}
              useDetailedView={true}
              onDocumentClick={handleViewDocument}
              onDownload={handleDownloadDocument}
              onDelete={handleDeleteDocument}
              onShare={handleShareDocument}
              onSignature={handleRequestSignature}
              onAskEmma={handleAskEmma}
            />
          )}

          {/* Documents Table */}
          {!isLoading && !error && viewMode === 'table' && filteredDocuments.length > 0 && (
            <DocumentsDataTable
              data={filteredDocuments}
              onViewDocument={handleViewDocument}
              onEditDocument={handleEditDocument}
              onDeleteDocument={handleDeleteDocument}
              onDownloadDocument={handleDownloadDocument}
              onPreviewDocument={handleViewDocument}
              onFullPagePreview={handleFullPagePreview}
              onShareDocument={handleShareDocument}
              onRequestSignature={handleRequestSignature}
              onAskEmma={handleAskEmma}
              canConvertToTemplate={isTenantAdmin}
              onConvertToTemplate={handleConvertToTemplate}
              convertLoadingId={convertingDocumentId}
            />
          )}

          {!isLoading && !error && filteredDocuments.length === 0 && (
            <Card className="text-center py-12">
              <CardContent>
                <IconFile className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-semibold mb-2">{t('documentsPage.empty.title')}</h3>
                <p className="text-muted-foreground mb-4">
                  {searchQuery || selectedFilter !== 'all'
                    ? t('documentsPage.empty.messageWithFilter')
                    : t('documentsPage.empty.messageWithoutFilter')
                  }
                </p>
                {!searchQuery && selectedFilter === 'all' && (
                  <Button onClick={openUploadDialog}>
                    <IconPlus className="mr-2 h-4 w-4" />
                    {t('documentsPage.uploadButton')}
                  </Button>
                )}
              </CardContent>
            </Card>
          )}

          {/* Pagination - Only show for grid view */}
          {!isLoading && !error && totalPages > 1 && viewMode === 'grid' && (
            <Card className="mt-6">
              <CardContent className="p-4">
                <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
                  <div className="text-sm text-muted-foreground">
                    {t('documentsPage.pagination.showing', {
                      start: ((currentPage - 1) * perPage) + 1,
                      end: Math.min(currentPage * perPage, totalDocuments),
                      total: totalDocuments
                    })}
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                      disabled={currentPage === 1}
                    >
                      <IconChevronLeft className="h-4 w-4" />
                      {t('documentsPage.pagination.previous')}
                    </Button>

                    <div className="flex items-center gap-1">
                      <Button
                        size="sm"
                        variant={currentPage === 1 ? "default" : "outline"}
                        onClick={() => setCurrentPage(1)}
                        className="min-w-[40px]"
                      >
                        1
                      </Button>

                      {currentPage > 3 && (
                        <span className="px-2 text-muted-foreground">...</span>
                      )}

                      {Array.from({ length: totalPages }, (_, i) => i + 1)
                        .filter(page => page > 1 && page < totalPages && Math.abs(page - currentPage) <= 1)
                        .map(page => (
                          <Button
                            key={page}
                            size="sm"
                            variant={currentPage === page ? "default" : "outline"}
                            onClick={() => setCurrentPage(page)}
                            className="min-w-[40px]"
                          >
                            {page}
                          </Button>
                        ))
                      }

                      {currentPage < totalPages - 2 && (
                        <span className="px-2 text-muted-foreground">...</span>
                      )}

                      {totalPages > 1 && (
                        <Button
                          size="sm"
                          variant={currentPage === totalPages ? "default" : "outline"}
                          onClick={() => setCurrentPage(totalPages)}
                          className="min-w-[40px]"
                        >
                          {totalPages}
                        </Button>
                      )}
                    </div>

                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                      disabled={currentPage === totalPages}
                    >
                      {t('documentsPage.pagination.next')}
                      <IconChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Document Dialogs */}
          <EditDocumentDialog
            document={selectedDocument}
            open={editDialogOpen}
            onOpenChange={setEditDialogOpen}
            onSave={handleSaveDocument}
          />

          <DeleteDocumentDialog
            document={selectedDocument}
            open={deleteDialogOpen}
            onOpenChange={setDeleteDialogOpen}
            onConfirm={handleConfirmDelete}
          />


          <ShareDocumentDialog
            document={selectedDocument}
            open={shareDialogOpen}
            onOpenChange={setShareDialogOpen}
          />

        </div> {/* End main content */}

      </div>
    </div>
  )
}
  const handleEntitySelectForSearch = (entity: SearchEntity) => {
    setSelectedEntities(prev => {
      if (prev.some(e => e.id === entity.id)) {
        return prev
      }
      return [...prev, entity]
    })
  }

  const handleRemoveSearchEntity = (entityId: string) => {
    setSelectedEntities(prev => prev.filter(entity => entity.id !== entityId))
  }

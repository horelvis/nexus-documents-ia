"use client"

import { useState, useEffect, useCallback, useRef, useMemo } from "react"
import { useParams, useRouter } from "next/navigation"
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
  IconAlertTriangle
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
import { 
  EditDocumentDialog, 
  DocumentViewerDialog, 
  DeleteDocumentDialog,
  DocumentsDataTable 
} from "@/components/documents"
import { ShareDocumentDialog } from "@/components/documents/share-document-dialog"
import { getFileIcon, formatFileSize } from "@/lib/document-utils"
import { useTranslation } from "@/lib/i18n/hooks"

const DOCUMENT_FILTERS = [
  { value: 'all', label: 'All Documents' },
  { value: 'recent', label: 'Recent Documents' },
] as const

type DocumentFilterOption = typeof DOCUMENT_FILTERS[number]['value']

const isDocumentFilterOption = (value: unknown): value is DocumentFilterOption =>
  DOCUMENT_FILTERS.some(filter => filter.value === value)

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
    return DOCUMENT_FILTERS.find(option => option.value === selectedFilter)?.label ?? 'All Documents'
  }, [selectedFilter])
  // Siempre usar búsqueda semántica por contenido
  const useDeepSearch = true

  // Local state for search input
  const [localSearchQuery, setLocalSearchQuery] = useState(searchQuery)

  const handleFilterChange = (value: DocumentFilterOption) => {
    setSelectedFilter(value)
    storePreference('filter', value)
  }

  const handleSearchConfirm = () => {
    setSearchQuery(localSearchQuery)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearchConfirm()
    }
  }
  
  // Dialog states
  const [viewDialogOpen, setViewDialogOpen] = useState(false)
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
        
        // Transform search results to match document format
        const documents = searchResults.data?.map(result => {
          const doc = result.document || result || {}
          return {
            ...doc,
            id: doc.id || '',
            title: doc.title || doc.filename || 'Untitled',
            filename: doc.filename || 'unknown',
            status: 'active' as const,
            created_by: doc.created_by || {},
            tenant_id: tenantId,
            indexed: doc.indexed || 'INDEXED',
            file_hash: doc.file_hash || '',
            version: doc.version || 1,
            category: doc.category || '',
            document_metadata: doc.document_metadata || {},
            content: doc.content || '',
            extracted_entities: doc.extracted_entities || null,
            ocr_status: doc.ocr_status || null,
            ocr_completed_at: doc.ocr_completed_at || null,
            signature_fields: doc.signature_fields || null,
            file_type: doc.file_type || 'unknown',
            mime_type: doc.mime_type || 'application/octet-stream',
            file_size: doc.file_size || 0,
            created_at: doc.created_at || new Date().toISOString(),
            updated_at: doc.updated_at || new Date().toISOString(),
            tags: doc.tags || [],
            description: doc.description || ''
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
    console.log('[DEBUG] DocumentsPage: handleDocumentsUpdated received payload:', payload)

    if (payload?.tenantId && payload.tenantId !== tenantId) {
      console.log('[DEBUG] DocumentsPage: Tenant ID mismatch, ignoring event')
      return
    }

    if (payload?.source === 'upload') {
      console.log('[DEBUG] DocumentsPage: Processing upload event')
      const uploadedFiles = payload.files || []
      if (!uploadedFiles.length) {
        console.log('[DEBUG] DocumentsPage: No files in payload, skipping')
        return
      }

      const successfulUploads = uploadedFiles.filter(file => file.status === 'success')
      if (!successfulUploads.length) {
         console.log('[DEBUG] DocumentsPage: No successful uploads, skipping')
        return
      }

      // closeUploadDialog is now handled in GlobalUploadDialog

      addNotification({
        type: 'upload',
        title: 'Upload Complete',
        message: `${successfulUploads.length} file${successfulUploads.length > 1 ? 's' : ''} uploaded successfully`,
        fileCount: successfulUploads.length,
        action: {
          label: 'View Documents',
          href: '/documents'
        }
      })

      console.log('[DEBUG] DocumentsPage: Resetting filters and search')
      setSearchQuery('')
      setSelectedFilter('all')
      storePreference('filter', 'all')
      setCurrentPage(1)

      // Wait a bit for Elasticsearch to index the new documents (now removed, refreshing immediately)
      console.log('[DEBUG] DocumentsPage: Executing immediate loadDocuments')
      loadDocuments()

      return
    }
    
    console.log('[DEBUG] DocumentsPage: Generic update event, reloading documents immediately')
    loadDocuments()
  }, [addNotification, closeUploadDialog, loadDocuments, setCurrentPage, setSearchQuery, setSelectedFilter, storePreference, tenantId])

  useDocumentEvent("documents:updated", handleDocumentsUpdated)

  // Document operations
  const handleViewDocument = (document: ApiDocument) => {
    setSelectedDocument(document)
    setViewDialogOpen(true)
  }

  const handleEditDocument = (document: ApiDocument) => {
    setSelectedDocument(document)
    setEditDialogOpen(true)
  }

  const handleDeleteDocument = (document: ApiDocument) => {
    setSelectedDocument(document)
    setDeleteDialogOpen(true)
  }

  const handlePreviewDocument = (document: ApiDocument) => {
    router.push(`/${tenantId}/documents/${document.id}/preview`)
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
        title: 'Formato no soportado',
        message: 'Solo se pueden convertir documentos ODT en plantillas.'
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
        title: 'Plantilla creada',
        message: `La plantilla "${template.name}" se ha creado correctamente.`
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
        title: 'Conversión fallida',
        message: error instanceof Error ? error.message : 'No se pudo convertir el documento.'
      })
    } finally {
      setConvertingDocumentId(null)
    }
  }, [isTenantAdmin, documentService, addNotification, openTemplateInGoogleDocs, isOdtDocument])

  const handleRequestSignature = (document: ApiDocument) => {
    router.push(`/${tenantId}/documents/${document.id}/signature-request`)
  }

  const handleFullPagePreview = (document: ApiDocument) => {
    router.push(`/${tenantId}/documents/${document.id}/preview`)
  }

  const handleDownloadDocument = async (document: ApiDocument) => {
    try {
      addNotification({
        type: 'info',
        title: 'Downloading',
        message: `Downloading ${document.filename}...`
      })
      
      const result = await documentService.downloadDocument(document.id)
      
      if ('error' in result) {
        addNotification({
          type: 'error',
          title: 'Download Failed',
          message: result.error
        })
        return
      }

      // Verify we have a blob
      if (!result.blob || !(result.blob instanceof Blob)) {
        addNotification({
          type: 'error',
          title: 'Download Failed',
          message: 'Invalid file data received'
        })
        return
      }

      // Create download link
      const url = URL.createObjectURL(result.blob)
      const a = window.document.createElement('a')
      a.href = url
      a.download = result.filename || document.filename || 'document'
      a.style.display = 'none'
      window.document.body.appendChild(a)
      a.click()
      
      // Cleanup
      setTimeout(() => {
        window.document.body.removeChild(a)
        URL.revokeObjectURL(url)
      }, 100)

      addNotification({
        type: 'success',
        title: 'Download Complete',
        message: `${document.filename} downloaded successfully`
      })
    } catch (error) {
      console.error('Download exception:', error)
      addNotification({
        type: 'error',
        title: 'Download Failed',
        message: error instanceof Error ? error.message : 'Unknown error occurred'
      })
    }
  }

  const handleSaveDocument = async (id: string, updates: Partial<Pick<ApiDocument, 'title' | 'description' | 'tags' | 'category'>>) => {
    try {
      const response = await documentService.updateDocument(id, updates)
      
      if (response.error) {
        addNotification({
          type: 'error',
          title: 'Update Failed',
          message: response.error
        })
        return
      }

      // Update local state
      setDocuments(prev => prev.map(doc => 
        doc.id === id ? { ...doc, ...updates } : doc
      ))

      addNotification({
        type: 'success',
        title: 'Document Updated',
        message: 'Document information has been updated successfully'
      })
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Update Failed',
        message: error instanceof Error ? error.message : 'Unknown error occurred'
      })
      throw error // Re-throw to prevent dialog from closing
    }
  }

  const handleConfirmDelete = async (id: string) => {
    try {
      const response = await documentService.deleteDocument(id)
      
      if (response.error) {
        addNotification({
          type: 'error',
          title: 'Delete Failed',
          message: response.error
        })
        return
      }

      // Remove from local state
      setDocuments(prev => prev.filter(doc => doc.id !== id))

      addNotification({
        type: 'success',
        title: 'Document Deleted',
        message: 'Document has been deleted successfully'
      })

      emitDocumentEvent("documents:updated", {
        tenantId,
        source: "delete"
      })
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Delete Failed',
        message: error instanceof Error ? error.message : 'Unknown error occurred'
      })
      throw error // Re-throw to prevent dialog from closing
    }
  }

  const handleGetDocumentContent = async (id: string) => {
    try {
      const response = await documentService.getDocumentContent(id)
      if (response.error) {
        return { error: response.error }
      }
      return { content: response.data?.content }
    } catch (error) {
      return { error: error instanceof Error ? error.message : 'Failed to load content' }
    }
  }

  const handleGetDocumentSummary = async (id: string) => {
    try {
      const response = await documentService.getDocumentSummary(id)
      if (response.error) {
        return { error: response.error }
      }
      return { summary: response.data?.summary }
    } catch (error) {
      return { error: error instanceof Error ? error.message : 'Failed to load summary' }
    }
  }

  return (
    <div className="flex flex-col gap-4 p-6 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
          <div>
            <h1 className="text-3xl font-bold mb-2">Document Library</h1>
            <p className="text-muted-foreground">
              Manage and organize your uploaded documents
            </p>
          </div>
          <Button onClick={openUploadDialog}>
            <IconPlus className="mr-2 h-4 w-4" />
            Upload Document
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
                    placeholder="Search documents... (usa @ para mencionar entidades)"
                    value={localSearchQuery}
                    onChange={setLocalSearchQuery}
                    onKeyDown={handleKeyDown}
                    className="pl-10 border bg-background shadow-sm"
                    documentId="general"
                    onEntitySelect={(entity) => {
                      console.log("Entity selected in document search:", entity)
                      // Optionally trigger search when entity is selected
                      handleSearchConfirm() // Trigger search on entity select
                    }}
                  />
                </div>
                
                <div className="flex items-center gap-2 flex-wrap">
                  <Button onClick={handleSearchConfirm} variant="outline" className="flex-shrink-0">
                    Search
                  </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline">
                      <IconFilter className="mr-2 h-4 w-4" />
                      Filter: {selectedFilterLabel}
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
              
              {/* Búsqueda semántica siempre habilitada */}
              <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                <IconBrain className="h-4 w-4" />
                <span>Búsqueda inteligente por contenido activada</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Loading State */}
        {isLoading && (
          <div className="flex justify-center items-center py-12">
            <IconLoader2 className="h-8 w-8 animate-spin" />
            <span className="ml-2">Loading documents...</span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <Card className="text-center py-12">
            <CardContent>
              <p className="text-red-600 mb-4">{error}</p>
              <Button onClick={loadDocuments} variant="outline">
                Try Again
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Documents List */}
        {!isLoading && !error && viewMode === 'grid' && filteredDocuments.length > 0 && (
          <div className="space-y-2">
            {filteredDocuments.map((document: any) => (
              <Card 
                key={document.id} 
                className="hover:shadow-lg transition-shadow cursor-pointer group"
                onClick={() => handleViewDocument(document)}
              >
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    {/* File Icon */}
                    <div className="flex-shrink-0">
                      {getFileIcon(document.file_type, document.mime_type, document.filename)}
                    </div>
                    
                    {/* Document Info */}
                    <div className="flex-grow min-w-0">
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <div className="min-w-0 flex-1">
                          <h3 
                            className="text-base font-medium truncate cursor-pointer hover:text-blue-600 transition-colors" 
                            title={document.title || document.filename}
                            onClick={(e) => {
                              e.stopPropagation()
                              handleFullPagePreview(document)
                            }}
                          >
                            {document.title || document.filename}
                          </h3>
                          {document.description && (
                            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                              {document.description}
                            </p>
                          )}
                        </div>
                      </div>
                      
                      {/* Metadata and Actions */}
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <span>Size: {formatFileSize(document.file_size)}</span>
                          <span>•</span>
                          <span>Uploaded: {new Date(document.created_at).toLocaleDateString()}</span>
                          <span>•</span>
                          <span>{document.category || 'Sin Categoría'}</span>
                        </div>
                        
                        {/* Actions */}
                        <div className="flex gap-0.5 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                          {/* 3 Main Actions */}
                          <Button 
                            size="sm" 
                            variant="ghost"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleFullPagePreview(document)
                            }}
                            title="Full Preview"
                            className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                          >
                            <IconEye className="h-3.5 w-3.5" />
                          </Button>
                          <Button 
                            size="sm" 
                            variant="ghost"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDownloadDocument(document)
                            }}
                            title="Download"
                            className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                          >
                            <IconDownload className="h-3.5 w-3.5" />
                          </Button>
                          <Button 
                            size="sm" 
                            variant="ghost"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleShareDocument(document)
                            }}
                            title="Share"
                            className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                          >
                            <IconShare2 className="h-3.5 w-3.5" />
                          </Button>
                          
                          {/* More Actions Dropdown */}
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button 
                                size="sm" 
                                variant="ghost"
                                onClick={(e) => e.stopPropagation()}
                                title="More actions"
                                className="h-7 w-7 p-0 opacity-80 group-hover:opacity-100"
                              >
                                <IconDotsVertical className="h-3.5 w-3.5" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => handleViewDocument(document)}>
                                <IconEye className="mr-2 h-4 w-4" />
                                View Details
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => handleDownloadDocument(document)}>
                                <IconDownload className="mr-2 h-4 w-4" />
                                Download
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => handleRequestSignature(document)}>
                                <IconSignature className="mr-2 h-4 w-4" />
                                Request Signature
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => handleEditDocument(document)}>
                                <IconEdit className="mr-2 h-4 w-4" />
                                Edit
                              </DropdownMenuItem>
                              {isTenantAdmin && (
                                <DropdownMenuItem
                                  onClick={(event) => {
                                    event.preventDefault()
                                    event.stopPropagation()
                                    handleConvertToTemplate(document)
                                  }}
                                  disabled={convertingDocumentId === document.id}
                                >
                                  {convertingDocumentId === document.id ? (
                                    <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                                  ) : (
                                    <IconFileTypeDoc className="mr-2 h-4 w-4" />
                                  )}
                                  Convert to Template
                                </DropdownMenuItem>
                              )}
                              
                              
                              <DropdownMenuSeparator />
                              
                              <DropdownMenuItem 
                                onClick={() => handleDeleteDocument(document)}
                                className="text-red-600 focus:text-red-600"
                              >
                                <IconTrash className="mr-2 h-4 w-4" />
                                Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </div>
                      
                      {/* Tags */}
                      {(document.tags || []).length > 0 && (
                        <div className="flex flex-wrap gap-0.5">
                          {(document.tags || []).map((tag: string) => (
                            <Badge key={tag} variant="outline" className="text-xs px-1.5 py-0 h-5">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Documents Table */}
        {!isLoading && !error && viewMode === 'table' && filteredDocuments.length > 0 && (
          <DocumentsDataTable
            data={filteredDocuments}
            onViewDocument={handleViewDocument}
            onEditDocument={handleEditDocument}
            onDeleteDocument={handleDeleteDocument}
            onDownloadDocument={handleDownloadDocument}
            onPreviewDocument={handlePreviewDocument}
            onFullPagePreview={handleFullPagePreview}
            onShareDocument={handleShareDocument}
            onRequestSignature={handleRequestSignature}
            canConvertToTemplate={isTenantAdmin}
            onConvertToTemplate={handleConvertToTemplate}
            convertLoadingId={convertingDocumentId}
          />
        )}

        {!isLoading && !error && filteredDocuments.length === 0 && (
          <Card className="text-center py-12">
            <CardContent>
              <IconFile className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">No documents found</h3>
              <p className="text-muted-foreground mb-4">
                {searchQuery || selectedFilter !== 'all' 
                  ? 'Try adjusting your search or filter criteria.'
                  : 'Get started by uploading your first document.'
                }
              </p>
              {!searchQuery && selectedFilter === 'all' && (
                <Button onClick={openUploadDialog}>
                  <IconPlus className="mr-2 h-4 w-4" />
                  Upload Document
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
                  Showing {((currentPage - 1) * perPage) + 1} to {Math.min(currentPage * perPage, totalDocuments)} of {totalDocuments} documents
                </div>
                
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                    disabled={currentPage === 1}
                  >
                    <IconChevronLeft className="h-4 w-4" />
                    Previous
                  </Button>
                  
                  <div className="flex items-center gap-1">
                    {/* Show first page */}
                    <Button
                      size="sm"
                      variant={currentPage === 1 ? "default" : "outline"}
                      onClick={() => setCurrentPage(1)}
                      className="min-w-[40px]"
                    >
                      1
                    </Button>
                    
                    {/* Show dots if needed */}
                    {currentPage > 3 && (
                      <span className="px-2 text-muted-foreground">...</span>
                    )}
                    
                    {/* Show pages around current page */}
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
                    
                    {/* Show dots if needed */}
                    {currentPage < totalPages - 2 && (
                      <span className="px-2 text-muted-foreground">...</span>
                    )}
                    
                    {/* Show last page */}
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
                    Next
                    <IconChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Document Dialogs */}
        <DocumentViewerDialog
          document={selectedDocument}
          open={viewDialogOpen}
          onOpenChange={setViewDialogOpen}
          onGetContent={handleGetDocumentContent}
          onGetSummary={handleGetDocumentSummary}
          onDownload={handleDownloadDocument}
        />

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

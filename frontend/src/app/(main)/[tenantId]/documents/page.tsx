"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import { 
  IconPlus, 
  IconSearch, 
  IconFilter,
  IconFile,
  IconFileText,
  IconFileTypePdf,
  IconClock,
  IconEye,
  IconDownload,
  IconTrash,
  IconEdit,
  IconLoader2,
  IconPhoto,
  IconChevronLeft,
  IconChevronRight,
  IconLayoutGrid,
  IconLayoutList,
  IconShare2,
  IconSignature
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from "@/components/ui/dropdown-menu"
import { useUpload } from "@/contexts/upload-context"
import { useNotifications } from "@/contexts/notifications-context"
import { useDocumentService } from "@/lib/services/document.service"
import { Document as ApiDocument } from "@/lib/types"
import { 
  EditDocumentDialog, 
  DocumentViewerDialog, 
  DeleteDocumentDialog,
  DocumentPreviewDialog,
  DocumentsDataTable 
} from "@/components/documents"
import { ShareDocumentDialog } from "@/components/documents/share-document-dialog"
import { getFileIcon, formatFileSize, getStatusColor, getStatusLabel } from "@/lib/document-utils"

export default function DocumentsPage() {
  const params = useParams()
  const router = useRouter()
  const tenantId = params.tenantId as string

  const [documents, setDocuments] = useState<ApiDocument[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedFilter, setSelectedFilter] = useState('all')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Pagination state
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalDocuments, setTotalDocuments] = useState(0)
  const [perPage] = useState(10)
  
  // View state
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid')
  
  // Dialog states
  const [viewDialogOpen, setViewDialogOpen] = useState(false)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false)
  const [shareDialogOpen, setShareDialogOpen] = useState(false)
  const [selectedDocument, setSelectedDocument] = useState<ApiDocument | null>(null)
  
  const { openUploadDialog, setOnUploadComplete } = useUpload()
  const { addNotification } = useNotifications()
  const documentService = useDocumentService()

  // Load documents from API - simple pattern
  const loadDocuments = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      // For table view, load all documents to handle pagination client-side
      const itemsPerPage = viewMode === 'table' ? 100 : perPage
      const response = await documentService.getDocuments({
        search: searchQuery || undefined,
        status: selectedFilter !== 'all' ? selectedFilter : undefined,
        per_page: itemsPerPage,
        page: viewMode === 'table' ? 1 : currentPage
      })
      
      if (response.error) {
        setError(response.error)
      } else {
        setDocuments(response.data?.items || [])
        setTotalPages(response.data?.pages || 1)
        setTotalDocuments(response.data?.total || 0)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load documents')
    } finally {
      setIsLoading(false)
    }
  }

  // Load on mount
  useEffect(() => {
    loadDocuments()
  }, [])

  // Reload when filters, pagination or view mode changes
  useEffect(() => {
    loadDocuments()
  }, [selectedFilter, currentPage, viewMode])
  
  // Reset to page 1 when filter or view mode changes
  useEffect(() => {
    setCurrentPage(1)
  }, [selectedFilter, searchQuery, viewMode])


  // Documents are already filtered server-side
  const filteredDocuments = documents || []

  const handleUploadComplete = (uploadedFiles: Array<{file: File, id: string, status: string}>) => {
    // Reload documents from server to get the latest data
    loadDocuments()
    
    // Show success notification
    addNotification({
      type: 'upload',
      title: 'Upload Complete',
      message: `${uploadedFiles.length} file${uploadedFiles.length > 1 ? 's' : ''} uploaded successfully`,
      fileCount: uploadedFiles.length,
      action: {
        label: 'View Documents',
        href: '/documents'
      }
    })
  }

  // Register upload completion handler for this page
  useEffect(() => {
    setOnUploadComplete(handleUploadComplete)
    
    return () => {
      setOnUploadComplete(undefined)
    }
  }, [])

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
    setSelectedDocument(document)
    setPreviewDialogOpen(true)
  }

  const handleShareDocument = (document: ApiDocument) => {
    setSelectedDocument(document)
    setShareDialogOpen(true)
  }

  const handleRequestSignature = (document: ApiDocument) => {
    router.push(`/${tenantId}/documents/${document.id}/signature-request`)
  }

  const handleFullPagePreview = (document: ApiDocument) => {
    router.push(`/${tenantId}/documents/${document.id}/preview`)
  }

  const handleDownloadDocument = async (document: ApiDocument) => {
    try {
      const result = await documentService.downloadDocument(document.id)
      
      if ('error' in result) {
        addNotification({
          type: 'error',
          title: 'Download Failed',
          message: result.error
        })
        return
      }

      // Create download link
      const url = URL.createObjectURL(result.blob)
      const link = document.createElement('a')
      link.href = url
      link.download = result.filename
      document.body.appendChild(link)
      link.click()
      
      // Cleanup
      document.body.removeChild(link)
      URL.revokeObjectURL(url)

      addNotification({
        type: 'success',
        title: 'Download Started',
        message: `${result.filename} is being downloaded`
      })
    } catch (error) {
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

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <IconFile className="h-8 w-8 text-blue-500" />
                <div className="ml-3">
                  <p className="text-sm font-medium text-muted-foreground">Total Documents</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? <IconLoader2 className="h-6 w-6 animate-spin" /> : (documents || []).length}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <IconClock className="h-8 w-8 text-green-500" />
                <div className="ml-3">
                  <p className="text-sm font-medium text-muted-foreground">Processed</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? <IconLoader2 className="h-6 w-6 animate-spin" /> : (documents || []).filter((d: any) => d.indexed === 'INDEXED').length}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <IconEye className="h-8 w-8 text-purple-500" />
                <div className="ml-3">
                  <p className="text-sm font-medium text-muted-foreground">Recently Viewed</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? <IconLoader2 className="h-6 w-6 animate-spin" /> : (documents || []).filter((d: any) => d.indexed === 'INDEXED').length}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <IconDownload className="h-8 w-8 text-orange-500" />
                <div className="ml-3">
                  <p className="text-sm font-medium text-muted-foreground">Processing</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? <IconLoader2 className="h-6 w-6 animate-spin" /> : (documents || []).filter((d: any) => d.indexed === 'PROCESSING').length}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Search and Filter */}
        <Card className="mb-6">
          <CardContent className="p-6">
            <div className="flex flex-col sm:flex-row gap-4">
              <div className="flex-1 flex gap-2">
                <div className="flex-1 relative">
                  <IconSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                  <Input
                    placeholder="Search documents..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && loadDocuments()}
                    className="pl-10"
                  />
                </div>
                <Button onClick={loadDocuments} variant="outline">
                  Search
                </Button>
              </div>
              
              <div className="flex items-center gap-2">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline">
                      <IconFilter className="mr-2 h-4 w-4" />
                      Filter: {selectedFilter === 'all' ? 'All' : selectedFilter}
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    <DropdownMenuItem onClick={() => setSelectedFilter('all')}>
                      All Documents
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setSelectedFilter('INDEXED')}>
                      Indexed
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setSelectedFilter('PROCESSING')}>
                      Processing
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setSelectedFilter('INDEXING_ERROR')}>
                      Error
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                
                {/* View Toggle */}
                <div className="flex items-center rounded-md border">
                  <Button
                    variant={viewMode === 'grid' ? 'default' : 'ghost'}
                    size="sm"
                    onClick={() => setViewMode('grid')}
                    className="rounded-r-none"
                  >
                    <IconLayoutGrid className="h-4 w-4" />
                  </Button>
                  <Button
                    variant={viewMode === 'table' ? 'default' : 'ghost'}
                    size="sm"
                    onClick={() => setViewMode('table')}
                    className="rounded-l-none"
                  >
                    <IconLayoutList className="h-4 w-4" />
                  </Button>
                </div>
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
        {!isLoading && !error && viewMode === 'grid' && (
          <div className="space-y-2">
            {filteredDocuments.map((document: any) => (
              <Card key={document.id} className="hover:shadow-lg transition-shadow">
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
                          <h3 className="text-base font-medium truncate" title={document.title || document.filename}>
                            {document.title || document.filename}
                          </h3>
                          {document.description && (
                            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                              {document.description}
                            </p>
                          )}
                        </div>
                        <Badge className={getStatusColor(document.indexed)} variant="secondary" size="sm">
                          {getStatusLabel(document.indexed)}
                        </Badge>
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
                        <div className="flex gap-0.5 flex-shrink-0">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button 
                                size="sm" 
                                variant="ghost"
                                title="Preview options"
                                className="h-7 w-7 p-0"
                              >
                                <IconPhoto className="h-3.5 w-3.5" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => handlePreviewDocument(document)}>
                                <IconPhoto className="mr-2 h-4 w-4" />
                                Quick Preview
                              </DropdownMenuItem>
                              <DropdownMenuItem onClick={() => handleFullPagePreview(document)}>
                                <IconEye className="mr-2 h-4 w-4" />
                                Full Page Preview
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                          <Button 
                            size="sm" 
                            variant="ghost"
                            onClick={() => handleViewDocument(document)}
                            title="View details"
                            className="h-7 w-7 p-0"
                          >
                            <IconEye className="h-3.5 w-3.5" />
                          </Button>
                          <Button 
                            size="sm" 
                            variant="ghost"
                            onClick={() => handleDownloadDocument(document)}
                            title="Download"
                            className="h-7 w-7 p-0"
                          >
                            <IconDownload className="h-3.5 w-3.5" />
                          </Button>
                          <Button 
                            size="sm" 
                            variant="ghost"
                            onClick={() => handleShareDocument(document)}
                            title="Share"
                            className="h-7 w-7 p-0"
                          >
                            <IconShare2 className="h-3.5 w-3.5" />
                          </Button>
                          <Button 
                            size="sm" 
                            variant="ghost"
                            onClick={() => handleRequestSignature(document)}
                            title="Request Signature"
                            className="h-7 w-7 p-0"
                          >
                            <IconSignature className="h-3.5 w-3.5" />
                          </Button>
                          <Button 
                            size="sm" 
                            variant="ghost"
                            onClick={() => handleEditDocument(document)}
                            title="Edit"
                            className="h-7 w-7 p-0"
                          >
                            <IconEdit className="h-3.5 w-3.5" />
                          </Button>
                          <Button 
                            size="sm" 
                            variant="ghost" 
                            className="text-red-600 hover:text-red-700 hover:bg-red-50 h-7 w-7 p-0"
                            onClick={() => handleDeleteDocument(document)}
                            title="Delete"
                          >
                            <IconTrash className="h-3.5 w-3.5" />
                          </Button>
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
        {!isLoading && !error && viewMode === 'table' && (
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

        <DocumentPreviewDialog
          document={selectedDocument}
          open={previewDialogOpen}
          onOpenChange={setPreviewDialogOpen}
        />

        <ShareDocumentDialog
          document={selectedDocument}
          open={shareDialogOpen}
          onOpenChange={setShareDialogOpen}
        />

      </div>
    </div>
  )
}
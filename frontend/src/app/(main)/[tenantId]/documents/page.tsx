"use client"

import { useState, useEffect } from "react"
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
  IconLoader2
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

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<ApiDocument[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedFilter, setSelectedFilter] = useState('all')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  const { openUploadDialog, setOnUploadComplete } = useUpload()
  const { addNotification } = useNotifications()
  const documentService = useDocumentService()

  // Load documents from API - simple pattern
  const loadDocuments = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await documentService.getDocuments({
        search: searchQuery || undefined,
        status: selectedFilter !== 'all' ? selectedFilter : undefined,
        per_page: 50,
        page: 1
      })
      
      if (response.error) {
        setError(response.error)
      } else {
        setDocuments(response.data?.documents || [])
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

  // Reload when filters change
  useEffect(() => {
    loadDocuments()
  }, [selectedFilter])

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const getFileIcon = (fileType: string) => {
    if (fileType.includes('pdf')) {
      return <IconFileTypePdf className="h-5 w-5 text-red-500" />
    } else if (fileType.includes('word') || fileType.includes('doc')) {
      return <IconFileText className="h-5 w-5 text-blue-500" />
    } else {
      return <IconFile className="h-5 w-5 text-gray-500" />
    }
  }

  const getStatusColor = (indexed: string) => {
    switch (indexed) {
      case 'INDEXED':
        return 'bg-green-100 text-green-800'
      case 'PROCESSING':
        return 'bg-yellow-100 text-yellow-800'
      case 'INDEXING_ERROR':
        return 'bg-red-100 text-red-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const filteredDocuments = (documents || []).filter((doc: any) => {
    const matchesSearch = doc.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         (doc.tags || []).some((tag: string) => tag.toLowerCase().includes(searchQuery.toLowerCase()))
    
    if (selectedFilter === 'all') return matchesSearch
    // Backend uses 'indexed' field instead of 'status'
    return matchesSearch && doc.indexed === selectedFilter
  })

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

  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
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

        {/* Documents Grid */}
        {!isLoading && !error && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredDocuments.map((document: any) => (
              <Card key={document.id} className="hover:shadow-lg transition-shadow">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      {getFileIcon(document.file_type)}
                      <div className="min-w-0 flex-1">
                        <CardTitle className="text-base truncate" title={document.filename}>
                          {document.title || document.filename}
                        </CardTitle>
                      </div>
                    </div>
                    <Badge className={getStatusColor(document.indexed)} variant="secondary">
                      {document.indexed}
                    </Badge>
                  </div>
                </CardHeader>
                
                <CardContent>
                  <div className="space-y-3">
                    <div className="text-sm text-muted-foreground">
                      <p>Size: {formatFileSize(document.file_size)}</p>
                      <p>Uploaded: {new Date(document.created_at).toLocaleDateString()}</p>
                      {document.updated_at && (
                        <p>Updated: {new Date(document.updated_at).toLocaleDateString()}</p>
                      )}
                    </div>
                    
                    <div className="flex flex-wrap gap-1">
                      {(document.tags || []).map((tag: string) => (
                        <Badge key={tag} variant="outline" className="text-xs">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                    
                    <div className="flex justify-between pt-2">
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline">
                          <IconEye className="h-4 w-4" />
                        </Button>
                        <Button size="sm" variant="outline">
                          <IconDownload className="h-4 w-4" />
                        </Button>
                        <Button size="sm" variant="outline">
                          <IconEdit className="h-4 w-4" />
                        </Button>
                      </div>
                      <Button size="sm" variant="outline" className="text-red-600 hover:text-red-700">
                        <IconTrash className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
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


      </div>
    </div>
  )
}
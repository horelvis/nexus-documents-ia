"use client"

import { useState, useEffect, useCallback } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  IconLoader2,
  IconFile,
  IconFileText,
  IconFileTypePdf,
  IconDownload,
  IconEye,
  IconClock,
  IconUser,
  IconTag,
  IconFolder
} from "@tabler/icons-react"
import { Document } from "@/lib/types"
import { getFileIcon, formatFileSize, getStatusColor } from "@/lib/document-utils"
import { useDocumentService } from "@/lib/services/document.service"
import dynamic from "next/dynamic"

const PDFViewer = dynamic(() => import("@/components/documents/pdf-viewer"), {
  ssr: false,
  loading: () => <div className="flex justify-center p-4"><IconLoader2 className="animate-spin" /></div>
})

interface DocumentViewerDialogProps {
  document: Document | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onGetContent: (id: string) => Promise<{ content?: string; error?: string }>
  onGetSummary: (id: string) => Promise<{ summary?: string; error?: string }>
  onDownload: (document: Document) => Promise<void> | void
}

export function DocumentViewerDialog({
  document,
  open,
  onOpenChange,
  onGetContent,
  onGetSummary,
  onDownload
}: DocumentViewerDialogProps) {
  const documentService = useDocumentService()
  const [activeTab, setActiveTab] = useState<'info' | 'preview' | 'content' | 'summary'>('info')
  const [content, setContent] = useState<string | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [loadingContent, setLoadingContent] = useState(false)
  const [loadingSummary, setLoadingSummary] = useState(false)
  const [contentError, setContentError] = useState<string | null>(null)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  // PDF preview state (using blob URL pattern like analysis page)
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [loadingPdf, setLoadingPdf] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)

  // Reset state when document changes
  useEffect(() => {
    if (document) {
      setActiveTab('info')
      setContent(null)
      setSummary(null)
      setContentError(null)
      setSummaryError(null)
      // Reset PDF state
      if (pdfUrl) {
        URL.revokeObjectURL(pdfUrl)
      }
      setPdfUrl(null)
      setPdfError(null)
    }
  }, [document])

  // Cleanup blob URL on unmount
  useEffect(() => {
    return () => {
      if (pdfUrl) {
        URL.revokeObjectURL(pdfUrl)
      }
    }
  }, [pdfUrl])


  // Load PDF as blob (same pattern as analysis page - avoids CORS)
  const handleLoadPdf = useCallback(async () => {
    console.log('[DocumentViewerDialog] handleLoadPdf called', {
      hasDocument: !!document,
      documentId: document?.id,
      fileType: document?.file_type,
      mimeType: document?.mime_type,
      hasPdfUrl: !!pdfUrl,
      loadingPdf
    })

    if (!document || pdfUrl || loadingPdf) {
      console.log('[DocumentViewerDialog] Skipping load - conditions not met')
      return
    }

    setLoadingPdf(true)
    setPdfError(null)

    try {
      let result

      const isPdf = document.file_type === 'pdf' || document.mime_type === 'application/pdf'
      console.log('[DocumentViewerDialog] isPdf:', isPdf)

      if (isPdf) {
        console.log('[DocumentViewerDialog] Downloading original PDF...')
        result = await documentService.downloadDocument(document.id)
      } else {
        console.log('[DocumentViewerDialog] Downloading converted PDF...')
        result = await documentService.downloadConvertedDocument(document.id)
      }

      console.log('[DocumentViewerDialog] Download result:', {
        hasBlob: 'blob' in result,
        blobSize: 'blob' in result ? result.blob?.size : null,
        blobType: 'blob' in result ? result.blob?.type : null,
        error: 'error' in result ? result.error : null
      })

      if ('blob' in result && result.blob) {
        const localUrl = URL.createObjectURL(result.blob)
        console.log('[DocumentViewerDialog] Created blob URL:', localUrl)
        setPdfUrl(localUrl)
      } else if ('error' in result) {
        console.error('[DocumentViewerDialog] Download error:', result.error)
        setPdfError(result.error || 'Error al cargar el PDF')
      } else {
        console.error('[DocumentViewerDialog] Unexpected result - no blob and no error')
        setPdfError('Respuesta inesperada del servidor')
      }
    } catch (err) {
      console.error('[DocumentViewerDialog] Exception loading PDF:', err)
      setPdfError('Error inesperado al cargar el PDF')
    } finally {
      setLoadingPdf(false)
    }
  }, [document, pdfUrl, loadingPdf, documentService])

  const handleLoadContent = async () => {
    if (!document || content) return

    setLoadingContent(true)
    setContentError(null)

    try {
      const result = await onGetContent(document.id)
      if (result.error) {
        setContentError(result.error)
      } else {
        setContent(result.content || 'No content available')
      }
    } catch (error) {
      setContentError('Failed to load content')
    } finally {
      setLoadingContent(false)
    }
  }

  const handleLoadSummary = async () => {
    if (!document || summary) return

    setLoadingSummary(true)
    setSummaryError(null)
    
    try {
      const result = await onGetSummary(document.id)
      if (result.error) {
        setSummaryError(result.error)
      } else {
        setSummary(result.summary || 'No summary available')
      }
    } catch (error) {
      setSummaryError('Failed to load summary')
    } finally {
      setLoadingSummary(false)
    }
  }

  const handleTabChange = (tab: 'info' | 'preview' | 'content' | 'summary') => {
    console.log('[DocumentViewerDialog] Tab changed to:', tab, {
      pdfUrl: !!pdfUrl,
      loadingPdf
    })
    setActiveTab(tab)

    if (tab === 'preview' && !pdfUrl && !loadingPdf) {
      console.log('[DocumentViewerDialog] Triggering PDF load')
      handleLoadPdf()
    } else if (tab === 'content' && !content && !loadingContent) {
      handleLoadContent()
    } else if (tab === 'summary' && !summary && !loadingSummary) {
      handleLoadSummary()
    }
  }

  if (!document) return null

  const isPreviewable = document && (
    document.mime_type === 'application/pdf' ||
    document.file_type?.toLowerCase() === 'pdf' ||
    document.file_type?.toLowerCase() === 'odt' ||
    document.mime_type?.includes('opendocument')
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[800px] max-h-[90vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-center gap-3">
            {getFileIcon(document.file_type, document.mime_type, document.filename, 'lg')}
            <div className="flex-1 min-w-0">
              <DialogTitle className="truncate">
                {document.title || document.filename}
              </DialogTitle>
              <div className="flex items-center gap-2 mt-1">
                <Badge className={getStatusColor(document.indexed)} variant="secondary">
                  {document.indexed}
                </Badge>
                <span className="text-sm text-muted-foreground">
                  {formatFileSize(document.file_size)}
                </span>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onDownload(document)}
            >
              <IconDownload className="h-4 w-4" />
            </Button>
          </div>
        </DialogHeader>

        {/* Tab Navigation */}
        <div className="flex border-b">
          <Button
            variant={activeTab === 'info' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => handleTabChange('info')}
            className="rounded-none border-0"
          >
            <IconEye className="mr-2 h-4 w-4" />
            Info
          </Button>
          {isPreviewable && (
            <Button
              variant={activeTab === 'preview' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => handleTabChange('preview')}
              className="rounded-none border-0"
            >
              <IconFileTypePdf className="mr-2 h-4 w-4" />
              Preview
            </Button>
          )}
          <Button
            variant={activeTab === 'content' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => handleTabChange('content')}
            className="rounded-none border-0"
          >
            <IconFileText className="mr-2 h-4 w-4" />
            Content
          </Button>
          <Button
            variant={activeTab === 'summary' ? 'default' : 'ghost'}
            size="sm"
            onClick={() => handleTabChange('summary')}
            className="rounded-none border-0"
          >
            <IconFile className="mr-2 h-4 w-4" />
            Summary
          </Button>
        </div>

        <div className="flex-1 overflow-hidden min-h-[300px]">
          <ScrollArea className="h-full">
            <div className="p-4">
              {/* Info Tab */}
              {activeTab === 'info' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-sm">
                        <IconFile className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium">Filename:</span>
                      </div>
                      <p className="text-sm text-muted-foreground pl-6">
                        {document.filename}
                      </p>
                    </div>
                    
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-sm">
                        <IconClock className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium">Created:</span>
                      </div>
                      <p className="text-sm text-muted-foreground pl-6">
                        {new Date(document.created_at).toLocaleString()}
                      </p>
                    </div>
                  </div>

                  {document.description && (
                    <>
                      <Separator />
                      <div className="space-y-2">
                        <h4 className="font-medium">Description</h4>
                        <p className="text-sm text-muted-foreground">
                          {document.description}
                        </p>
                      </div>
                    </>
                  )}

                  {document.category && (
                    <>
                      <Separator />
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <IconFolder className="h-4 w-4 text-muted-foreground" />
                          <span className="font-medium">Category:</span>
                        </div>
                        <Badge variant="outline">{document.category}</Badge>
                      </div>
                    </>
                  )}

                  {document.tags && document.tags.length > 0 && (
                    <>
                      <Separator />
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <IconTag className="h-4 w-4 text-muted-foreground" />
                          <span className="font-medium">Tags:</span>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {document.tags.map((tag) => (
                            <Badge key={tag} variant="outline" className="text-xs">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </>
                  )}

                  <Separator />
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <IconUser className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">Created by:</span>
                    </div>
                    <p className="text-sm text-muted-foreground pl-6">
                      {typeof document.created_by === 'object' && document.created_by !== null
                        ? document.created_by.full_name || document.created_by.email
                        : document.created_by}
                    </p>
                  </div>
                </div>
              )}

              {/* Preview Tab */}
              {activeTab === 'preview' && isPreviewable && (
                <div className="h-full min-h-[400px]">
                  {console.log('[DocumentViewerDialog] Rendering preview tab:', { loadingPdf, pdfError, pdfUrl: !!pdfUrl })}

                  {loadingPdf && (
                    <div className="flex items-center justify-center py-8">
                      <IconLoader2 className="h-6 w-6 animate-spin mr-2" />
                      <span>Cargando PDF...</span>
                    </div>
                  )}

                  {pdfError && (
                    <div className="text-center py-8">
                      <p className="text-red-600 mb-4">{pdfError}</p>
                      <Button onClick={handleLoadPdf} variant="outline" size="sm">
                        Reintentar
                      </Button>
                    </div>
                  )}

                  {pdfUrl && !loadingPdf && (
                    <PDFViewer
                      url={pdfUrl}
                      fileName={document.filename}
                      height="400px"
                    />
                  )}

                  {!loadingPdf && !pdfError && !pdfUrl && (
                    <div className="text-center py-8 text-muted-foreground">
                      No hay PDF cargado. Estado inconsistente.
                    </div>
                  )}
                </div>
              )}

              {/* Content Tab */}
              {activeTab === 'content' && (
                <div className="space-y-4">
                  {loadingContent && (
                    <div className="flex items-center justify-center py-8">
                      <IconLoader2 className="h-6 w-6 animate-spin mr-2" />
                      <span>Loading content...</span>
                    </div>
                  )}

                  {contentError && (
                    <div className="text-center py-8">
                      <p className="text-red-600 mb-4">{contentError}</p>
                      <Button onClick={handleLoadContent} variant="outline" size="sm">
                        Try Again
                      </Button>
                    </div>
                  )}

                  {content && !loadingContent && (
                    <div className="bg-muted/50 p-4 rounded-lg">
                      <pre className="whitespace-pre-wrap text-sm font-mono">
                        {content}
                      </pre>
                    </div>
                  )}
                </div>
              )}

              {/* Summary Tab */}
              {activeTab === 'summary' && (
                <div className="space-y-4">
                  {loadingSummary && (
                    <div className="flex items-center justify-center py-8">
                      <IconLoader2 className="h-6 w-6 animate-spin mr-2" />
                      <span>Loading summary...</span>
                    </div>
                  )}

                  {summaryError && (
                    <div className="text-center py-8">
                      <p className="text-red-600 mb-4">{summaryError}</p>
                      <Button onClick={handleLoadSummary} variant="outline" size="sm">
                        Try Again
                      </Button>
                    </div>
                  )}

                  {summary && !loadingSummary && (
                    <div className="bg-muted/50 p-4 rounded-lg">
                      <p className="text-sm leading-relaxed">{summary}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  )
}
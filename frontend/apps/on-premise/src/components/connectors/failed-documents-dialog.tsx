'use client'

/**
 * Failed Documents Dialog for Emma On-Premise
 *
 * Shows failed documents with error breakdown, preview links, and retry options.
 */

import { useState, useEffect } from 'react'
import {
  IconAlertTriangle,
  IconLoader2,
  IconAlertCircle,
  IconCheck,
  IconFileText,
  IconRefresh,
  IconExternalLink,
  IconPlayerPlay,
  IconFilter,
  IconX,
  IconChevronDown,
  IconChevronUp,
} from '@tabler/icons-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Badge,
  Button,
  Separator,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  ScrollArea,
} from '@nexus/shared/ui'
import {
  Connector,
  FailedDocument,
  ErrorBreakdown,
  connectorService,
  connectorNames,
} from '@/lib/services/connector.service'

interface FailedDocumentsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  connector: Connector | null
  onRetryComplete?: () => void
}

export function FailedDocumentsDialog({
  open,
  onOpenChange,
  connector,
  onRetryComplete,
}: FailedDocumentsDialogProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [isRetrying, setIsRetrying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Data
  const [failedDocs, setFailedDocs] = useState<FailedDocument[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [errorBreakdown, setErrorBreakdown] = useState<ErrorBreakdown[]>([])

  // Filters
  const [selectedErrorFilter, setSelectedErrorFilter] = useState<string | null>(null)
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set())

  // UI state
  const [showErrorBreakdown, setShowErrorBreakdown] = useState(true)

  useEffect(() => {
    if (open && connector) {
      setError(null)
      setSuccessMessage(null)
      setSelectedErrorFilter(null)
      setSelectedDocIds(new Set())
      loadData()
    }
  }, [open, connector])

  useEffect(() => {
    if (open && connector) {
      loadFailedDocuments()
    }
  }, [selectedErrorFilter])

  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [successMessage])

  const loadData = async () => {
    if (!connector) return
    setIsLoading(true)
    setError(null)

    try {
      // Load stats for error breakdown
      const statsResult = await connectorService.getConnectorStats(connector.id)
      if (statsResult.data) {
        setErrorBreakdown(statsResult.data.documents.errors_by_type || [])
      }

      // Load failed documents
      await loadFailedDocuments()
    } catch (err: any) {
      setError(err.message || 'Error al cargar datos')
    } finally {
      setIsLoading(false)
    }
  }

  const loadFailedDocuments = async () => {
    if (!connector) return

    try {
      const result = await connectorService.getFailedDocuments(connector.id, {
        limit: 50,
        error_filter: selectedErrorFilter || undefined,
      })
      if (result.data) {
        setFailedDocs(result.data.items)
        setTotalCount(result.data.total_count)
      } else if (result.error) {
        setError(result.error)
      }
    } catch (err: any) {
      setError(err.message || 'Error al cargar documentos fallidos')
    }
  }

  const handleRetryAll = async () => {
    if (!connector) return
    setIsRetrying(true)
    setError(null)
    setSuccessMessage(null)

    try {
      const result = await connectorService.retryFailedDocuments(connector.id, {
        error_filter: selectedErrorFilter || undefined,
      })
      if (result.error) {
        setError(result.error)
      } else if (result.data) {
        setSuccessMessage(`${result.data.reset_count} documentos marcados para reintentar`)
        setSelectedDocIds(new Set())
        setTimeout(() => {
          loadData()
          onRetryComplete?.()
        }, 2000)
      }
    } catch (err: any) {
      setError(err.message || 'Error al reintentar')
    } finally {
      setIsRetrying(false)
    }
  }

  const handleRetrySelected = async () => {
    if (!connector || selectedDocIds.size === 0) return
    setIsRetrying(true)
    setError(null)
    setSuccessMessage(null)

    try {
      const result = await connectorService.retryFailedDocuments(connector.id, {
        document_ids: Array.from(selectedDocIds),
      })
      if (result.error) {
        setError(result.error)
      } else if (result.data) {
        setSuccessMessage(`${result.data.reset_count} documentos marcados para reintentar`)
        setSelectedDocIds(new Set())
        setTimeout(() => {
          loadData()
          onRetryComplete?.()
        }, 2000)
      }
    } catch (err: any) {
      setError(err.message || 'Error al reintentar')
    } finally {
      setIsRetrying(false)
    }
  }

  const handleRetryByErrorType = async (errorType: string) => {
    if (!connector) return
    setIsRetrying(true)
    setError(null)
    setSuccessMessage(null)

    try {
      const result = await connectorService.retryFailedDocuments(connector.id, {
        error_filter: errorType,
      })
      if (result.error) {
        setError(result.error)
      } else if (result.data) {
        setSuccessMessage(`${result.data.reset_count} documentos marcados para reintentar`)
        setTimeout(() => {
          loadData()
          onRetryComplete?.()
        }, 2000)
      }
    } catch (err: any) {
      setError(err.message || 'Error al reintentar')
    } finally {
      setIsRetrying(false)
    }
  }

  const toggleDocSelection = (docId: string) => {
    const newSelection = new Set(selectedDocIds)
    if (newSelection.has(docId)) {
      newSelection.delete(docId)
    } else {
      newSelection.add(docId)
    }
    setSelectedDocIds(newSelection)
  }

  const toggleSelectAll = () => {
    if (selectedDocIds.size === failedDocs.length) {
      setSelectedDocIds(new Set())
    } else {
      setSelectedDocIds(new Set(failedDocs.map(d => d.id)))
    }
  }

  const getErrorShortName = (error: string): string => {
    // Extract key phrase from error message
    if (error.includes('No text content')) return 'Sin texto'
    if (error.includes('Unsupported extension')) return 'Extensión inválida'
    if (error.includes('timeout')) return 'Timeout'
    if (error.includes('connection')) return 'Conexión'
    if (error.includes('OCR')) return 'OCR fallido'
    if (error.includes('password')) return 'Protegido'
    if (error.includes('corrupt')) return 'Corrupto'
    // Truncate long errors
    return error.length > 30 ? error.substring(0, 30) + '...' : error
  }

  if (!connector) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="overflow-hidden flex flex-col"
        style={{ width: '700px', maxWidth: '90vw', maxHeight: '85vh' }}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <IconAlertTriangle className="h-5 w-5 text-red-500" />
            Documentos Fallidos
          </DialogTitle>
          <DialogDescription>
            {connector.name} ({connectorNames[connector.connector_type]}) — {totalCount} documentos con errores
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-hidden flex flex-col space-y-4">
          {/* Message area */}
          <div className="min-h-[40px]">
            {error && (
              <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 dark:bg-red-950/30 px-3 py-2 rounded">
                <IconAlertCircle className="h-4 w-4 flex-shrink-0" />
                <span className="truncate">{error}</span>
              </div>
            )}
            {successMessage && !error && (
              <div className="flex items-center gap-2 text-sm text-green-600 bg-green-50 dark:bg-green-950/30 px-3 py-2 rounded">
                <IconCheck className="h-4 w-4 flex-shrink-0" />
                <span className="truncate">{successMessage}</span>
              </div>
            )}
          </div>

          {/* Error Breakdown Section */}
          <div className="rounded border bg-muted/20">
            <button
              className="w-full flex items-center justify-between p-3 text-sm font-medium hover:bg-muted/30 transition-colors"
              onClick={() => setShowErrorBreakdown(!showErrorBreakdown)}
            >
              <span className="flex items-center gap-2">
                <IconFilter className="h-4 w-4" />
                Errores por Tipo
                <Badge variant="secondary" className="ml-1">{errorBreakdown.length}</Badge>
              </span>
              {showErrorBreakdown ? (
                <IconChevronUp className="h-4 w-4" />
              ) : (
                <IconChevronDown className="h-4 w-4" />
              )}
            </button>

            {showErrorBreakdown && errorBreakdown.length > 0 && (
              <div className="px-3 pb-3 space-y-2">
                <Separator />
                <div className="grid gap-2 max-h-[120px] overflow-y-auto">
                  {errorBreakdown.map((eb, idx) => (
                    <div
                      key={idx}
                      className={`flex items-center justify-between p-2 rounded text-xs transition-colors cursor-pointer ${
                        selectedErrorFilter === eb.error
                          ? 'bg-primary/10 border border-primary/30'
                          : 'bg-muted/30 hover:bg-muted/50'
                      }`}
                      onClick={() => setSelectedErrorFilter(
                        selectedErrorFilter === eb.error ? null : eb.error
                      )}
                    >
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <Badge
                          variant="destructive"
                          className="text-[10px] px-1.5 flex-shrink-0"
                        >
                          {eb.count}
                        </Badge>
                        <span className="truncate text-muted-foreground" title={eb.error}>
                          {getErrorShortName(eb.error)}
                        </span>
                      </div>
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 w-6 p-0 flex-shrink-0"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleRetryByErrorType(eb.error)
                              }}
                              disabled={isRetrying}
                            >
                              {isRetrying ? (
                                <IconLoader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <IconRefresh className="h-3 w-3" />
                              )}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            <p>Reintentar todos de este tipo</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Active Filter Badge */}
          {selectedErrorFilter && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">Filtro activo:</span>
              <Badge variant="outline" className="flex items-center gap-1">
                {getErrorShortName(selectedErrorFilter)}
                <button
                  className="ml-1 hover:text-destructive"
                  onClick={() => setSelectedErrorFilter(null)}
                >
                  <IconX className="h-3 w-3" />
                </button>
              </Badge>
            </div>
          )}

          <Separator />

          {/* Failed Documents List */}
          <div className="flex-1 min-h-0 flex flex-col">
            {/* List Header */}
            <div className="flex items-center justify-between pb-2">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-gray-300"
                  checked={failedDocs.length > 0 && selectedDocIds.size === failedDocs.length}
                  onChange={toggleSelectAll}
                  disabled={failedDocs.length === 0}
                />
                <span className="text-xs text-muted-foreground">
                  {selectedDocIds.size > 0
                    ? `${selectedDocIds.size} seleccionados`
                    : `${failedDocs.length} documentos`
                  }
                </span>
              </div>
              {selectedDocIds.size > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={handleRetrySelected}
                  disabled={isRetrying}
                >
                  {isRetrying ? (
                    <IconLoader2 className="h-3 w-3 animate-spin mr-1" />
                  ) : (
                    <IconPlayerPlay className="h-3 w-3 mr-1" />
                  )}
                  Reintentar Seleccionados
                </Button>
              )}
            </div>

            {/* Document List */}
            <ScrollArea className="flex-1 rounded border">
              <div className="p-2 space-y-1">
                {isLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <IconLoader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : failedDocs.length === 0 ? (
                  <div className="text-center py-8 text-sm text-muted-foreground">
                    {selectedErrorFilter
                      ? 'No hay documentos con este tipo de error'
                      : 'No hay documentos fallidos'
                    }
                  </div>
                ) : (
                  failedDocs.map((doc) => (
                    <div
                      key={doc.id}
                      className={`flex items-start gap-2 p-2 rounded text-xs transition-colors ${
                        selectedDocIds.has(doc.id)
                          ? 'bg-primary/10'
                          : 'hover:bg-muted/50'
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-gray-300 mt-0.5"
                        checked={selectedDocIds.has(doc.id)}
                        onChange={() => toggleDocSelection(doc.id)}
                      />
                      <IconFileText className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium truncate" title={doc.title}>
                            {doc.title}
                          </span>
                          {doc.file_extension && (
                            <Badge variant="outline" className="text-[10px] px-1 flex-shrink-0">
                              {doc.file_extension}
                            </Badge>
                          )}
                        </div>
                        <div className="text-muted-foreground mt-0.5 truncate" title={doc.indexing_error || ''}>
                          {doc.indexing_error || 'Error desconocido'}
                        </div>
                        {doc.external_path && (
                          <div className="text-muted-foreground/70 mt-0.5 truncate text-[10px]" title={doc.external_path}>
                            {doc.external_path}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        {doc.external_url && doc.actions.can_preview && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <a
                                  href={doc.external_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="p-1 rounded hover:bg-muted"
                                >
                                  <IconExternalLink className="h-3.5 w-3.5 text-blue-500" />
                                </a>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>Abrir en origen</p>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </ScrollArea>
          </div>
        </div>

        <DialogFooter className="gap-2 mt-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={loadData}
            disabled={isLoading}
          >
            <IconRefresh className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={handleRetryAll}
            disabled={isRetrying || totalCount === 0}
          >
            {isRetrying ? (
              <IconLoader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <IconPlayerPlay className="h-4 w-4 mr-2" />
            )}
            Reintentar Todos {selectedErrorFilter ? '(filtrados)' : `(${totalCount})`}
          </Button>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

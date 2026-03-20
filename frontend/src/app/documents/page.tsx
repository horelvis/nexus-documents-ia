'use client'

/**
 * Synchronized Documents Page
 *
 * Displays all documents indexed from connectors with search, filtering,
 * and server-side pagination. Documents can be opened in their source
 * (Google Drive, OneDrive, etc.) via external_url.
 */

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  IconFileText,
  IconLoader2,
  IconRefresh,
  IconSearch,
  IconExternalLink,
  IconPlug,
} from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
  Button,
  Badge,
  Input,
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui'
import { useAuth } from '@/contexts/auth-context'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import {
  connectorService,
  connectorNames,
  IndexedDocument,
  Connector,
  ConnectorType,
} from '@/lib/services/connector.service'
import { ConnectorIcon } from '@/components/connectors'
import {
  getFileIcon,
  formatFileSize,
  getStatusBadgeConfig,
  formatDate,
} from '@/lib/document-utils'

// ============================================================================
// Main Page Component
// ============================================================================

export default function DocumentsPage() {
  const { isLoaded, isAuthenticated } = useAuth()

  // Documents data
  const [documents, setDocuments] = useState<IndexedDocument[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [page, setPage] = useState(1)
  const pageSize = 20

  // Filters
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [connectorFilter, setConnectorFilter] = useState<string>('all')

  // Connectors lookup
  const [connectors, setConnectors] = useState<Connector[]>([])

  // Loading state
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // ── Load connectors once for the filter dropdown + name lookup ──────────
  useEffect(() => {
    async function loadConnectors() {
      const response = await connectorService.getConnectors()
      if (response.data) {
        setConnectors(response.data.items || [])
      }
    }
    if (isLoaded && isAuthenticated) {
      loadConnectors()
    }
  }, [isLoaded, isAuthenticated])

  // ── Load documents when page/filters change ─────────────────────────────
  useEffect(() => {
    if (isLoaded && isAuthenticated) {
      loadDocuments()
    }
  }, [page, statusFilter, connectorFilter, isLoaded, isAuthenticated])

  async function loadDocuments() {
    setIsLoading(true)
    setError(null)
    try {
      const params: {
        page: number
        page_size: number
        search?: string
        status?: string
        connector_id?: string
      } = {
        page,
        page_size: pageSize,
      }

      if (searchQuery.trim()) {
        params.search = searchQuery.trim()
      }
      if (statusFilter !== 'all') {
        params.status = statusFilter
      }
      if (connectorFilter !== 'all') {
        params.connector_id = connectorFilter
      }

      const response = await connectorService.getIndexedDocuments(params)
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setDocuments(response.data.items)
        setTotal(response.data.total)
        setTotalPages(response.data.total_pages)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al cargar documentos')
    } finally {
      setIsLoading(false)
    }
  }

  // ── Manual search (button / Enter key) ──────────────────────────────────
  function handleSearch() {
    setPage(1)
    loadDocuments()
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  // ── Connector name lookup ───────────────────────────────────────────────
  function getConnectorName(connectorId: string | null): string {
    if (!connectorId) return '—'
    const connector = connectors.find(c => c.id === connectorId)
    if (!connector) return '—'
    return connector.name
  }

  function getConnectorType(connectorId: string | null): ConnectorType | null {
    if (!connectorId) return null
    const connector = connectors.find(c => c.id === connectorId)
    return connector?.connector_type || null
  }

  // ── Auth guard ──────────────────────────────────────────────────────────
  if (!isLoaded) {
    return (
      <div className="flex h-screen items-center justify-center">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <nav className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/" className="hover:text-foreground transition-colors">Inicio</Link>
            <span>/</span>
            <span className="text-foreground font-medium">Documentos</span>
          </nav>
        </PageHeader>

        <main className="flex-1 overflow-auto p-4 md:p-6">
          <div className="space-y-6">
            {/* Title + Refresh */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-semibold flex items-center gap-2">
                  <IconFileText className="h-6 w-6" />
                  Documentos Sincronizados
                </h1>
                <p className="text-sm text-muted-foreground mt-1">
                  Documentos indexados desde tus conectores
                </p>
              </div>
              <div className="flex items-center gap-2">
                {!isLoading && (
                  <Badge variant="secondary">{total} documentos</Badge>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => loadDocuments()}
                  disabled={isLoading}
                >
                  <IconRefresh className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                </Button>
              </div>
            </div>

            {/* Toolbar: search + filters */}
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="flex flex-1 gap-2">
                <Input
                  placeholder="Buscar por nombre..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className="max-w-sm"
                />
                <Button variant="outline" size="sm" onClick={handleSearch}>
                  <IconSearch className="h-4 w-4 mr-1" />
                  Buscar
                </Button>
              </div>

              <div className="flex gap-2">
                <Select
                  value={statusFilter}
                  onValueChange={(value) => { setStatusFilter(value); setPage(1) }}
                >
                  <SelectTrigger size="sm">
                    <SelectValue placeholder="Estado" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos los estados</SelectItem>
                    <SelectItem value="indexed">Indexado</SelectItem>
                    <SelectItem value="pending">Pendiente</SelectItem>
                    <SelectItem value="processing">Procesando</SelectItem>
                    <SelectItem value="failed">Error</SelectItem>
                  </SelectContent>
                </Select>

                <Select
                  value={connectorFilter}
                  onValueChange={(value) => { setConnectorFilter(value); setPage(1) }}
                >
                  <SelectTrigger size="sm">
                    <SelectValue placeholder="Conector" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos los conectores</SelectItem>
                    {connectors.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            {/* Table */}
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : documents.length === 0 && total === 0 && !searchQuery && statusFilter === 'all' && connectorFilter === 'all' ? (
              /* Empty state — no documents at all */
              <div className="text-center py-16">
                <IconFileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
                <p className="text-muted-foreground mb-2">No hay documentos sincronizados</p>
                <p className="text-sm text-muted-foreground mb-4">
                  Configura un conector para empezar a indexar documentos
                </p>
                <Button asChild variant="outline">
                  <Link href="/connectors">
                    <IconPlug className="h-4 w-4 mr-2" />
                    Ir a Conectores
                  </Link>
                </Button>
              </div>
            ) : documents.length === 0 ? (
              /* No results for current filters */
              <div className="text-center py-12">
                <IconSearch className="h-10 w-10 mx-auto mb-3 text-muted-foreground opacity-50" />
                <p className="text-muted-foreground">No se encontraron documentos con los filtros actuales</p>
              </div>
            ) : (
              <>
                <div className="rounded-md border pr-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10"></TableHead>
                      <TableHead>Nombre</TableHead>
                      <TableHead className="hidden lg:table-cell">Ruta</TableHead>
                      <TableHead className="hidden md:table-cell">Conector</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead className="hidden sm:table-cell">Tamaño</TableHead>
                      <TableHead className="hidden sm:table-cell">Fecha</TableHead>
                      <TableHead className="w-10"></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documents.map((doc) => {
                      const statusConfig = getStatusBadgeConfig(doc.indexing_status)
                      const cType = getConnectorType(doc.connector_id)

                      return (
                        <TableRow key={doc.id}>
                          {/* Icon */}
                          <TableCell>
                            {getFileIcon(doc.mime_type, doc.file_extension, 'sm')}
                          </TableCell>

                          {/* Name */}
                          <TableCell>
                            <span className="font-medium line-clamp-1" title={doc.title}>
                              {doc.title}
                            </span>
                          </TableCell>

                          {/* Path */}
                          <TableCell className="hidden lg:table-cell">
                            <span className="text-muted-foreground text-xs line-clamp-1" title={doc.external_path || ''}>
                              {doc.external_path || '—'}
                            </span>
                          </TableCell>

                          {/* Connector */}
                          <TableCell className="hidden md:table-cell">
                            <div className="flex items-center gap-1.5">
                              {cType && <ConnectorIcon type={cType} size="sm" />}
                              <span className="text-xs text-muted-foreground">
                                {getConnectorName(doc.connector_id)}
                              </span>
                            </div>
                          </TableCell>

                          {/* Status */}
                          <TableCell>
                            <Badge variant={statusConfig.variant} className="text-xs">
                              {statusConfig.label}
                            </Badge>
                          </TableCell>

                          {/* Size */}
                          <TableCell className="hidden sm:table-cell text-xs text-muted-foreground">
                            {formatFileSize(doc.size_bytes)}
                          </TableCell>

                          {/* Date */}
                          <TableCell className="hidden sm:table-cell text-xs text-muted-foreground">
                            {formatDate(doc.source_modified_at || doc.indexed_at)}
                          </TableCell>

                          {/* Actions */}
                          <TableCell>
                            {doc.external_url ? (
                              <a
                                href={doc.external_url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                <Button variant="ghost" size="sm">
                                  <IconExternalLink className="h-4 w-4" />
                                </Button>
                              </a>
                            ) : (
                              <Button variant="ghost" size="sm" disabled>
                                <IconExternalLink className="h-4 w-4 opacity-30" />
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between pt-2">
                    <span className="text-sm text-muted-foreground">
                      Página {page} de {totalPages}
                    </span>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPage(p => Math.max(1, p - 1))}
                        disabled={page <= 1}
                      >
                        Anterior
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                        disabled={page >= totalPages}
                      >
                        Siguiente
                      </Button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

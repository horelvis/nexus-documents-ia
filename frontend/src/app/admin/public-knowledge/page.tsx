"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  IconDatabase,
  IconSearch,
  IconLoader2,
  IconAlertCircle,
  IconScale,
  IconGavel,
  IconFileText,
  IconWorld,
  IconBuilding,
  IconRefresh,
  IconX,
  IconHistory,
  IconExternalLink,
  IconVersions,
  IconCircleCheck,
  IconClock,
  IconChevronLeft,
  IconBrain,
} from "@tabler/icons-react"
import {
  SidebarProvider,
  SidebarInset,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Alert,
  AlertDescription,
} from "@/components/ui"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Input } from "@/components/ui/input"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useApiClient } from "@/lib/api-client"
import { useAuth } from "@/contexts/auth-context"
import { AppSidebar } from "@/components/layout/app-sidebar"
import { PageHeader } from '@/components/layout/page-header'

interface PublicKnowledgeStats {
  total_documents: number
  verified_count: number
  documents_by_category: Record<string, number>
  documents_by_jurisdiction: Record<string, number>
  last_updated: string
  current_versions_count?: number
  total_content_size_kb?: number
}

interface PublicDocument {
  id: string
  title: string
  category: string
  jurisdiction: string
  legal_reference?: string
  verified: boolean
  created_at: string
  similarity_score?: number
  version_number?: number
  is_current_version?: boolean
  legal_status?: string
  modification_type?: string
  consolidation_date?: string
  modifying_laws?: string[]
  boe_id?: string
  eli_uri?: string
}

interface SearchResult {
  query: string
  total_results: number
  search_time_ms: number
  results: PublicDocument[]
}

const CATEGORY_LABELS: Record<string, string> = {
  legislation: "Legislación",
  regulation: "Regulación",
  jurisprudence: "Jurisprudencia",
  template: "Plantilla",
  guideline: "Directriz",
  reference: "Referencia",
  form: "Formulario",
  treaty: "Tratado"
}

const JURISDICTION_LABELS: Record<string, string> = {
  es: "España",
  eu: "Unión Europea",
  int: "Internacional",
  regional: "Autonómico"
}

export default function PublicKnowledgePage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const router = useRouter()
  const apiClient = useApiClient()

  const [stats, setStats] = useState<PublicKnowledgeStats | null>(null)
  const [searchResults, setSearchResults] = useState<SearchResult | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [isLoading, setIsLoading] = useState(true)
  const [isSearching, setIsSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [enabledCategories, setEnabledCategories] = useState<Record<string, boolean>>({
    legislation: true,
    regulation: true,
    jurisprudence: true,
    template: true,
    guideline: true,
    reference: true,
    form: false,
    treaty: true
  })

  useEffect(() => {
    if (isLoaded && isAuthenticated) {
      loadStats()
    }
  }, [isLoaded, isAuthenticated])

  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push('/auth/sign-in')
    }
  }, [isLoaded, isAuthenticated, router])

  const loadStats = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await apiClient.get<PublicKnowledgeStats>('/weaviate/public-knowledge/stats')

      if (response.error) {
        throw new Error(response.error)
      }

      setStats(response.data || null)
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error al cargar estadísticas'
      setError(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) return

    setIsSearching(true)
    setError(null)

    try {
      const enabledCats = Object.entries(enabledCategories)
        .filter(([, enabled]) => enabled)
        .map(([cat]) => cat)

      const response = await apiClient.post<SearchResult>('/weaviate/public-knowledge/search', {
        query: searchQuery,
        limit: 20,
        categories: enabledCats.length > 0 ? enabledCats : undefined,
        search_type: 'hybrid'
      })

      if (response.error) {
        throw new Error(response.error)
      }

      setSearchResults(response.data || null)
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Error en la búsqueda'
      setError(errorMessage)
    } finally {
      setIsSearching(false)
    }
  }

  const toggleCategory = (category: string) => {
    setEnabledCategories(prev => ({
      ...prev,
      [category]: !prev[category]
    }))
  }

  const getCategoryIcon = (category: string) => {
    const icons: Record<string, React.ReactNode> = {
      legislation: <IconScale className="h-4 w-4" />,
      regulation: <IconBuilding className="h-4 w-4" />,
      jurisprudence: <IconGavel className="h-4 w-4" />,
      template: <IconFileText className="h-4 w-4" />,
      guideline: <IconFileText className="h-4 w-4" />,
      reference: <IconFileText className="h-4 w-4" />,
      form: <IconFileText className="h-4 w-4" />,
      treaty: <IconWorld className="h-4 w-4" />
    }
    return icons[category] || <IconFileText className="h-4 w-4" />
  }

  const getJurisdictionLabel = (jurisdiction: string) => {
    return JURISDICTION_LABELS[jurisdiction] || jurisdiction.toUpperCase()
  }

  const getCategoryLabel = (category: string) => {
    return CATEGORY_LABELS[category] || category
  }

  const getLegalStatusBadge = (status?: string) => {
    const statusConfig: Record<string, { color: string; label: string }> = {
      vigente: { color: 'bg-green-100 text-green-800', label: 'Vigente' },
      derogada: { color: 'bg-red-100 text-red-800', label: 'Derogada' },
      parcialmente_derogada: { color: 'bg-yellow-100 text-yellow-800', label: 'Parcialmente derogada' },
      pendiente: { color: 'bg-blue-100 text-blue-800', label: 'Pendiente' }
    }
    const config = statusConfig[status || 'vigente'] || statusConfig.vigente
    return (
      <Badge className={`${config.color} border-0`}>
        {config.label}
      </Badge>
    )
  }

  const getModificationTypeBadge = (type?: string) => {
    const typeConfig: Record<string, { icon: React.ReactNode; label: string }> = {
      original: { icon: <IconCircleCheck className="h-3 w-3" />, label: 'Original' },
      modificacion: { icon: <IconHistory className="h-3 w-3" />, label: 'Modificación' },
      correccion: { icon: <IconRefresh className="h-3 w-3" />, label: 'Corrección' },
      derogacion_parcial: { icon: <IconX className="h-3 w-3" />, label: 'Derogación parcial' },
      refundido: { icon: <IconVersions className="h-3 w-3" />, label: 'Texto refundido' }
    }
    const config = typeConfig[type || 'original'] || typeConfig.original
    return (
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        {config.icon}
        {config.label}
      </span>
    )
  }

  const formatConsolidationDate = (dateStr?: string) => {
    if (!dateStr) return null
    try {
      const date = new Date(dateStr)
      return date.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' })
    } catch {
      return null
    }
  }

  // Loading state
  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  // Not authenticated - redirect handled by useEffect
  if (!isAuthenticated) {
    return null
  }

  return (
    <SidebarProvider>
      <AppSidebar variant="inset" />

      <SidebarInset>
        {/* Header */}
        <PageHeader>
          <Link href="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground">
            <IconChevronLeft className="h-4 w-4" />
            <IconBrain className="h-5 w-5 text-primary" />
            <span className="font-semibold text-foreground">Emma</span>
          </Link>
          <div className="h-4 w-px bg-border" />
          <IconDatabase className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">Base de Conocimiento</span>
        </PageHeader>

        {/* Main Content */}
        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-6xl mx-auto space-y-6">
            {/* Title */}
            <div>
              <h1 className="text-2xl font-bold">Base de Conocimiento Público</h1>
              <p className="text-muted-foreground">
                Legislación, normativa y jurisprudencia indexada para consultas de Emma AI
              </p>
            </div>

            {/* Info Notice */}
            <Alert>
              <IconDatabase className="h-4 w-4" />
              <AlertDescription>
                Esta base de conocimiento contiene documentos públicos verificados (BOE, DOUE, jurisprudencia)
                que Emma utiliza para fundamentar sus respuestas legales.
              </AlertDescription>
            </Alert>

            {/* Statistics Card */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Estadísticas</CardTitle>
                    <CardDescription>
                      Resumen del contenido indexado
                    </CardDescription>
                  </div>
                  <Button variant="outline" onClick={loadStats} disabled={isLoading}>
                    <IconRefresh className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                    Actualizar
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <IconLoader2 className="h-6 w-6 animate-spin" />
                    <span className="ml-2">Cargando...</span>
                  </div>
                ) : error && !stats ? (
                  <Alert variant="destructive">
                    <IconAlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                ) : stats ? (
                  <div className="grid gap-4 md:grid-cols-4">
                    <div className="rounded-lg border p-4">
                      <div className="text-2xl font-bold">{stats.total_documents}</div>
                      <div className="text-sm text-muted-foreground">Documentos totales</div>
                    </div>
                    <div className="rounded-lg border p-4">
                      <div className="text-2xl font-bold">{stats.verified_count}</div>
                      <div className="text-sm text-muted-foreground">Documentos verificados</div>
                    </div>
                    <div className="rounded-lg border p-4">
                      <div className="text-2xl font-bold">{Object.keys(stats.documents_by_category).length}</div>
                      <div className="text-sm text-muted-foreground">Categorías</div>
                    </div>
                    <div className="rounded-lg border p-4">
                      <div className="text-2xl font-bold">{Object.keys(stats.documents_by_jurisdiction).length}</div>
                      <div className="text-sm text-muted-foreground">Jurisdicciones</div>
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>

            {/* Category Selection */}
            <Card>
              <CardHeader>
                <CardTitle>Categorías habilitadas</CardTitle>
                <CardDescription>
                  Selecciona qué tipos de documentos incluir en las búsquedas
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-4">
                  {Object.entries(enabledCategories).map(([category, enabled]) => (
                    <div key={category} className="flex items-center justify-between rounded-lg border p-3">
                      <div className="flex items-center gap-2">
                        {getCategoryIcon(category)}
                        <span className="text-sm font-medium">{getCategoryLabel(category)}</span>
                      </div>
                      <Switch
                        checked={enabled}
                        onCheckedChange={() => toggleCategory(category)}
                      />
                    </div>
                  ))}
                </div>
                {stats && stats.documents_by_category && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {Object.entries(stats.documents_by_category).map(([category, count]) => (
                      <Badge
                        key={category}
                        variant={enabledCategories[category] ? "default" : "outline"}
                        className="cursor-pointer"
                        onClick={() => toggleCategory(category)}
                      >
                        {getCategoryLabel(category)}: {count}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Search */}
            <Card>
              <CardHeader>
                <CardTitle>Buscar en la base de conocimiento</CardTitle>
                <CardDescription>
                  Busca leyes, normativas o jurisprudencia por texto o referencia
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex gap-2">
                  <Input
                    placeholder="Ej: protección de datos, LOPDGDD, artículo 89..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                    className="flex-1"
                  />
                  <Button onClick={handleSearch} disabled={isSearching || !searchQuery.trim()}>
                    {isSearching ? (
                      <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <IconSearch className="mr-2 h-4 w-4" />
                    )}
                    Buscar
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Search Results */}
            {searchResults && (
              <Card>
                <CardHeader>
                  <CardTitle>
                    {searchResults.total_results} resultados encontrados
                  </CardTitle>
                  <CardDescription>
                    Tiempo de búsqueda: {searchResults.search_time_ms}ms
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {searchResults.results.length === 0 ? (
                    <div className="text-center py-8">
                      <IconSearch className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                      <p className="text-muted-foreground">
                        No se encontraron resultados para tu búsqueda
                      </p>
                    </div>
                  ) : (
                    <TooltipProvider>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Título</TableHead>
                            <TableHead>Categoría</TableHead>
                            <TableHead>Jurisdicción</TableHead>
                            <TableHead>Referencia</TableHead>
                            <TableHead>Estado</TableHead>
                            <TableHead>Versión</TableHead>
                            <TableHead>Relevancia</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {searchResults.results.map((doc) => (
                            <TableRow key={doc.id}>
                              <TableCell className="max-w-sm">
                                <div className="flex flex-col gap-1">
                                  <span className="font-medium line-clamp-2">{doc.title}</span>
                                  {doc.modifying_laws && doc.modifying_laws.length > 0 && (
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <span className="text-xs text-muted-foreground cursor-help flex items-center gap-1">
                                          <IconHistory className="h-3 w-3" />
                                          {doc.modifying_laws.length} modificaciones
                                        </span>
                                      </TooltipTrigger>
                                      <TooltipContent className="max-w-sm">
                                        <p className="font-medium mb-1">Modificada por:</p>
                                        <ul className="text-xs space-y-1">
                                          {doc.modifying_laws.map((law, i) => (
                                            <li key={i}>• {law}</li>
                                          ))}
                                        </ul>
                                      </TooltipContent>
                                    </Tooltip>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline">
                                  <span className="mr-1">{getCategoryIcon(doc.category)}</span>
                                  {getCategoryLabel(doc.category)}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Badge variant="secondary">
                                  {getJurisdictionLabel(doc.jurisdiction)}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <div className="flex flex-col gap-1">
                                  <span className="text-sm font-mono">
                                    {doc.boe_id || doc.legal_reference || '-'}
                                  </span>
                                  {doc.eli_uri && (
                                    <a
                                      href={doc.eli_uri}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                                    >
                                      <IconExternalLink className="h-3 w-3" />
                                      BOE
                                    </a>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell>
                                <div className="flex flex-col gap-1">
                                  {getLegalStatusBadge(doc.legal_status)}
                                  {getModificationTypeBadge(doc.modification_type)}
                                </div>
                              </TableCell>
                              <TableCell>
                                <div className="flex flex-col gap-1">
                                  <div className="flex items-center gap-1">
                                    <IconVersions className="h-3 w-3 text-muted-foreground" />
                                    <span className="text-sm font-medium">v{doc.version_number || 1}</span>
                                    {doc.is_current_version && (
                                      <Badge variant="outline" className="text-xs px-1 py-0 bg-green-50 text-green-700 border-green-200">
                                        actual
                                      </Badge>
                                    )}
                                  </div>
                                  {doc.consolidation_date && (
                                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                                      <IconClock className="h-3 w-3" />
                                      {formatConsolidationDate(doc.consolidation_date)}
                                    </span>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell>
                                {doc.similarity_score ? (
                                  <span className="text-sm font-medium">{(doc.similarity_score * 100).toFixed(0)}%</span>
                                ) : '-'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TooltipProvider>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Versioning System Info */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <IconVersions className="h-5 w-5" />
                  Sistema de Versionado Legal
                </CardTitle>
                <CardDescription>
                  Las leyes se actualizan y modifican constantemente. El sistema mantiene el historial de versiones para análisis temporal.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="rounded-lg border p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <IconCircleCheck className="h-5 w-5 text-green-600" />
                      <span className="font-medium">Estado Legal</span>
                    </div>
                    <ul className="text-sm text-muted-foreground space-y-1">
                      <li className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-green-500"></span>
                        <strong>Vigente:</strong> Ley en vigor
                      </li>
                      <li className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-yellow-500"></span>
                        <strong>Parcialmente derogada:</strong> Algunos artículos sin efecto
                      </li>
                      <li className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-red-500"></span>
                        <strong>Derogada:</strong> Ley sin efecto
                      </li>
                    </ul>
                  </div>
                  <div className="rounded-lg border p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <IconHistory className="h-5 w-5 text-blue-600" />
                      <span className="font-medium">Tipo de Modificación</span>
                    </div>
                    <ul className="text-sm text-muted-foreground space-y-1">
                      <li><strong>Original:</strong> Texto inicial publicado</li>
                      <li><strong>Modificación:</strong> Cambios en artículos</li>
                      <li><strong>Corrección:</strong> Erratas del BOE</li>
                      <li><strong>Refundido:</strong> Texto consolidado oficial</li>
                    </ul>
                  </div>
                  <div className="rounded-lg border p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <IconClock className="h-5 w-5 text-purple-600" />
                      <span className="font-medium">Consolidación</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      La <strong>fecha de consolidación</strong> indica cuándo el BOE publicó la última versión integrada del texto.
                      Se recomienda verificar siempre en el BOE la versión más reciente para documentos críticos.
                    </p>
                  </div>
                </div>
                <div className="mt-4 p-3 rounded-lg bg-blue-50 dark:bg-blue-950">
                  <p className="text-sm text-blue-800 dark:text-blue-200">
                    <strong>Nota:</strong> Emma AI utiliza automáticamente la versión vigente de las leyes para análisis de documentos.
                    El historial de versiones permite analizar contratos según la legislación aplicable en su fecha de firma.
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Category Information */}
            <div className="grid gap-4 md:grid-cols-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <IconScale className="h-4 w-4" />
                    Legislación
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    Leyes orgánicas, ordinarias, decretos legislativos y otras normas con rango de ley.
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <IconBuilding className="h-4 w-4" />
                    Regulación
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    Reales decretos, órdenes ministeriales y otras disposiciones reglamentarias.
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <IconGavel className="h-4 w-4" />
                    Jurisprudencia
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    Sentencias del Tribunal Constitucional, Tribunal Supremo y otros órganos jurisdiccionales.
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <IconWorld className="h-4 w-4" />
                    Tratados
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    Tratados internacionales, convenios y normativa de la Unión Europea.
                  </p>
                </CardContent>
              </Card>
            </div>
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

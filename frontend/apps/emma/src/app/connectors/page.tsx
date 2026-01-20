'use client'

/**
 * Connectors Page for Emma On-Premise
 *
 * Admin page to manage connectors (CRUD) and user page to authorize/sync.
 */

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  Brain,
  Loader2,
  Plug,
  RefreshCw,
  CheckCircle2,
  XCircle,
  ChevronLeft,
  Trash2,
  Plus,
  TestTube,
} from 'lucide-react'
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Button,
  Badge,
  Alert,
  AlertDescription,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@nexus/shared/ui'
import { useAuth } from '@/contexts/auth-context'
import { AppSidebar } from '@/components/layout/app-sidebar'
import {
  connectorService,
  connectorNames,
  Connector,
  ConnectorType,
} from '@/lib/services/connector.service'
import { ConnectorIcon, HealthCheckDialog } from '@/components/connectors'

function getHealthBadge(status: string) {
  const config: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
    healthy: { label: 'Saludable', variant: 'default' },
    degraded: { label: 'Degradado', variant: 'secondary' },
    unhealthy: { label: 'Error', variant: 'destructive' },
    unknown: { label: 'Desconocido', variant: 'outline' },
  }
  const { label, variant } = config[status] || config.unknown
  return <Badge variant={variant}>{label}</Badge>
}

// ============================================================================
// Main Page Component
// ============================================================================

export default function ConnectorsPage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const router = useRouter()

  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Connectors list
  const [connectors, setConnectors] = useState<Connector[]>([])

  // Action states
  const [deletingId, setDeletingId] = useState<string | null>(null)

  // Health check dialog state
  const [healthCheckDialogOpen, setHealthCheckDialogOpen] = useState(false)
  const [selectedConnector, setSelectedConnector] = useState<Connector | null>(null)

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = await connectorService.getConnectors()
      if (result.data) {
        setConnectors(result.data.items)
      } else if (result.error) {
        setError(result.error)
      }
    } catch (err: any) {
      setError(err.message || 'Error al cargar conectores')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isLoaded && isAuthenticated) {
      loadData()
    }
  }, [isLoaded, isAuthenticated, loadData])

  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push('/auth/sign-in')
    }
  }, [isLoaded, isAuthenticated, router])

  const handleTestConnector = (connector: Connector) => {
    setSelectedConnector(connector)
    setHealthCheckDialogOpen(true)
  }

  const handleHealthCheckComplete = () => {
    loadData()
  }

  const handleDeleteConnector = async (connectorId: string) => {
    if (!confirm('¿Estás seguro de eliminar este conector? Esta acción no se puede deshacer.')) {
      return
    }

    setDeletingId(connectorId)
    try {
      const result = await connectorService.deleteConnector(connectorId)
      if (result.error) {
        setError(result.error)
      } else {
        await loadData()
      }
    } catch (err: any) {
      setError(err.message || 'Error al eliminar conector')
    } finally {
      setDeletingId(null)
    }
  }

  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <SidebarProvider>
      <AppSidebar variant="inset" />

      <SidebarInset>
        {/* Header */}
        <header className="h-14 border-b flex items-center gap-2 px-4 shrink-0">
          <SidebarTrigger className="-ml-1" />
          <div className="h-4 w-px bg-border" />
          <Link href="/" className="flex items-center gap-2 text-muted-foreground hover:text-foreground">
            <ChevronLeft className="h-4 w-4" />
            <Brain className="h-5 w-5 text-primary" />
            <span className="font-semibold text-foreground">Emma</span>
          </Link>
          <div className="h-4 w-px bg-border" />
          <Plug className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">Conectores</span>
        </header>

        {/* Main Content */}
        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-5xl mx-auto space-y-6">
            {/* Title & Actions */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold">Conectores de Datos</h1>
                <p className="text-muted-foreground">
                  Gestiona las fuentes de datos externas para Emma
                </p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={loadData} disabled={isLoading}>
                  <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                  Actualizar
                </Button>
                <Button asChild>
                  <Link href="/connectors/new">
                    <Plus className="h-4 w-4 mr-2" />
                    Añadir Conector
                  </Link>
                </Button>
              </div>
            </div>

            {/* Error Alert */}
            {error && (
              <Alert variant="destructive">
                <XCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* Tabs for Admin / User view */}
            <Tabs defaultValue="admin" className="space-y-4">
              <TabsList>
                <TabsTrigger value="admin">Gestión</TabsTrigger>
                <TabsTrigger value="user">Fuentes Activas</TabsTrigger>
              </TabsList>

              {/* Admin Tab - Connector Management */}
              <TabsContent value="admin" className="space-y-4">
                {isLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  </div>
                ) : connectors.length === 0 ? (
                  <Card>
                    <CardContent className="py-12">
                      <div className="text-center">
                        <Plug className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
                        <p className="text-muted-foreground mb-4">No hay conectores configurados</p>
                        <Button asChild>
                          <Link href="/connectors/new">
                            <Plus className="h-4 w-4 mr-2" />
                            Crear Primer Conector
                          </Link>
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ) : (
                  <div className="space-y-4">
                    {connectors.map((connector) => (
                      <Card key={connector.id}>
                        <CardContent className="p-4">
                          <div className="flex items-start justify-between">
                            <div className="flex items-start gap-4">
                              <ConnectorIcon type={connector.connector_type} size="lg" />
                              <div>
                                <div className="flex items-center gap-2">
                                  <span className="font-medium">{connector.name}</span>
                                  {getHealthBadge(connector.health_status)}
                                  {!connector.is_active && (
                                    <Badge variant="secondary">Inactivo</Badge>
                                  )}
                                </div>
                                <div className="text-sm text-muted-foreground">
                                  {connectorNames[connector.connector_type]} • {connector.auth_type}
                                </div>
                                {connector.description && (
                                  <div className="text-sm text-muted-foreground mt-1">
                                    {connector.description}
                                  </div>
                                )}
                                <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                                  <span>{connector.users_connected} usuarios conectados</span>
                                  <span>
                                    Sync: {connector.sync_enabled ? `cada ${connector.sync_interval_hours}h` : 'Deshabilitado'}
                                  </span>
                                </div>
                              </div>
                            </div>
                            <div className="flex gap-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleTestConnector(connector)}
                              >
                                <TestTube className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDeleteConnector(connector.id)}
                                disabled={deletingId === connector.id}
                                className="text-destructive hover:text-destructive"
                              >
                                {deletingId === connector.id ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <Trash2 className="h-4 w-4" />
                                )}
                              </Button>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </TabsContent>

              {/* User Tab - View Active Data Sources (read-only) */}
              <TabsContent value="user" className="space-y-4">
                {isLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  </div>
                ) : connectors.filter(c => c.is_active && c.sync_enabled).length === 0 ? (
                  <Card>
                    <CardContent className="py-12">
                      <div className="text-center">
                        <Plug className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
                        <p className="text-muted-foreground mb-2">No hay fuentes de datos activas</p>
                        <p className="text-sm text-muted-foreground">
                          Contacta a tu administrador para configurar conectores
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                ) : (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">Fuentes de Datos Activas</CardTitle>
                      <CardDescription>
                        Estos conectores están sincronizando documentos automáticamente
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="grid gap-4 md:grid-cols-2">
                        {connectors
                          .filter(c => c.is_active && c.sync_enabled)
                          .map((connector) => (
                            <div key={connector.id} className="flex items-start gap-4 p-4 rounded-lg border bg-muted/30">
                              <ConnectorIcon type={connector.connector_type} size="lg" />
                              <div className="flex-1">
                                <div className="flex items-center gap-2">
                                  <span className="font-medium">{connector.name}</span>
                                  {getHealthBadge(connector.health_status)}
                                </div>
                                <div className="text-sm text-muted-foreground">
                                  {connectorNames[connector.connector_type]}
                                </div>
                                <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                                  <RefreshCw className="h-3 w-3" />
                                  <span>Sincroniza cada {connector.sync_interval_hours}h</span>
                                </div>
                              </div>
                              <CheckCircle2 className="h-5 w-5 text-green-500 flex-shrink-0" />
                            </div>
                          ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </TabsContent>
            </Tabs>
          </div>
        </main>
      </SidebarInset>

      {/* Health Check Dialog */}
      <HealthCheckDialog
        open={healthCheckDialogOpen}
        onOpenChange={setHealthCheckDialogOpen}
        connector={selectedConnector}
        onHealthCheckComplete={handleHealthCheckComplete}
      />
    </SidebarProvider>
  )
}

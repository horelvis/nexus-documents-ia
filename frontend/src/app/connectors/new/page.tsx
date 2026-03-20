'use client'

/**
 * New Connector Page for Emma On-Premise
 *
 * Full-page wizard for adding new data source connectors.
 * Step 1: Visual selection of connector type
 * Step 2: Configuration form
 */

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  IconBrain,
  IconLoader2,
  IconPlug,
  IconChevronLeft,
  IconChevronRight,
  IconArrowLeft,
  IconCircleX,
  IconCheck,
  IconSearch,
} from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Button,
  Badge,
  Alert,
  AlertDescription,
  Input,
  Label,
  Textarea,
  Switch,
  ScrollArea,
} from '@/components/ui'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/auth-context'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import {
  connectorService,
  connectorNames,
  connectorDescriptions,
  connectorCategories,
  connectorConfigs,
  ConnectorType,
  ConnectorCategory,
  CreateConnectorData,
  OAUTH_CONNECTOR_TYPES,
} from '@/lib/services/connector.service'
import { ConnectorIcon, GoogleDriveOAuthStep } from '@/components/connectors'

export default function NewConnectorPage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const router = useRouter()

  const [step, setStep] = useState<'select' | 'configure' | 'oauth'>('select')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [connectorId, setConnectorId] = useState<string | null>(null)

  // Form state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [connectorType, setConnectorType] = useState<ConnectorType | null>(null)
  const [syncEnabled, setSyncEnabled] = useState(true)
  const [syncIntervalHours, setSyncIntervalHours] = useState(24)
  const [config, setConfig] = useState<Record<string, any>>({})

  // Redirect if not authenticated
  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push('/auth/sign-in')
    }
  }, [isLoaded, isAuthenticated, router])

  // Reset config when connector type changes
  useEffect(() => {
    if (connectorType) {
      // Reset config when type changes
      setConfig({})
      // Auto-fill name with connector name
      if (!name) {
        setName(connectorNames[connectorType])
      }
    }
  }, [connectorType])

  const handleConfigChange = (field: string, value: any) => {
    setConfig((prev) => ({ ...prev, [field]: value }))
  }

  const handleSelectConnector = (type: ConnectorType) => {
    setConnectorType(type)
    setStep('configure')
    setError(null)
  }

  const handleBack = () => {
    if (step === 'oauth') {
      // Can't go back from OAuth step (connector already created)
      router.push('/connectors')
    } else if (step === 'configure') {
      setStep('select')
      setError(null)
    } else {
      router.push('/connectors')
    }
  }

  const handleSubmit = async () => {
    if (!connectorType) return

    setIsLoading(true)
    setError(null)

    try {
      const isOAuthConnector = OAUTH_CONNECTOR_TYPES.includes(connectorType)

      const data: CreateConnectorData = {
        name,
        description: description || undefined,
        connector_type: connectorType,
        auth_type: isOAuthConnector ? 'delegated' : 'service_account',
        config: isOAuthConnector ? {} : config,
        sync_enabled: syncEnabled,
        sync_interval_hours: syncIntervalHours,
      }

      const result = await connectorService.createConnector(data)

      if (result.error) {
        setError(result.error)
      } else if (isOAuthConnector && result.data) {
        setConnectorId(result.data.id)
        setStep('oauth')
      } else {
        router.push('/connectors')
      }
    } catch (err: any) {
      setError(err.message || 'Error al crear conector')
    } finally {
      setIsLoading(false)
    }
  }

  const connectorFields = connectorType ? connectorConfigs[connectorType]?.fields : null

  // Filter connectors by search query
  const filteredCategories = Object.entries(connectorCategories)
    .map(([key, category]) => ({
      key: key as ConnectorCategory,
      name: category.name,
      types: category.types.filter(
        (type) =>
          connectorNames[type].toLowerCase().includes(searchQuery.toLowerCase()) ||
          connectorDescriptions[type].toLowerCase().includes(searchQuery.toLowerCase())
      ),
    }))
    .filter((category) => category.types.length > 0)

  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
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
        <PageHeader>
          <Link href="/connectors" className="flex items-center gap-2 text-muted-foreground hover:text-foreground">
            <IconChevronLeft className="h-4 w-4" />
            <IconPlug className="h-4 w-4" />
            <span>Conectores</span>
          </Link>
          <div className="h-4 w-px bg-border" />
          <span className="font-medium">Nuevo Conector</span>

          {/* Step indicator */}
          <div className="ml-auto flex items-center gap-2">
            <div className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm",
              step === 'select' ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
            )}>
              <span className="font-medium">1</span>
              <span className="hidden sm:inline">Seleccionar</span>
            </div>
            <IconChevronRight className="h-4 w-4 text-muted-foreground" />
            <div className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm",
              step === 'configure' ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
            )}>
              <span className="font-medium">2</span>
              <span className="hidden sm:inline">Configurar</span>
            </div>
            {connectorType && OAUTH_CONNECTOR_TYPES.includes(connectorType) && (
              <>
                <IconChevronRight className="h-4 w-4 text-muted-foreground" />
                <div className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-full text-sm",
                  step === 'oauth' ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
                )}>
                  <span className="font-medium">3</span>
                  <span className="hidden sm:inline">Autorizar</span>
                </div>
              </>
            )}
          </div>
        </PageHeader>

        {/* Main Content */}
        <main className="flex-1 overflow-auto p-6">
          {/* Step 1: Connector Selection */}
          {step === 'select' && (
            <div className="max-w-5xl mx-auto">
              {/* Title */}
              <div className="text-center mb-8">
                <h1 className="text-3xl font-bold mb-2">Añadir Conector</h1>
                <p className="text-lg text-muted-foreground">
                  Selecciona una fuente de datos para conectar con Emma
                </p>
              </div>

              {/* Search */}
              <div className="relative max-w-md mx-auto mb-8">
                <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                <Input
                  placeholder="Buscar conectores..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 h-12 text-base"
                />
              </div>

              {/* Connector Grid */}
              <div className="space-y-8">
                {filteredCategories.map((category) => (
                  <div key={category.key}>
                    <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
                      {category.name}
                      <Badge variant="secondary" className="font-normal text-xs">
                        {category.types.length}
                      </Badge>
                    </h2>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                      {category.types.map((type) => (
                        <button
                          key={type}
                          onClick={() => handleSelectConnector(type)}
                          className={cn(
                            "group relative flex items-center gap-3 p-3 rounded-lg border bg-card text-left transition-all",
                            "hover:border-primary hover:bg-accent/50",
                            "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
                          )}
                        >
                          {/* Icon */}
                          <div className="flex-shrink-0">
                            <ConnectorIcon type={type} size="lg" />
                          </div>

                          {/* Content */}
                          <div className="flex-1 min-w-0">
                            <h3 className="font-medium text-sm group-hover:text-primary transition-colors">
                              {connectorNames[type]}
                            </h3>
                            <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                              {connectorDescriptions[type]}
                            </p>
                          </div>

                          {/* Hover Arrow */}
                          <IconChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                        </button>
                      ))}
                    </div>
                  </div>
                ))}

                {filteredCategories.length === 0 && (
                  <div className="text-center py-12">
                    <IconPlug className="h-12 w-12 mx-auto mb-3 text-muted-foreground opacity-30" />
                    <h3 className="font-medium mb-1">No se encontraron conectores</h3>
                    <p className="text-sm text-muted-foreground">
                      No hay conectores que coincidan con "{searchQuery}"
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-3"
                      onClick={() => setSearchQuery('')}
                    >
                      Limpiar búsqueda
                    </Button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Step 2: Configuration */}
          {step === 'configure' && connectorType && (
            <div className="max-w-2xl mx-auto">
              {/* Title with connector info */}
              <div className="flex items-start gap-4 mb-8">
                <ConnectorIcon type={connectorType} size="xl" className="flex-shrink-0" />
                <div>
                  <h1 className="text-2xl font-bold mb-1">
                    Configurar {connectorNames[connectorType]}
                  </h1>
                  <p className="text-muted-foreground">
                    {connectorDescriptions[connectorType]}
                  </p>
                </div>
              </div>

              {/* Error Alert */}
              {error && (
                <Alert variant="destructive" className="mb-6">
                  <IconCircleX className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              {/* Configuration Form */}
              <div className="space-y-6">
                {/* Basic Info */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Información Básica</CardTitle>
                    <CardDescription>
                      Nombre y descripción para identificar este conector
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="name">Nombre del Conector *</Label>
                      <Input
                        id="name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Mi Conector"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="description">Descripción</Label>
                      <Textarea
                        id="description"
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="Descripción opcional del conector"
                        rows={2}
                      />
                    </div>
                  </CardContent>
                </Card>

                {/* Type-specific Config (skip for OAuth connectors — Google Drive, OneDrive) */}
                {connectorFields && connectorFields.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">
                        Credenciales de {connectorNames[connectorType]}
                      </CardTitle>
                      <CardDescription>
                        Credenciales de cuenta de servicio para conexión automática
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {connectorFields.map((field) => (
                        <div key={field.name} className="space-y-2">
                          <Label htmlFor={field.name}>
                            {field.label}
                            {field.required && <span className="text-destructive ml-1">*</span>}
                          </Label>
                          {field.type === 'textarea' ? (
                            <Textarea
                              id={field.name}
                              value={config[field.name] || ''}
                              onChange={(e) => handleConfigChange(field.name, e.target.value)}
                              placeholder={field.placeholder}
                              rows={4}
                            />
                          ) : (
                            <Input
                              id={field.name}
                              type={field.type === 'password' ? 'password' : field.type}
                              value={config[field.name] ?? field.defaultValue ?? ''}
                              onChange={(e) =>
                                handleConfigChange(
                                  field.name,
                                  field.type === 'number' ? Number(e.target.value) : e.target.value
                                )
                              }
                              placeholder={field.placeholder}
                              min={field.min}
                              max={field.max}
                            />
                          )}
                          {field.description && (
                            <p className="text-xs text-muted-foreground">{field.description}</p>
                          )}
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                {/* Sync Settings */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Sincronización</CardTitle>
                    <CardDescription>
                      Configura la sincronización automática de documentos
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between p-4 rounded-lg border bg-muted/30">
                      <div>
                        <Label className="text-base font-medium">Sincronización Automática</Label>
                        <p className="text-sm text-muted-foreground">
                          Sincronizar documentos automáticamente en segundo plano
                        </p>
                      </div>
                      <Switch checked={syncEnabled} onCheckedChange={setSyncEnabled} />
                    </div>
                    {syncEnabled && (
                      <div className="space-y-2">
                        <Label htmlFor="sync-interval">Intervalo de Sincronización</Label>
                        <div className="flex items-center gap-3">
                          <Input
                            id="sync-interval"
                            type="number"
                            value={syncIntervalHours}
                            onChange={(e) => setSyncIntervalHours(Number(e.target.value))}
                            min={1}
                            max={168}
                            className="w-24"
                          />
                          <span className="text-muted-foreground">horas</span>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          Los documentos se sincronizarán cada {syncIntervalHours} hora{syncIntervalHours !== 1 ? 's' : ''}
                        </p>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Action Buttons */}
                <div className="flex items-center justify-between pt-4">
                  <Button variant="ghost" onClick={handleBack} disabled={isLoading}>
                    <IconArrowLeft className="h-4 w-4 mr-2" />
                    Volver
                  </Button>
                  <div className="flex gap-3">
                    <Button
                      variant="outline"
                      onClick={() => router.push('/connectors')}
                      disabled={isLoading}
                    >
                      Cancelar
                    </Button>
                    <Button
                      onClick={handleSubmit}
                      disabled={isLoading || !name}
                      size="lg"
                    >
                      {isLoading ? (
                        <>
                          <IconLoader2 className="h-4 w-4 mr-2 animate-spin" />
                          Creando...
                        </>
                      ) : (
                        <>
                          <IconCheck className="h-4 w-4 mr-2" />
                          Crear Conector
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}
          {/* Step 3: OAuth & Folder Selection */}
          {step === 'oauth' && connectorId && connectorType && (
            <div className="max-w-2xl mx-auto">
              <GoogleDriveOAuthStep
                connectorId={connectorId}
                connectorName={name}
                connectorType={connectorType}
                onComplete={() => router.push('/connectors')}
              />
            </div>
          )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

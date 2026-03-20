'use client'

/**
 * Connector Onboarding Component
 *
 * Shows available connectors and guides user through authorization and sync setup.
 * This is shown to new users who haven't connected any data sources yet.
 */

import { useState, useEffect } from 'react'
import {
  IconCheck,
  IconChevronRight,
  IconCloud,
  IconDatabase,
  IconExternalLink,
  IconFolderShare,
  IconLoader2,
  IconRefresh,
  IconServer,
} from '@tabler/icons-react'
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Badge,
  Progress,
} from '@/components/ui'
import {
  connectorService,
  ConnectorOnboardingItem,
  OnboardingStatus,
  ConnectorType,
  connectorNames,
} from '@/lib/services/connector.service'

// Icon mapping for connector types
const ConnectorIcon = ({ type }: { type: ConnectorType }) => {
  const iconClass = 'h-6 w-6'

  switch (type) {
    case 'onedrive':
      return <IconCloud className={iconClass} />
    case 'google_drive':
      return <IconFolderShare className={iconClass} />
    case 'network_share':
      return <IconServer className={iconClass} />
    default:
      return <IconCloud className={iconClass} />
  }
}

interface ConnectorCardProps {
  connector: ConnectorOnboardingItem
  onAuthorize: (connectorId: string) => void
  onEnableSync: (connectorId: string) => void
  isLoading: boolean
}

function ConnectorCard({
  connector,
  onAuthorize,
  onEnableSync,
  isLoading,
}: ConnectorCardProps) {
  const getStatus = () => {
    if (connector.is_syncing) return 'syncing'
    if (connector.is_authorized) return 'authorized'
    return 'not_connected'
  }

  const status = getStatus()

  return (
    <Card
      className={`transition-all ${
        status === 'syncing'
          ? 'border-green-500/50 bg-green-500/5'
          : status === 'authorized'
          ? 'border-blue-500/50 bg-blue-500/5'
          : 'hover:border-primary/50'
      }`}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`p-2 rounded-lg ${
                status === 'syncing'
                  ? 'bg-green-500/10 text-green-600'
                  : status === 'authorized'
                  ? 'bg-blue-500/10 text-blue-600'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              <ConnectorIcon type={connector.connector_type} />
            </div>
            <div>
              <CardTitle className="text-base">
                {connector.name}
              </CardTitle>
              <CardDescription className="text-xs mt-0.5">
                {connectorNames[connector.connector_type]}
              </CardDescription>
            </div>
          </div>
          {status === 'syncing' && (
            <Badge variant="default" className="bg-green-600">
              <IconCheck className="h-3 w-3 mr-1" />
              Sincronizando
            </Badge>
          )}
          {status === 'authorized' && (
            <Badge variant="secondary" className="bg-blue-100 text-blue-700">
              Autorizado
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {connector.description && (
          <p className="text-sm text-muted-foreground mb-4">
            {connector.description}
          </p>
        )}

        {status === 'syncing' && connector.documents_indexed > 0 && (
          <div className="mb-4">
            <div className="flex justify-between text-sm mb-1">
              <span className="text-muted-foreground">Documentos indexados</span>
              <span className="font-medium">{connector.documents_indexed}</span>
            </div>
          </div>
        )}

        <div className="flex gap-2">
          {status === 'not_connected' && (
            <Button
              onClick={() => onAuthorize(connector.id)}
              disabled={isLoading}
              className="flex-1"
            >
              {isLoading ? (
                <IconLoader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <IconExternalLink className="h-4 w-4 mr-2" />
              )}
              Conectar
            </Button>
          )}

          {status === 'authorized' && !connector.is_syncing && (
            <Button
              onClick={() => onEnableSync(connector.id)}
              disabled={isLoading}
              className="flex-1"
            >
              {isLoading ? (
                <IconLoader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <IconFolderShare className="h-4 w-4 mr-2" />
              )}
              Activar sincronización
            </Button>
          )}

          {status === 'syncing' && (
            <Button variant="outline" className="flex-1" disabled>
              <IconCheck className="h-4 w-4 mr-2" />
              Configurado
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

interface ConnectorOnboardingProps {
  onComplete: () => void
  onSkip?: () => void
}

export function ConnectorOnboarding({
  onComplete,
  onSkip,
}: ConnectorOnboardingProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<OnboardingStatus | null>(null)
  const [loadingConnector, setLoadingConnector] = useState<string | null>(null)

  // Load onboarding status
  const loadStatus = async () => {
    setIsLoading(true)
    setError(null)

    const { data, error: fetchError } = await connectorService.getOnboardingStatus()

    if (fetchError) {
      setError(fetchError)
    } else {
      setStatus(data)
      // Auto-complete if user has already connected
      if (data?.has_completed_onboarding) {
        onComplete()
      }
    }

    setIsLoading(false)
  }

  useEffect(() => {
    loadStatus()
  }, [])

  // Handle connector authorization
  const handleAuthorize = async (connectorId: string) => {
    setLoadingConnector(connectorId)

    const { data, error: fetchError } = await connectorService.getConnectorOAuthUrl(connectorId)

    if (fetchError || !data) {
      setError(fetchError || 'Failed to get authorization URL')
      setLoadingConnector(null)
      return
    }

    // Redirect to OAuth
    window.location.href = data.auth_url
  }

  // Handle enabling sync
  const handleEnableSync = async (connectorId: string) => {
    setLoadingConnector(connectorId)

    const { error: syncError } = await connectorService.enableSync(connectorId)

    if (syncError) {
      setError(syncError)
    } else {
      // Refresh status
      await loadStatus()
    }

    setLoadingConnector(null)
  }

  // Render loading state
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-muted-foreground">Cargando conectores disponibles...</p>
      </div>
    )
  }

  // Render error state
  if (error && !status) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
        <p className="text-destructive">{error}</p>
        <Button onClick={loadStatus} variant="outline">
          <IconRefresh className="h-4 w-4 mr-2" />
          Reintentar
        </Button>
      </div>
    )
  }

  // No connectors available
  if (!status || status.total_connectors === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4 text-center">
        <IconDatabase className="h-16 w-16 text-muted-foreground" />
        <h3 className="text-xl font-semibold">No hay conectores disponibles</h3>
        <p className="text-muted-foreground max-w-md">
          El administrador aún no ha configurado ningún conector de datos.
          Contacta a tu administrador para que configure OneDrive,
          Google Drive, Alfresco u otras fuentes de datos.
        </p>
        {onSkip && (
          <Button variant="outline" onClick={onSkip}>
            Continuar sin conectar
          </Button>
        )}
      </div>
    )
  }

  const progress =
    status.total_connectors > 0
      ? Math.round((status.syncing_count / status.total_connectors) * 100)
      : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-bold">Conecta tus fuentes de datos</h2>
        <p className="text-muted-foreground max-w-lg mx-auto">
          Emma puede acceder y analizar documentos de tus fuentes de datos
          corporativas. Conecta al menos una fuente para comenzar.
        </p>
      </div>

      {/* Progress */}
      {status.total_connectors > 1 && (
        <div className="max-w-md mx-auto">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-muted-foreground">Progreso</span>
            <span className="font-medium">
              {status.syncing_count} de {status.total_connectors} conectores activos
            </span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="text-center text-destructive text-sm">{error}</div>
      )}

      {/* Connector grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {status.available_connectors.map((connector) => (
          <ConnectorCard
            key={connector.id}
            connector={connector}
            onAuthorize={handleAuthorize}
            onEnableSync={handleEnableSync}
            isLoading={loadingConnector === connector.id}
          />
        ))}
      </div>

      {/* Actions */}
      <div className="flex justify-center gap-4 pt-4">
        {status.syncing_count > 0 && (
          <Button onClick={onComplete} size="lg">
            Continuar a Emma
            <IconChevronRight className="h-4 w-4 ml-2" />
          </Button>
        )}
        {status.syncing_count === 0 && onSkip && (
          <Button variant="ghost" onClick={onSkip}>
            Omitir por ahora
          </Button>
        )}
      </div>
    </div>
  )
}

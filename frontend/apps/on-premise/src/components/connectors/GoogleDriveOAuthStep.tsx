'use client'

/**
 * OAuth Step Component (Google Drive, OneDrive)
 *
 * 3-phase component for the connector creation wizard:
 * 1. Authorize — opens OAuth popup, polls for completion
 * 2. Folder Selection — browse folders, select sync root
 * 3. Complete — redirects to connectors list
 */

import { useState, useEffect, useRef } from 'react'
import {
  IconBrandGoogle,
  IconBrandWindows,
  IconCheck,
  IconChevronRight,
  IconFolder,
  IconFolderOpen,
  IconHome,
  IconLoader2,
  IconCircleX,
  IconCloudUpload,
} from '@tabler/icons-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Button,
  Badge,
  Alert,
  AlertDescription,
} from '@nexus/shared/ui'
import {
  connectorService,
  OAuthStatus,
  DriveFolder,
  ConnectorType,
} from '@/lib/services/connector.service'

interface GoogleDriveOAuthStepProps {
  connectorId: string
  connectorName: string
  connectorType?: ConnectorType
  onComplete: () => void
}

// Provider-specific branding config
const OAUTH_BRANDING: Record<string, {
  providerName: string
  authorizeTitle: string
  authorizeDescription: string
  authorizeButtonLabel: string
  authorizeButtonPolling: string
  authPopupHint: string
  syncAllLabel: string
  rootFolderName: string
  Icon: typeof IconBrandGoogle
}> = {
  google_drive: {
    providerName: 'Google Drive',
    authorizeTitle: 'Autorizar Google Drive',
    authorizeDescription: 'Conecta tu cuenta de Google para acceder a los documentos de Drive',
    authorizeButtonLabel: 'Autorizar con Google',
    authorizeButtonPolling: 'Esperando autorización...',
    authPopupHint: 'Al hacer clic en "Autorizar con Google", se abrirá una ventana para iniciar sesión con tu cuenta de Google y otorgar permisos de lectura a los documentos de Drive.',
    syncAllLabel: 'Sincronizar todo Google Drive',
    rootFolderName: 'Mi Drive',
    Icon: IconBrandGoogle,
  },
  onedrive: {
    providerName: 'Microsoft OneDrive',
    authorizeTitle: 'Autorizar OneDrive',
    authorizeDescription: 'Conecta tu cuenta de Microsoft para acceder a los archivos de OneDrive',
    authorizeButtonLabel: 'Autorizar con Microsoft',
    authorizeButtonPolling: 'Esperando autorización...',
    authPopupHint: 'Al hacer clic en "Autorizar con Microsoft", se abrirá una ventana para iniciar sesión con tu cuenta de Microsoft y otorgar permisos de lectura a los archivos de OneDrive.',
    syncAllLabel: 'Sincronizar todo OneDrive',
    rootFolderName: 'Mi OneDrive',
    Icon: IconBrandWindows,
  },
}

export function GoogleDriveOAuthStep({
  connectorId,
  connectorName,
  connectorType = 'google_drive',
  onComplete,
}: GoogleDriveOAuthStepProps) {
  const branding = OAUTH_BRANDING[connectorType] || OAUTH_BRANDING.google_drive
  const [phase, setPhase] = useState<'authorize' | 'folders' | 'complete'>('authorize')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // OAuth state
  const [oauthStatus, setOauthStatus] = useState<OAuthStatus | null>(null)
  const [isPolling, setIsPolling] = useState(false)
  const pollingRef = useRef<NodeJS.Timeout | null>(null)

  // Folder state
  const [folders, setFolders] = useState<DriveFolder[]>([])
  const [breadcrumb, setBreadcrumb] = useState<{ id: string; name: string }[]>([
    { id: 'root', name: branding.rootFolderName },
  ])
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null)
  const [isFoldersLoading, setIsFoldersLoading] = useState(false)

  // Check initial OAuth status on mount
  useEffect(() => {
    checkOAuthStatus()
  }, [])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
      }
    }
  }, [])

  const checkOAuthStatus = async () => {
    const result = await connectorService.getOAuthStatus(connectorId)
    if (result.data) {
      setOauthStatus(result.data)
      if (result.data.connected) {
        setPhase('folders')
        loadFolders('root')
      }
    }
  }

  const handleAuthorize = async () => {
    setError(null)
    setIsLoading(true)

    try {
      const result = await connectorService.getOAuthAuthorizeUrl(connectorId)
      if (result.error || !result.data?.auth_url) {
        setError(result.error || 'No se pudo obtener la URL de autorización')
        setIsLoading(false)
        return
      }

      const popup = window.open(result.data.auth_url, 'oauth-popup', 'width=600,height=700,scrollbars=yes')

      if (!popup) {
        setError('No se pudo abrir la ventana de autorización. Verifica que los popups estén permitidos.')
        setIsLoading(false)
        return
      }
    } catch (err: any) {
      setError(err.message || 'Error al iniciar autorización')
      setIsLoading(false)
      return
    }

    setIsLoading(false)

    // Start polling for OAuth completion (fallback)
    setIsPolling(true)
    pollingRef.current = setInterval(async () => {
      const result = await connectorService.getOAuthStatus(connectorId)
      if (result.data?.connected) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        setIsPolling(false)
        setOauthStatus(result.data)
        setPhase('folders')
        loadFolders('root')
      }
    }, 3000)
  }

  // Listen for postMessage from OAuth popup (faster than polling)
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'oauth-success') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current)
          pollingRef.current = null
        }
        setIsPolling(false)
        setOauthStatus({
          connected: true,
          ...(connectorType === 'onedrive'
            ? { microsoft_email: event.data.email }
            : { google_email: event.data.email }),
        })
        setPhase('folders')
        loadFolders('root')
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [])

  const loadFolders = async (parentId: string) => {
    setIsFoldersLoading(true)
    setError(null)

    try {
      const result = await connectorService.listFolders(connectorId, parentId)
      if (result.error) {
        setError(result.error)
      } else {
        setFolders(result.data || [])
      }
    } catch (err: any) {
      setError(err.message || 'Error al cargar carpetas')
    } finally {
      setIsFoldersLoading(false)
    }
  }

  const handleNavigateFolder = (folder: DriveFolder) => {
    setSelectedFolderId(null)
    setBreadcrumb((prev) => [...prev, { id: folder.id, name: folder.name }])
    loadFolders(folder.id)
  }

  const handleBreadcrumbClick = (index: number) => {
    const target = breadcrumb[index]
    setSelectedFolderId(null)
    setBreadcrumb((prev) => prev.slice(0, index + 1))
    loadFolders(target.id)
  }

  const handleSelectFolder = async () => {
    // Use selected folder if one is picked, otherwise use current breadcrumb location
    const selectedFolder = selectedFolderId
      ? folders.find(f => f.id === selectedFolderId)
      : null
    const folderId = selectedFolder ? selectedFolder.id : breadcrumb[breadcrumb.length - 1].id
    const folderName = selectedFolder ? selectedFolder.name : breadcrumb[breadcrumb.length - 1].name

    setIsLoading(true)
    setError(null)

    try {
      const result = await connectorService.updateConnectorConfig(connectorId, {
        folder_id: folderId === 'root' ? null : folderId,
        folder_name: folderName,
      })
      if (result.error) {
        setError(result.error)
      } else {
        setPhase('complete')
        setTimeout(onComplete, 1500)
      }
    } catch (err: any) {
      setError(err.message || 'Error al guardar configuración')
    } finally {
      setIsLoading(false)
    }
  }

  const handleSyncAll = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = await connectorService.updateConnectorConfig(connectorId, {
        folder_id: null,
        folder_name: null,
      })
      if (result.error) {
        setError(result.error)
      } else {
        setPhase('complete')
        setTimeout(onComplete, 1500)
      }
    } catch (err: any) {
      setError(err.message || 'Error al guardar configuración')
    } finally {
      setIsLoading(false)
    }
  }

  // Phase 3: Complete
  if (phase === 'complete') {
    return (
      <Card>
        <CardContent className="flex flex-col items-center py-12">
          <div className="h-16 w-16 rounded-full bg-green-100 flex items-center justify-center mb-4">
            <IconCheck className="h-8 w-8 text-green-600" />
          </div>
          <h2 className="text-xl font-bold mb-2">¡Conector creado!</h2>
          <p className="text-muted-foreground">
            {connectorName} está listo para sincronizar documentos.
          </p>
          <p className="text-sm text-muted-foreground mt-1">Redirigiendo...</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {/* Error */}
      {error && (
        <Alert variant="destructive">
          <IconCircleX className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Phase 1: Authorize */}
      {phase === 'authorize' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{branding.authorizeTitle}</CardTitle>
            <CardDescription>
              {branding.authorizeDescription}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="p-4 rounded-lg border bg-muted/30 text-sm text-muted-foreground">
              <p>{branding.authPopupHint}</p>
            </div>

            <Button
              onClick={handleAuthorize}
              disabled={isPolling || isLoading}
              size="lg"
              className="w-full"
            >
              {isPolling ? (
                <>
                  <IconLoader2 className="h-5 w-5 mr-2 animate-spin" />
                  {branding.authorizeButtonPolling}
                </>
              ) : (
                <>
                  <branding.Icon className="h-5 w-5 mr-2" />
                  {branding.authorizeButtonLabel}
                </>
              )}
            </Button>

            {isPolling && (
              <p className="text-xs text-center text-muted-foreground">
                Completa la autorización en la ventana emergente. Esta página se actualizará automáticamente.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Phase 2: Folder Selection */}
      {phase === 'folders' && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">Seleccionar Carpeta</CardTitle>
                <CardDescription>
                  Elige qué carpeta de Drive sincronizar, o sincroniza todo
                </CardDescription>
              </div>
              {(oauthStatus?.google_email || oauthStatus?.microsoft_email || oauthStatus?.email) && (
                <Badge variant="secondary" className="flex items-center gap-1.5">
                  <IconCheck className="h-3 w-3 text-green-600" />
                  {oauthStatus.google_email || oauthStatus.microsoft_email || oauthStatus.email}
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Breadcrumb */}
            <div className="flex items-center gap-1 text-sm flex-wrap">
              {breadcrumb.map((crumb, idx) => (
                <span key={crumb.id} className="flex items-center gap-1">
                  {idx > 0 && <IconChevronRight className="h-3 w-3 text-muted-foreground" />}
                  <button
                    onClick={() => handleBreadcrumbClick(idx)}
                    className="text-primary hover:underline flex items-center gap-1"
                  >
                    {idx === 0 ? <IconHome className="h-3.5 w-3.5" /> : <IconFolder className="h-3.5 w-3.5" />}
                    {crumb.name}
                  </button>
                </span>
              ))}
            </div>

            {/* Folder list */}
            <div className="border rounded-lg divide-y max-h-80 overflow-auto">
              {isFoldersLoading ? (
                <div className="flex items-center justify-center py-8">
                  <IconLoader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : folders.length === 0 ? (
                <div className="text-center py-8 text-sm text-muted-foreground">
                  <IconFolderOpen className="h-8 w-8 mx-auto mb-2 opacity-30" />
                  No hay subcarpetas en esta ubicación
                </div>
              ) : (
                folders.map((folder) => (
                  <div
                    key={folder.id}
                    className={`flex items-center gap-3 w-full px-4 py-3 hover:bg-accent/50 transition-colors ${selectedFolderId === folder.id ? 'bg-primary/10 border-l-2 border-l-primary' : ''}`}
                  >
                    <button
                      onClick={() => setSelectedFolderId(selectedFolderId === folder.id ? null : folder.id)}
                      className="flex items-center gap-3 flex-1 text-left min-w-0"
                    >
                      <IconFolder className={`h-5 w-5 flex-shrink-0 ${selectedFolderId === folder.id ? 'text-primary' : 'text-blue-500'}`} />
                      <span className="text-sm truncate">{folder.name}</span>
                    </button>
                    <button
                      onClick={() => handleNavigateFolder(folder)}
                      className="p-1 rounded hover:bg-accent flex-shrink-0"
                      title="Abrir carpeta"
                    >
                      <IconChevronRight className="h-4 w-4 text-muted-foreground" />
                    </button>
                  </div>
                ))
              )}
            </div>

            {/* Actions */}
            <div className="flex flex-col gap-2 pt-2">
              <Button
                onClick={handleSelectFolder}
                disabled={isLoading}
                size="lg"
              >
                {isLoading ? (
                  <IconLoader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <IconCheck className="h-4 w-4 mr-2" />
                )}
                Seleccionar carpeta
                <Badge variant="secondary" className="ml-2 text-xs">
                  {selectedFolderId ? folders.find(f => f.id === selectedFolderId)?.name : breadcrumb[breadcrumb.length - 1].name}
                </Badge>
              </Button>
              <Button
                variant="ghost"
                onClick={handleSyncAll}
                disabled={isLoading}
                className="text-muted-foreground"
              >
                <IconCloudUpload className="h-4 w-4 mr-2" />
                {branding.syncAllLabel}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

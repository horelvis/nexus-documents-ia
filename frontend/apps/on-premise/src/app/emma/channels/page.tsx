'use client'

/**
 * Channels Page for Emma On-Premise
 *
 * Admin page to manage Emma multi-channel messaging (Telegram, WhatsApp, Slack, Email).
 * Follows the same layout and component pattern as the Connectors page.
 */

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import {
  IconBrain,
  IconLoader2,
  IconMessageCircle,
  IconRefresh,
  IconPlus,
  IconTrash,
  IconTestPipe,
  IconChevronLeft,
  IconCircleX,
  IconCircleCheck,
  IconRobot,
  IconBrandTelegram,
  IconBrandWhatsapp,
  IconBrandSlack,
  IconMail,
  IconLink,
} from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
  Card,
  CardContent,
  Button,
  Badge,
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@nexus/shared/ui'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/contexts/auth-context'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'

// ============================================================================
// Types & Constants
// ============================================================================

interface Channel {
  id: string
  channel_type: string
  channel_name: string
  config: Record<string, any>
  is_active: boolean
  auto_respond: boolean
}

const CHANNEL_TYPES = [
  { value: 'telegram', label: 'Telegram', icon: IconBrandTelegram, description: 'Bot de Telegram' },
  { value: 'whatsapp', label: 'WhatsApp', icon: IconBrandWhatsapp, description: 'Twilio WhatsApp API' },
  { value: 'slack', label: 'Slack', icon: IconBrandSlack, description: 'Slack Web API' },
  { value: 'email', label: 'Email', icon: IconMail, description: 'SMTP / IMAP' },
]

const EMMA_SERVICE_URL = process.env.NEXT_PUBLIC_EMMA_SERVICE_URL || 'http://localhost:8009'

function getChannelIcon(type: string) {
  const info = CHANNEL_TYPES.find((t) => t.value === type)
  if (!info) return IconRobot
  return info.icon
}

// ============================================================================
// Main Page Component
// ============================================================================

export default function ChannelsPage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const router = useRouter()

  const [channels, setChannels] = useState<Channel[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create dialog
  const [createDialogOpen, setCreateDialogOpen] = useState(false)

  // Delete confirmation
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [channelToDelete, setChannelToDelete] = useState<Channel | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  // Health check
  const [checkingId, setCheckingId] = useState<string | null>(null)

  // Pairing dialog
  const [pairingDialogOpen, setPairingDialogOpen] = useState(false)

  const loadChannels = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await fetch(`${EMMA_SERVICE_URL}/channels`)
      if (res.ok) {
        const data = await res.json()
        setChannels(data.channels || [])
      } else {
        setError('Error al cargar canales')
      }
    } catch (err: any) {
      setError(err.message || 'Error de conexión con Emma Service')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (isLoaded && isAuthenticated) {
      loadChannels()
    }
  }, [isLoaded, isAuthenticated])

  useEffect(() => {
    if (isLoaded && !isAuthenticated) {
      router.push('/auth/sign-in')
    }
  }, [isLoaded, isAuthenticated, router])

  const handleDeleteClick = (channel: Channel) => {
    setChannelToDelete(channel)
    setDeleteDialogOpen(true)
  }

  const handleDeleteConfirm = async () => {
    if (!channelToDelete) return
    setDeleteDialogOpen(false)
    setDeletingId(channelToDelete.id)

    try {
      const res = await fetch(`${EMMA_SERVICE_URL}/channels/${channelToDelete.id}`, {
        method: 'DELETE',
      })
      if (!res.ok) {
        setError('Error al eliminar canal')
      } else {
        await loadChannels()
      }
    } catch (err: any) {
      setError(err.message || 'Error al eliminar canal')
    } finally {
      setDeletingId(null)
      setChannelToDelete(null)
    }
  }

  const handleHealthCheck = async (channel: Channel) => {
    setCheckingId(channel.id)
    try {
      const res = await fetch(`${EMMA_SERVICE_URL}/channels/${channel.id}/health`)
      const data = await res.json()
      // Refresh list to show updated health status
      await loadChannels()
    } catch {
      setError('No se pudo verificar la conexión')
    } finally {
      setCheckingId(null)
    }
  }

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
          <Link
            href="/"
            className="flex items-center gap-2 text-muted-foreground hover:text-foreground"
          >
            <IconChevronLeft className="h-4 w-4" />
            <IconBrain className="h-5 w-5 text-primary" />
            <span className="font-semibold text-foreground">Emma</span>
          </Link>
          <div className="h-4 w-px bg-border" />
          <IconMessageCircle className="h-4 w-4 text-muted-foreground" />
          <span className="text-muted-foreground">Canales</span>
        </PageHeader>

        {/* Main Content */}
        <main className="flex-1 overflow-auto p-6">
          <div className="max-w-5xl mx-auto space-y-6">
            {/* Title & Actions */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold">Canales de Emma</h1>
                <p className="text-muted-foreground">
                  Conecta Emma a WhatsApp, Telegram, Slack y Email
                </p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setPairingDialogOpen(true)}>
                  <IconLink className="h-4 w-4 mr-2" />
                  Vincular Cuenta
                </Button>
                <Button variant="outline" onClick={loadChannels} disabled={isLoading}>
                  <IconRefresh className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                  Actualizar
                </Button>
                <Button onClick={() => setCreateDialogOpen(true)}>
                  <IconPlus className="h-4 w-4 mr-2" />
                  Nuevo Canal
                </Button>
              </div>
            </div>

            {/* Error Alert */}
            {error && (
              <Alert variant="destructive">
                <IconCircleX className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* Channel List */}
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
              </div>
            ) : channels.length === 0 ? (
              <Card>
                <CardContent className="py-12">
                  <div className="text-center">
                    <IconMessageCircle className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
                    <p className="text-muted-foreground mb-4">No hay canales configurados</p>
                    <Button onClick={() => setCreateDialogOpen(true)}>
                      <IconPlus className="h-4 w-4 mr-2" />
                      Crear Primer Canal
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-4">
                {channels.map((channel) => {
                  const ChannelIcon = getChannelIcon(channel.channel_type)
                  const typeInfo = CHANNEL_TYPES.find((t) => t.value === channel.channel_type)

                  return (
                    <Card key={channel.id}>
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between">
                          <div className="flex items-start gap-4">
                            <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center">
                              <ChannelIcon className="h-5 w-5 text-foreground" />
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-medium">{channel.channel_name}</span>
                                {channel.is_active ? (
                                  <Badge variant="default">Activo</Badge>
                                ) : (
                                  <Badge variant="secondary">Inactivo</Badge>
                                )}
                              </div>
                              <div className="text-sm text-muted-foreground">
                                {typeInfo?.label || channel.channel_type}
                                {channel.auto_respond && ' · Auto-respuesta activada'}
                              </div>
                            </div>
                          </div>

                          <TooltipProvider>
                            <div className="flex gap-2">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleHealthCheck(channel)}
                                    disabled={checkingId === channel.id}
                                  >
                                    {checkingId === channel.id ? (
                                      <IconLoader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                      <IconTestPipe className="h-4 w-4" />
                                    )}
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p>Verificar conexión</p>
                                </TooltipContent>
                              </Tooltip>

                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleDeleteClick(channel)}
                                    disabled={deletingId === channel.id}
                                    className="text-destructive hover:text-destructive"
                                  >
                                    {deletingId === channel.id ? (
                                      <IconLoader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                      <IconTrash className="h-4 w-4" />
                                    )}
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p>Eliminar canal</p>
                                </TooltipContent>
                              </Tooltip>
                            </div>
                          </TooltipProvider>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            )}
          </div>
        </main>
      </SidebarInset>

      {/* Create Channel Dialog */}
      <CreateChannelDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onCreated={() => {
          setCreateDialogOpen(false)
          loadChannels()
        }}
      />

      {/* Pairing Dialog */}
      <PairingDialog
        open={pairingDialogOpen}
        onOpenChange={setPairingDialogOpen}
      />

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar canal?</AlertDialogTitle>
            <AlertDialogDescription>
              {channelToDelete && (
                <>
                  Estás a punto de eliminar el canal{' '}
                  <strong>{channelToDelete.channel_name}</strong>.
                  <br />
                  <br />
                  Se eliminarán todas las credenciales y configuraciones asociadas.
                  Esta acción no se puede deshacer.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              <IconTrash className="h-4 w-4 mr-2" />
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SidebarProvider>
  )
}

// ============================================================================
// Create Channel Dialog
// ============================================================================

function CreateChannelDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}) {
  const [channelType, setChannelType] = useState('telegram')
  const [channelName, setChannelName] = useState('')
  const [credentials, setCredentials] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!channelName.trim()) return
    setIsSubmitting(true)
    setError(null)

    try {
      const res = await fetch(`${EMMA_SERVICE_URL}/channels`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          channel_type: channelType,
          channel_name: channelName,
          config: {},
          credentials: credentials || undefined,
          auto_respond: true,
        }),
      })
      if (res.ok) {
        // Reset form
        setChannelName('')
        setCredentials('')
        setChannelType('telegram')
        onCreated()
      } else {
        const data = await res.json()
        setError(data.detail || 'Error al crear canal')
      }
    } catch (err: any) {
      setError(err.message || 'Error de conexión')
    } finally {
      setIsSubmitting(false)
    }
  }

  const selectedType = CHANNEL_TYPES.find((t) => t.value === channelType)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Nuevo Canal</DialogTitle>
          <DialogDescription>
            Conecta Emma a una plataforma de mensajería externa
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Channel Type */}
          <div className="space-y-2">
            <Label>Tipo de canal</Label>
            <Select value={channelType} onValueChange={setChannelType}>
              <SelectTrigger>
                <SelectValue placeholder="Selecciona un tipo" />
              </SelectTrigger>
              <SelectContent>
                {CHANNEL_TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    <div className="flex items-center gap-2">
                      <t.icon className="h-4 w-4" />
                      <span>{t.label}</span>
                      <span className="text-muted-foreground text-xs">— {t.description}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Channel Name */}
          <div className="space-y-2">
            <Label htmlFor="channel-name">Nombre</Label>
            <Input
              id="channel-name"
              value={channelName}
              onChange={(e) => setChannelName(e.target.value)}
              placeholder={`Ej: Bot de soporte ${selectedType?.label || ''}`}
            />
          </div>

          {/* Credentials */}
          <div className="space-y-2">
            <Label htmlFor="channel-credentials">
              Credenciales (token / API key)
            </Label>
            <Input
              id="channel-credentials"
              type="password"
              value={credentials}
              onChange={(e) => setCredentials(e.target.value)}
              placeholder="Se encriptarán automáticamente"
            />
            <p className="text-xs text-muted-foreground">
              Las credenciales se almacenan con cifrado Fernet en el servidor
            </p>
          </div>

          {/* Error */}
          {error && (
            <Alert variant="destructive">
              <IconCircleX className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting || !channelName.trim()}
          >
            {isSubmitting ? (
              <>
                <IconLoader2 className="h-4 w-4 mr-2 animate-spin" />
                Creando...
              </>
            ) : (
              <>
                <IconPlus className="h-4 w-4 mr-2" />
                Crear Canal
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ============================================================================
// Pairing Dialog - Link external account to NouxCubeIA user
// ============================================================================

function PairingDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [code, setCode] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const { user } = useAuth()

  const handleSubmit = async () => {
    if (!code.trim() || code.length !== 6) {
      setError('El código debe tener 6 dígitos')
      return
    }

    setIsSubmitting(true)
    setError(null)
    setSuccess(false)

    try {
      const res = await fetch(`${EMMA_SERVICE_URL}/channels/pairing/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: code.trim(),
          user_id: user?.id || '00000000-0000-0000-0000-000000000001',
        }),
      })

      if (res.ok) {
        setSuccess(true)
        setCode('')
        // Close dialog after 2 seconds
        setTimeout(() => {
          onOpenChange(false)
          setSuccess(false)
        }, 2000)
      } else {
        const data = await res.json()
        setError(data.detail || 'Código inválido o expirado')
      }
    } catch (err: any) {
      setError(err.message || 'Error de conexión')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Only allow digits, max 6 characters
    const value = e.target.value.replace(/\D/g, '').slice(0, 6)
    setCode(value)
    setError(null)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Vincular Cuenta Externa</DialogTitle>
          <DialogDescription>
            Introduce el código de 6 dígitos que Emma te envió por Telegram, WhatsApp o Slack
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Code Input */}
          <div className="space-y-2">
            <Label htmlFor="pairing-code">Código de vinculación</Label>
            <Input
              id="pairing-code"
              value={code}
              onChange={handleCodeChange}
              placeholder="000000"
              className="text-center text-2xl tracking-widest font-mono"
              maxLength={6}
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground text-center">
              El código expira en 10 minutos
            </p>
          </div>

          {/* Success */}
          {success && (
            <Alert>
              <IconCircleCheck className="h-4 w-4 text-green-600" />
              <AlertDescription className="text-green-600">
                ¡Cuenta vinculada correctamente! Ahora puedes chatear con Emma desde tu canal externo.
              </AlertDescription>
            </Alert>
          )}

          {/* Error */}
          {error && (
            <Alert variant="destructive">
              <IconCircleX className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting || code.length !== 6 || success}
          >
            {isSubmitting ? (
              <>
                <IconLoader2 className="h-4 w-4 mr-2 animate-spin" />
                Verificando...
              </>
            ) : (
              <>
                <IconLink className="h-4 w-4 mr-2" />
                Vincular
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

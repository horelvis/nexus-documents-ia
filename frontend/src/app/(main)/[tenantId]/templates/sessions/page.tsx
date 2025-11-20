"use client"

import Link from "next/link"
import { use, useEffect, useMemo, useState } from "react"
import { formatDistanceToNow } from "date-fns"
import { IconClockHour4, IconExternalLink, IconRefresh, IconTrash, IconEditCircle } from "@tabler/icons-react"

import { useBackendUser } from "@/contexts/user-context"
import { useToast } from "@/hooks/use-toast"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"

interface TemplateEditSession {
  id: string
  template_id: string
  template_name: string
  google_doc_edit_url: string
  google_doc_url: string
  status: string
  created_at: string
  expires_at: string
  last_activity?: string
  completed_at?: string
  changes_detected?: boolean
  cleanup_completed?: boolean
  error_message?: string
}

export default function TemplateSessionsPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const resolvedParams = use(params)
  const tenantId = resolvedParams?.tenantId

  const { toast } = useToast()
  const { backendUser } = useBackendUser()

  const [sessions, setSessions] = useState<TemplateEditSession[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [includeCompleted, setIncludeCompleted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const loadSessions = async () => {
    if (!tenantId) return

    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch(
        `/api/template-editor/sessions?tenant_id=${tenantId}&include_completed=${includeCompleted}`
      )

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}))
        throw new Error(detail?.error || "No se pudieron cargar las sesiones")
      }

      const data = await response.json()
      setSessions(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error("[template-sessions] load error:", err)
      const message = err instanceof Error ? err.message : "Error desconocido al cargar las sesiones"
      setError(message)
      toast({
        title: "Error al cargar",
        description: message,
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadSessions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, includeCompleted])

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await loadSessions()
    setIsRefreshing(false)
  }

  const handleCancel = async (sessionId: string) => {
    try {
      const response = await fetch(`/api/template-editor/sessions/${sessionId}`, {
        method: "DELETE",
      })

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}))
        throw new Error(detail?.error || "No se pudo cancelar la sesión")
      }

      toast({
        title: "Sesión cancelada",
        description: "El documento temporal ha sido limpiado correctamente.",
      })

      await loadSessions()
    } catch (err) {
      console.error("[template-sessions] cancel error:", err)
      toast({
        title: "Error",
        description: err instanceof Error ? err.message : "No se pudo cancelar la sesión",
        variant: "destructive",
      })
    }
  }

  const handleExtend = async (sessionId: string) => {
    const clerkUserId = backendUser?.clerk_user_id || backendUser?.id
    if (!clerkUserId) {
      toast({
        title: "Sesión no disponible",
        description: "No pudimos identificar al usuario actual para extender la sesión.",
        variant: "destructive",
      })
      return
    }

    try {
      const response = await fetch(`/api/template-editor/sessions/${sessionId}/extend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: clerkUserId, hours: 1 }),
      })

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}))
        throw new Error(detail?.error || "No se pudo extender la sesión")
      }

      toast({
        title: "Sesión extendida",
        description: "Añadimos 1 hora al tiempo de edición.",
      })

      await loadSessions()
    } catch (err) {
      console.error("[template-sessions] extend error:", err)
      toast({
        title: "Error",
        description: err instanceof Error ? err.message : "No se pudo extender la sesión",
        variant: "destructive",
      })
    }
  }

  const handleCopyLink = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      toast({
        title: "Enlace copiado",
        description: "Puedes compartirlo directamente desde tu portapapeles.",
      })
    } catch {
      toast({
        title: "No se pudo copiar",
        description: "Copia manualmente desde el botón de abrir documento.",
        variant: "destructive",
      })
    }
  }

  const activeSessions = useMemo(
    () => sessions.filter((session) => session.status === "active"),
    [sessions]
  )

  const statusBadgeVariant = (status: string) => {
    switch (status) {
      case "active":
        return "success"
      case "completed":
        return "secondary"
      case "cleanup_pending":
        return "outline"
      default:
        return "destructive"
    }
  }

  const renderSessionCard = (session: TemplateEditSession) => {
    const expiresLabel = formatDistanceToNow(new Date(session.expires_at), { addSuffix: true })
    const createdLabel = formatDistanceToNow(new Date(session.created_at), { addSuffix: true })

    return (
      <Card key={session.id} className="flex flex-col">
        <CardHeader className="space-y-2">
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle className="text-lg">{session.template_name}</CardTitle>
              <CardDescription className="text-muted-foreground">
                Creada {createdLabel}
              </CardDescription>
            </div>
            <Badge variant={statusBadgeVariant(session.status)}>
              {session.status === "active" ? "Activa" : session.status}
            </Badge>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <IconClockHour4 className="h-4 w-4" />
            Expira {expiresLabel}
            {session.last_activity && (
              <>
                <span aria-hidden="true">•</span>
                Última actividad {formatDistanceToNow(new Date(session.last_activity), { addSuffix: true })}
              </>
            )}
            {session.changes_detected && (
              <>
                <span aria-hidden="true">•</span>
                Cambios detectados
              </>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex flex-1 flex-col gap-4">
          {session.error_message && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {session.error_message}
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => window.open(session.google_doc_edit_url, "_blank")}>
              <IconExternalLink className="mr-2 h-4 w-4" />
              Abrir documento
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleCopyLink(session.google_doc_edit_url)}
            >
              Copiar enlace
            </Button>
            {session.status === "active" && (
              <>
                <Button size="sm" variant="outline" onClick={() => handleExtend(session.id)}>
                  <IconEditCircle className="mr-2 h-4 w-4" />
                  Extender 1h
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  onClick={() => handleCancel(session.id)}
                >
                  <IconTrash className="mr-2 h-4 w-4" />
                  Cancelar
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="container mx-auto flex max-w-6xl flex-col gap-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Sesiones de edición</h1>
          <p className="text-muted-foreground">
            Controla los documentos que se están editando en Google Docs y gestiona su ciclo de vida.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" asChild>
            <Link href={`/${tenantId}/templates`}>
              Volver a plantillas
            </Link>
          </Button>
          <Button variant="outline" onClick={handleRefresh} disabled={isRefreshing || isLoading}>
            <IconRefresh className={cn("mr-2 h-4 w-4", isRefreshing && "animate-spin")} />
            Actualizar
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="flex flex-wrap items-center gap-3 py-4">
          <div className="flex items-center gap-3">
            <Switch
              id="include-completed"
              checked={includeCompleted}
              onCheckedChange={(checked) => setIncludeCompleted(!!checked)}
            />
            <Label htmlFor="include-completed">Mostrar sesiones completadas</Label>
          </div>
          <Separator orientation="vertical" className="hidden h-6 md:block" />
          <div className="text-sm text-muted-foreground">
            Activas: <span className="font-medium text-foreground">{activeSessions.length}</span> · Total{" "}
            {sessions.length}
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center">
          <div className="animate-spin rounded-full border-b-2 border-t-2 border-primary p-3" />
        </div>
      ) : error ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-destructive">
            {error}
          </CardContent>
        </Card>
      ) : sessions.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <p className="font-medium">No hay sesiones activas.</p>
            <p className="text-sm">
              Empieza a editar una plantilla para que aparezca aquí y puedas gestionarla.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          {sessions.map((session) => renderSessionCard(session))}
        </div>
      )}
    </div>
  )
}

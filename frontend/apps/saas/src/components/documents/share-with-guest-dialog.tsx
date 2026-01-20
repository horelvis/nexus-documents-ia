"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Checkbox } from "@/components/ui/checkbox"
import { ScrollArea } from "@/components/ui/scroll-area"
import { toast } from "sonner"
import { IconLoader2, IconUserShare, IconFile, IconMail, IconCalendar } from "@tabler/icons-react"
import { useSiteGuestService, type CreateGuestWithShareRequest } from "@/lib/services/site-guest.service"
import type { Document as ApiDocument } from "@/lib/types"
import { formatFileSize } from "@/lib/document-utils"

interface ShareWithGuestDialogProps {
  documents: ApiDocument[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

export function ShareWithGuestDialog({
  documents,
  open,
  onOpenChange,
  onSuccess,
}: ShareWithGuestDialogProps) {
  const siteGuestService = useSiteGuestService()

  // Form state
  const [email, setEmail] = useState("")
  const [name, setName] = useState("")
  const [shareName, setShareName] = useState("")
  const [permissionType, setPermissionType] = useState<'view' | 'download'>('view')
  const [expiresAt, setExpiresAt] = useState("")
  const [sendInvitation, setSendInvitation] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset form when dialog opens/closes
  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      // Reset form on close
      setEmail("")
      setName("")
      setShareName("")
      setPermissionType("view")
      setExpiresAt("")
      setSendInvitation(true)
      setError(null)
    }
    onOpenChange(newOpen)
  }

  const handleSubmit = async () => {
    // Validate email
    if (!email || !email.includes('@')) {
      setError('Por favor ingresa un email válido')
      return
    }

    if (documents.length === 0) {
      setError('No hay documentos seleccionados')
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      const requestData: CreateGuestWithShareRequest = {
        email: email.trim().toLowerCase(),
        name: name.trim() || undefined,
        share_name: shareName.trim() || `Documentos compartidos (${documents.length})`,
        document_ids: documents.map(d => d.id),
        permission_type: permissionType,
        expires_at: expiresAt || undefined,
        send_invitation: sendInvitation,
      }

      const response = await siteGuestService.createGuestWithShare(requestData)

      if (response.error) {
        setError(response.error)
        return
      }

      if (response.data) {
        const message = response.data.is_new_guest
          ? `Invitación enviada a ${email}`
          : `Documentos compartidos con ${email}`

        toast.success(message, {
          description: `${documents.length} documento(s) en "${response.data.share.name}"`,
        })

        handleOpenChange(false)
        onSuccess?.()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al compartir documentos')
    } finally {
      setIsLoading(false)
    }
  }

  // Get minimum date (today)
  const today = new Date().toISOString().split('T')[0]

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100">
              <IconUserShare className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <DialogTitle>Compartir con Invitado Externo</DialogTitle>
              <DialogDescription>
                Comparte {documents.length} documento(s) con un usuario externo
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Selected documents preview */}
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Documentos seleccionados</Label>
            <ScrollArea className="h-24 rounded-md border bg-muted/30 p-2">
              {documents.map((doc) => (
                <div key={doc.id} className="flex items-center gap-2 py-1 text-sm">
                  <IconFile className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                  <span className="truncate flex-1">{doc.title || doc.filename}</span>
                  <span className="text-xs text-muted-foreground">{formatFileSize(doc.file_size)}</span>
                </div>
              ))}
            </ScrollArea>
          </div>

          {/* Email input */}
          <div className="space-y-2">
            <Label htmlFor="email">
              <span className="flex items-center gap-2">
                <IconMail className="h-4 w-4" />
                Email del invitado <span className="text-red-500">*</span>
              </span>
            </Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="invitado@empresa.com"
              disabled={isLoading}
            />
          </div>

          {/* Name input (optional) */}
          <div className="space-y-2">
            <Label htmlFor="name">Nombre (opcional)</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Juan García"
              disabled={isLoading}
            />
          </div>

          {/* Share name */}
          <div className="space-y-2">
            <Label htmlFor="shareName">Nombre de la colección</Label>
            <Input
              id="shareName"
              value={shareName}
              onChange={(e) => setShareName(e.target.value)}
              placeholder={`Documentos compartidos (${documents.length})`}
              disabled={isLoading}
            />
            <p className="text-xs text-muted-foreground">
              El invitado verá esta colección en su portal
            </p>
          </div>

          {/* Permission type */}
          <div className="space-y-2">
            <Label htmlFor="permissionType">Permisos</Label>
            <Select value={permissionType} onValueChange={(v) => setPermissionType(v as 'view' | 'download')} disabled={isLoading}>
              <SelectTrigger id="permissionType">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="view">Solo ver</SelectItem>
                <SelectItem value="download">Ver y descargar</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Expiration date */}
          <div className="space-y-2">
            <Label htmlFor="expiresAt">
              <span className="flex items-center gap-2">
                <IconCalendar className="h-4 w-4" />
                Fecha de expiración (opcional)
              </span>
            </Label>
            <Input
              id="expiresAt"
              type="date"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              min={today}
              disabled={isLoading}
            />
          </div>

          {/* Send invitation checkbox */}
          <div className="flex items-center space-x-2">
            <Checkbox
              id="sendInvitation"
              checked={sendInvitation}
              onCheckedChange={(checked) => setSendInvitation(checked === true)}
              disabled={isLoading}
            />
            <Label htmlFor="sendInvitation" className="text-sm font-normal cursor-pointer">
              Enviar email de invitación
            </Label>
          </div>

          {/* Error message */}
          {error && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-600">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={isLoading}>
            Cancelar
          </Button>
          <Button onClick={handleSubmit} disabled={isLoading || !email}>
            {isLoading && <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />}
            <IconUserShare className="mr-2 h-4 w-4" />
            Compartir
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

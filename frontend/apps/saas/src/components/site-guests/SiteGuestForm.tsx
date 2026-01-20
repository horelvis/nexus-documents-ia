"use client"

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle
} from '@/components/ui/dialog'
import { useSiteGuestService, SiteGuest, SiteGuestCreate, SiteGuestUpdate } from '@/lib/services/site-guest.service'
import { Loader2, Eye, Download, Upload } from 'lucide-react'
import { useTranslation } from '@/lib/i18n/hooks'

interface SiteGuestFormProps {
  guest: SiteGuest | null
  open: boolean
  onClose: () => void
  onSaved: () => void
}

export function SiteGuestForm({ guest, open, onClose, onSaved }: SiteGuestFormProps) {
  const { t } = useTranslation()
  const isEditing = !!guest

  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [canView, setCanView] = useState(true)
  const [canDownload, setCanDownload] = useState(false)
  const [canUpload, setCanUpload] = useState(false)
  const [expiresAt, setExpiresAt] = useState('')
  const [sendInvitation, setSendInvitation] = useState(true)
  const [isActive, setIsActive] = useState(true)

  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastGuestId, setLastGuestId] = useState<string | null>(null)

  const siteGuestService = useSiteGuestService()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSaving(true)
    setError(null)

    try {
      if (isEditing) {
        const updateData: SiteGuestUpdate = {
          name: name || undefined,
          is_active: isActive,
          can_view: canView,
          can_download: canDownload,
          can_upload: canUpload,
          expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined
        }
        const response = await siteGuestService.updateGuest(guest!.id, updateData)
        if (response.error) {
          setError(response.error)
          return
        }
      } else {
        const createData: SiteGuestCreate = {
          email,
          name: name || undefined,
          can_view: canView,
          can_download: canDownload,
          can_upload: canUpload,
          expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined,
          send_invitation: sendInvitation
        }
        const response = await siteGuestService.createGuest(createData)
        if (response.error) {
          setError(response.error)
          return
        }
      }

      onSaved()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error saving guest')
    } finally {
      setIsSaving(false)
    }
  }

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      onClose()
    }
  }

  // Reset form when guest changes or form opens
  const currentGuestId = guest?.id || null
  if (open && currentGuestId !== lastGuestId) {
    setLastGuestId(currentGuestId)
    if (guest) {
      // Editing existing guest
      setEmail(guest.email)
      setName(guest.name || '')
      setCanView(guest.can_view)
      setCanDownload(guest.can_download)
      setCanUpload(guest.can_upload)
      setExpiresAt(guest.expires_at?.split('T')[0] || '')
      setIsActive(guest.is_active)
    } else {
      // Creating new guest - reset to defaults
      setEmail('')
      setName('')
      setCanView(true)
      setCanDownload(false)
      setCanUpload(false)
      setExpiresAt('')
      setSendInvitation(true)
      setIsActive(true)
    }
    setError(null)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{isEditing ? t('siteGuest.form.editTitle') : t('siteGuest.form.createTitle')}</DialogTitle>
          <DialogDescription>
            {isEditing
              ? t('siteGuest.guests.description')
              : t('siteGuest.description')
            }
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-md">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="email">{t('siteGuest.form.email')} *</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isEditing}
              required
              placeholder={t('siteGuest.form.emailPlaceholder')}
            />
            <p className="text-xs text-muted-foreground">
              {t('siteGuest.form.emailDescription')}
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="name">{t('siteGuest.form.name')}</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('siteGuest.form.namePlaceholder')}
            />
            <p className="text-xs text-muted-foreground">
              {t('siteGuest.form.nameDescription')}
            </p>
          </div>

          <div className="space-y-4">
            <Label>{t('siteGuest.form.globalPermissions')}</Label>
            <p className="text-xs text-muted-foreground -mt-2">
              {t('siteGuest.form.globalPermissionsDescription')}
            </p>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Eye className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm">{t('siteGuest.form.canView')}</span>
                </div>
                <Switch checked={canView} onCheckedChange={setCanView} />
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Download className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm">{t('siteGuest.form.canDownload')}</span>
                </div>
                <Switch checked={canDownload} onCheckedChange={setCanDownload} />
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Upload className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm">{t('siteGuest.form.canUpload')}</span>
                </div>
                <Switch checked={canUpload} onCheckedChange={setCanUpload} />
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="expires">{t('siteGuest.permissionsDialog.expiresAt')}</Label>
            <Input
              id="expires"
              type="date"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              min={new Date().toISOString().split('T')[0]}
            />
            <p className="text-xs text-muted-foreground">
              {t('siteGuest.permissionsDialog.noExpiration')}
            </p>
          </div>

          {isEditing && (
            <div className="flex items-center justify-between pt-2 border-t">
              <div>
                <Label>{t('siteGuest.guests.table.status')}</Label>
                <p className="text-xs text-muted-foreground">
                  {t('siteGuest.toast.guestDeactivated.description')}
                </p>
              </div>
              <Switch checked={isActive} onCheckedChange={setIsActive} />
            </div>
          )}

          {!isEditing && (
            <div className="flex items-center justify-between pt-2 border-t">
              <div>
                <Label>{t('siteGuest.form.sendInvitation')}</Label>
                <p className="text-xs text-muted-foreground">
                  {t('siteGuest.form.sendInvitationDescription')}
                </p>
              </div>
              <Switch checked={sendInvitation} onCheckedChange={setSendInvitation} />
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {isSaving
                ? (isEditing ? t('siteGuest.form.updating') : t('siteGuest.form.creating'))
                : (isEditing ? t('siteGuest.form.update') : t('siteGuest.form.create'))
              }
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

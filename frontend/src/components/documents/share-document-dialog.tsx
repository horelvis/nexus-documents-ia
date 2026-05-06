"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { useTranslation } from "@/lib/i18n/hooks"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "sonner"
import { Copy, Mail, Link, Eye, Download, Lock, Clock, Users, Shield, Loader2 } from "lucide-react"
import { useDocumentShareService } from "@/lib/services/document-share.service"
import type { Document as ApiDocument } from "@/lib/types"

interface ShareDocumentDialogProps {
  document: ApiDocument | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ShareDocumentDialog({
  document,
  open,
  onOpenChange,
}: ShareDocumentDialogProps) {
  const { t } = useTranslation()
  const { createShare } = useDocumentShareService()

  // Share link state
  const [email, setEmail] = useState("")
  const [recipientName, setRecipientName] = useState("")
  const [shareMessage, setShareMessage] = useState("")
  const [shareType, setShareType] = useState<'view' | 'download'>('view')
  const [expirationHours, setExpirationHours] = useState("24")
  const [maxAccessCount, setMaxAccessCount] = useState("")
  const [requirePassword, setRequirePassword] = useState(false)
  const [password, setPassword] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [shareLink, setShareLink] = useState("")
  const [showShareResult, setShowShareResult] = useState(false)

  // Reset form when dialog closes
  useEffect(() => {
    if (!open) {
      setEmail("")
      setRecipientName("")
      setShareMessage("")
      setShareType('view')
      setExpirationHours("24")
      setMaxAccessCount("")
      setRequirePassword(false)
      setPassword("")
      setShareLink("")
      setShowShareResult(false)
    }
  }, [open])

  if (!document) return null

  const createShareLink = async () => {
    if (!document?.id) {
      toast.error(t('shareDialog.toasts.documentIdRequired'))
      return
    }

    if (!createShare) {
      toast.error(t('shareDialog.toasts.serviceNotAvailable'))
      return
    }

    setIsLoading(true)

    try {
      const expiresAt = new Date()
      expiresAt.setHours(expiresAt.getHours() + parseInt(expirationHours))

      const response = await createShare({
        document_id: document.id,
        share_type: shareType,
        expires_at: expiresAt.toISOString(),
        max_access_count: maxAccessCount ? parseInt(maxAccessCount) : undefined,
        password: requirePassword ? password : undefined,
        recipient_email: email || undefined,
        recipient_name: recipientName || undefined,
        share_message: shareMessage || undefined,
      })

      if (response.error) {
        toast.error(response.error)
        return
      }

      if (response.data) {
        setShareLink(response.data.share_url)
        setShowShareResult(true)
        toast.success(t('shareDialog.toasts.linkCreated'))
      }

    } catch (error) {
      console.error('Failed to create share link:', error)
      toast.error(t('shareDialog.toasts.createLinkError'))
    } finally {
      setIsLoading(false)
    }
  }

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(shareLink)
      toast.success(t('shareDialog.toasts.linkCopied'))
    } catch (error) {
      toast.error(t('shareDialog.toasts.copyError'))
    }
  }

  const sendEmail = async () => {
    if (!email) {
      toast.error(t('shareDialog.toasts.enterEmail'))
      return
    }

    if (!shareLink) {
      // Create the share link first
      await createShareLink()
      if (!shareLink) return
    }

    // Use mailto as before, but with the secure share link
    const subject = encodeURIComponent(`Shared Document: ${document.title}`)
    const body = encodeURIComponent(`
${recipientName ? `Hi ${recipientName},` : 'Hello,'}

${shareMessage || `I'm sharing a document with you: "${document.title}"`}

You can ${shareType === 'download' ? 'download' : 'view'} the document using this secure link:
${shareLink}

${requirePassword ? `Password: ${password}` : ''}
${expirationHours ? `This link expires in ${expirationHours} hours.` : ''}
${maxAccessCount ? `Limited to ${maxAccessCount} access${parseInt(maxAccessCount) > 1 ? 'es' : ''}.` : ''}

Best regards
    `.trim())
    
    window.location.href = `mailto:${email}?subject=${subject}&body=${body}`

    toast.success(t('shareDialog.toasts.emailOpened'))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[550px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            {t('shareDialog.title')}
          </DialogTitle>
          <DialogDescription>
            {t('shareDialog.description', { title: document.title })}
          </DialogDescription>
        </DialogHeader>

        {!showShareResult ? (
          <div className="space-y-6">
            {/* Share Type */}
            <div className="space-y-2">
              <Label>{t('shareDialog.linkTab.shareType')}</Label>
              <Select value={shareType} onValueChange={(value: 'view' | 'download') => setShareType(value)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="view">
                    <div className="flex items-center gap-2">
                      <Eye className="h-4 w-4" />
                      {t('shareDialog.linkTab.viewOnly')}
                    </div>
                  </SelectItem>
                  <SelectItem value="download">
                    <div className="flex items-center gap-2">
                      <Download className="h-4 w-4" />
                      {t('shareDialog.linkTab.viewAndDownload')}
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Expiration */}
            <div className="space-y-2">
              <Label className="flex items-center gap-2">
                <Clock className="h-4 w-4" />
                {t('shareDialog.linkTab.linkExpiration')}
              </Label>
              <Select value={expirationHours} onValueChange={setExpirationHours}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">{t('shareDialog.linkTab.hours.1')}</SelectItem>
                  <SelectItem value="6">{t('shareDialog.linkTab.hours.6')}</SelectItem>
                  <SelectItem value="24">{t('shareDialog.linkTab.hours.24')}</SelectItem>
                  <SelectItem value="72">{t('shareDialog.linkTab.hours.72')}</SelectItem>
                  <SelectItem value="168">{t('shareDialog.linkTab.hours.168')}</SelectItem>
                  <SelectItem value="720">{t('shareDialog.linkTab.hours.720')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Access Limit */}
            <div className="space-y-2">
              <Label className="flex items-center gap-2">
                <Users className="h-4 w-4" />
                {t('shareDialog.linkTab.accessLimit')}
              </Label>
              <Input
                type="number"
                placeholder={t('shareDialog.linkTab.accessLimitPlaceholder')}
                value={maxAccessCount}
                onChange={(e) => setMaxAccessCount(e.target.value)}
                min="1"
                max="1000"
              />
              <p className="text-xs text-muted-foreground">
                {t('shareDialog.linkTab.accessLimitHelp')}
              </p>
            </div>

            {/* Password Protection */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="flex items-center gap-2">
                  <Lock className="h-4 w-4" />
                  {t('shareDialog.linkTab.passwordProtection')}
                </Label>
                <Switch
                  checked={requirePassword}
                  onCheckedChange={setRequirePassword}
                />
              </div>
              {requirePassword && (
                <Input
                  type="password"
                  placeholder={t('shareDialog.linkTab.enterPassword')}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              )}
            </div>

            {/* Recipient Info */}
            <div className="space-y-4 border-t pt-4">
              <h4 className="text-sm font-medium">{t('shareDialog.linkTab.recipientInfo')}</h4>

              <div className="space-y-2">
                <Label>{t('shareDialog.linkTab.emailAddress')}</Label>
                <Input
                  type="email"
                  placeholder={t('shareDialog.linkTab.emailPlaceholder')}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label>{t('shareDialog.linkTab.recipientName')}</Label>
                <Input
                  placeholder={t('shareDialog.linkTab.recipientNamePlaceholder')}
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label>{t('shareDialog.linkTab.shareMessage')}</Label>
                <Textarea
                  placeholder={t('shareDialog.linkTab.shareMessagePlaceholder')}
                  value={shareMessage}
                  onChange={(e) => setShareMessage(e.target.value)}
                  rows={3}
                />
              </div>
            </div>

            {/* Create Link Button */}
            <div className="flex gap-2">
              <Button
                onClick={createShareLink}
                disabled={isLoading || (requirePassword && !password)}
                className="flex-1"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {t('shareDialog.linkTab.creating')}
                  </>
                ) : (
                  <>
                    <Link className="mr-2 h-4 w-4" />
                    {t('shareDialog.linkTab.createSecureLink')}
                  </>
                )}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Share Link Result */}
            <div className="space-y-2">
              <Label>{t('shareDialog.linkTab.secureShareLink')}</Label>
              <div className="flex gap-2">
                <Input
                  value={shareLink}
                  readOnly
                  className="flex-1"
                />
                <Button
                  size="icon"
                  variant="outline"
                  onClick={copyToClipboard}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Link Details */}
            <div className="bg-muted/50 p-3 rounded-lg space-y-1 text-sm">
              <p><strong>{t('shareDialog.linkTab.expires')}:</strong> {expirationHours} {t('shareDialog.linkTab.hoursFromNow')}</p>
              {maxAccessCount && <p><strong>{t('shareDialog.linkTab.maxAccess')}:</strong> {maxAccessCount} {t('shareDialog.linkTab.times')}</p>}
              {requirePassword && <p><strong>{t('auth.password')}:</strong> {t('shareDialog.linkTab.protected')}</p>}
              <p><strong>{t('shareDialog.linkTab.type')}:</strong> {shareType === 'view' ? t('shareDialog.linkTab.viewOnly') : t('shareDialog.linkTab.viewAndDownload')}</p>
            </div>

            {/* Send Email */}
            {email && (
              <div className="border-t pt-4">
                <Button
                  onClick={sendEmail}
                  className="w-full"
                  variant="outline"
                >
                  <Mail className="mr-2 h-4 w-4" />
                  {t('shareDialog.linkTab.sendTo', { email })}
                </Button>
              </div>
            )}

            {/* Create Another Link */}
            <Button
              onClick={() => setShowShareResult(false)}
              variant="outline"
              className="w-full"
            >
              {t('shareDialog.linkTab.createAnotherLink')}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
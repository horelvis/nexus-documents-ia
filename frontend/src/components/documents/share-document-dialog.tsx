"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
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
  const { createShare } = useDocumentShareService()
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
      toast.error("Document ID is required")
      return
    }

    if (!createShare) {
      toast.error("Service not available. Please try again.")
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
        toast.success("Secure share link created successfully!")
      }

    } catch (error) {
      console.error('Failed to create share link:', error)
      toast.error("Failed to create share link")
    } finally {
      setIsLoading(false)
    }
  }

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(shareLink)
      toast.success("Secure link copied to clipboard")
    } catch (error) {
      toast.error("Failed to copy link")
    }
  }

  const sendEmail = async () => {
    if (!email) {
      toast.error("Please enter an email address")
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
    
    toast.success("Email client opened with secure share link")
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Share Document Securely
          </DialogTitle>
          <DialogDescription>
            Create a secure, time-limited link for "{document.title}"
          </DialogDescription>
        </DialogHeader>

        {!showShareResult ? (
          <div className="space-y-6">
            {/* Share Type */}
            <div className="space-y-2">
              <Label>Share Type</Label>
              <Select value={shareType} onValueChange={(value: 'view' | 'download') => setShareType(value)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="view">
                    <div className="flex items-center gap-2">
                      <Eye className="h-4 w-4" />
                      View Only
                    </div>
                  </SelectItem>
                  <SelectItem value="download">
                    <div className="flex items-center gap-2">
                      <Download className="h-4 w-4" />
                      View & Download
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Expiration */}
            <div className="space-y-2">
              <Label className="flex items-center gap-2">
                <Clock className="h-4 w-4" />
                Link Expiration
              </Label>
              <Select value={expirationHours} onValueChange={setExpirationHours}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1 Hour</SelectItem>
                  <SelectItem value="6">6 Hours</SelectItem>
                  <SelectItem value="24">24 Hours</SelectItem>
                  <SelectItem value="72">3 Days</SelectItem>
                  <SelectItem value="168">1 Week</SelectItem>
                  <SelectItem value="720">30 Days</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Access Limit */}
            <div className="space-y-2">
              <Label className="flex items-center gap-2">
                <Users className="h-4 w-4" />
                Access Limit (optional)
              </Label>
              <Input
                type="number"
                placeholder="Unlimited"
                value={maxAccessCount}
                onChange={(e) => setMaxAccessCount(e.target.value)}
                min="1"
                max="1000"
              />
              <p className="text-xs text-muted-foreground">
                Maximum number of times the link can be accessed
              </p>
            </div>

            {/* Password Protection */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="flex items-center gap-2">
                  <Lock className="h-4 w-4" />
                  Password Protection
                </Label>
                <Switch
                  checked={requirePassword}
                  onCheckedChange={setRequirePassword}
                />
              </div>
              {requirePassword && (
                <Input
                  type="password"
                  placeholder="Enter password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              )}
            </div>

            {/* Recipient Info */}
            <div className="space-y-4 border-t pt-4">
              <h4 className="text-sm font-medium">Recipient Information (Optional)</h4>
              
              <div className="space-y-2">
                <Label>Email Address</Label>
                <Input
                  type="email"
                  placeholder="recipient@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label>Recipient Name</Label>
                <Input
                  placeholder="John Doe"
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label>Share Message</Label>
                <Textarea
                  placeholder="I'm sharing this document with you..."
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
                    Creating...
                  </>
                ) : (
                  <>
                    <Link className="mr-2 h-4 w-4" />
                    Create Secure Link
                  </>
                )}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Share Link Result */}
            <div className="space-y-2">
              <Label>Secure Share Link</Label>
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
              <p><strong>Expires:</strong> {expirationHours} hours from now</p>
              {maxAccessCount && <p><strong>Max Access:</strong> {maxAccessCount} times</p>}
              {requirePassword && <p><strong>Password:</strong> Protected</p>}
              <p><strong>Type:</strong> {shareType === 'view' ? 'View Only' : 'View & Download'}</p>
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
                  Send to {email}
                </Button>
              </div>
            )}

            {/* Create Another Link */}
            <Button
              onClick={() => setShowShareResult(false)}
              variant="outline"
              className="w-full"
            >
              Create Another Link
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
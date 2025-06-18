"use client"

import { useState } from "react"
import { useParams } from "next/navigation"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Document as ApiDocument } from "@/lib/types"
import { useSharedDocumentsService } from "@/lib/services/shared-documents.service"
import { useNotifications } from "@/contexts/notifications-context"
import { IconLoader2, IconCopy, IconCheck } from "@tabler/icons-react"

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
  const params = useParams()
  const { addNotification } = useNotifications()
  const sharedDocumentsService = useSharedDocumentsService()
  
  const [isCreating, setIsCreating] = useState(false)
  const [shareUrl, setShareUrl] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  
  // Form state
  const [shareType, setShareType] = useState<string>("view")
  const [recipientEmail, setRecipientEmail] = useState("")
  const [recipientName, setRecipientName] = useState("")
  const [message, setMessage] = useState("")
  const [password, setPassword] = useState("")
  const [expiresIn, setExpiresIn] = useState<string>("never")
  const [maxAccessCount, setMaxAccessCount] = useState<string>("")
  const [permissions, setPermissions] = useState({
    view: true,
    download: false,
    edit: false
  })

  const handleClose = () => {
    onOpenChange(false)
    // Reset form after a delay
    setTimeout(() => {
      setShareUrl(null)
      setCopied(false)
      setRecipientEmail("")
      setRecipientName("")
      setMessage("")
      setPassword("")
      setExpiresIn("never")
      setMaxAccessCount("")
      setPermissions({ view: true, download: false, edit: false })
      setShareType("view")
    }, 200)
  }

  const handleCreateShare = async () => {
    if (!document) return
    
    setIsCreating(true)
    
    try {
      // Calculate expiration date
      let expiresAt: string | null = null
      if (expiresIn !== "never") {
        const date = new Date()
        switch (expiresIn) {
          case "1day":
            date.setDate(date.getDate() + 1)
            break
          case "7days":
            date.setDate(date.getDate() + 7)
            break
          case "30days":
            date.setDate(date.getDate() + 30)
            break
        }
        expiresAt = date.toISOString()
      }
      
      const response = await sharedDocumentsService.createShare({
        document_id: document.id,
        share_type: shareType,
        recipient_email: recipientEmail || null,
        recipient_name: recipientName || null,
        share_message: message || null,
        password: password || null,
        expires_at: expiresAt,
        max_access_count: maxAccessCount ? parseInt(maxAccessCount) : null,
        permissions: shareType === "view" ? { view: true, download: false, edit: false } :
                    shareType === "download" ? { view: true, download: true, edit: false } :
                    permissions
      })
      
      if (response.error) {
        addNotification({
          type: 'error',
          title: 'Share Failed',
          message: response.error
        })
      } else if (response.data) {
        setShareUrl(response.data.share_url)
        addNotification({
          type: 'success',
          title: 'Share Created',
          message: recipientEmail 
            ? `Share link sent to ${recipientEmail}`
            : 'Share link created successfully'
        })
      }
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Share Failed',
        message: 'Failed to create share link'
      })
    } finally {
      setIsCreating(false)
    }
  }

  const handleCopyLink = async () => {
    if (!shareUrl) return
    
    try {
      await navigator.clipboard.writeText(shareUrl)
      setCopied(true)
      addNotification({
        type: 'success',
        title: 'Link Copied',
        message: 'Share link copied to clipboard'
      })
      
      // Reset copied state after 2 seconds
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Copy Failed',
        message: 'Failed to copy link to clipboard'
      })
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>Share Document</DialogTitle>
          <DialogDescription>
            Share "{document?.title || document?.filename}" with others
          </DialogDescription>
        </DialogHeader>
        
        {!shareUrl ? (
          <div className="space-y-4 py-4">
            {/* Recipient Email - More prominent */}
            <div className="space-y-2">
              <Label className="text-base font-medium">Send to email</Label>
              <Input
                type="email"
                placeholder="recipient@example.com (optional)"
                value={recipientEmail}
                onChange={(e) => setRecipientEmail(e.target.value)}
                className="text-base"
              />
              <p className="text-xs text-muted-foreground">
                {recipientEmail 
                  ? `The share link will be sent to ${recipientEmail}` 
                  : "Leave empty to generate a link without sending email"}
              </p>
            </div>

            {/* Share Type */}
            <div className="space-y-2">
              <Label>Permissions</Label>
              <Select value={shareType} onValueChange={setShareType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="view">View Only</SelectItem>
                  <SelectItem value="download">View & Download</SelectItem>
                  <SelectItem value="edit">Full Access</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {recipientEmail && (
              <div className="space-y-2">
                <Label>Recipient Name (optional)</Label>
                <Input
                  placeholder="John Doe"
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                />
              </div>
            )}

            {/* Message (optional) */}
            <div className="space-y-2">
              <Label>Message (optional)</Label>
              <Textarea
                placeholder="Add a message for the recipient..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={3}
              />
            </div>

            {/* Password Protection */}
            <div className="space-y-2">
              <Label>Password Protection (optional)</Label>
              <Input
                type="password"
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {/* Expiration */}
            <div className="space-y-2">
              <Label>Link Expiration</Label>
              <Select value={expiresIn} onValueChange={setExpiresIn}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="never">Never</SelectItem>
                  <SelectItem value="1day">1 Day</SelectItem>
                  <SelectItem value="7days">7 Days</SelectItem>
                  <SelectItem value="30days">30 Days</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Access Limit */}
            <div className="space-y-2">
              <Label>Access Limit (optional)</Label>
              <Input
                type="number"
                placeholder="Unlimited"
                value={maxAccessCount}
                onChange={(e) => setMaxAccessCount(e.target.value)}
                min="1"
              />
              {maxAccessCount && (
                <p className="text-xs text-muted-foreground">
                  Link will expire after {maxAccessCount} views
                </p>
              )}
            </div>

            {/* Custom Permissions (for edit type) */}
            {shareType === "edit" && (
              <div className="space-y-2">
                <Label>Permissions</Label>
                <div className="space-y-2">
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="perm-view"
                      checked={permissions.view}
                      disabled
                    />
                    <label htmlFor="perm-view" className="text-sm">
                      View documents
                    </label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="perm-download"
                      checked={permissions.download}
                      onCheckedChange={(checked) => 
                        setPermissions(prev => ({ ...prev, download: !!checked }))
                      }
                    />
                    <label htmlFor="perm-download" className="text-sm">
                      Download documents
                    </label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="perm-edit"
                      checked={permissions.edit}
                      onCheckedChange={(checked) => 
                        setPermissions(prev => ({ ...prev, edit: !!checked }))
                      }
                    />
                    <label htmlFor="perm-edit" className="text-sm">
                      Edit document metadata
                    </label>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4 py-4">
            <div className="rounded-lg bg-muted p-4">
              <p className="text-sm font-medium mb-2">Share link created!</p>
              <div className="flex items-center gap-2">
                <Input
                  value={shareUrl}
                  readOnly
                  className="flex-1"
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCopyLink}
                >
                  {copied ? (
                    <>
                      <IconCheck className="mr-2 h-4 w-4" />
                      Copied
                    </>
                  ) : (
                    <>
                      <IconCopy className="mr-2 h-4 w-4" />
                      Copy
                    </>
                  )}
                </Button>
              </div>
              {recipientEmail && (
                <p className="text-xs text-muted-foreground mt-2">
                  An email with the share link has been sent to {recipientEmail}
                </p>
              )}
            </div>
          </div>
        )}
        
        <DialogFooter>
          {!shareUrl ? (
            <>
              <Button variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button onClick={handleCreateShare} disabled={isCreating}>
                {isCreating ? (
                  <>
                    <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Create Share Link'
                )}
              </Button>
            </>
          ) : (
            <Button onClick={handleClose}>
              Done
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
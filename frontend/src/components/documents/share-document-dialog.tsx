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
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { toast } from "sonner"
import { Copy, Mail, Link, Eye, Download, Lock, Clock, Users, Shield, Loader2, UserPlus, Trash2, Edit, Share2, Globe, X, Check } from "lucide-react"
import { useDocumentShareService } from "@/lib/services/document-share.service"
import { useDocumentACLService } from "@/lib/services/document-acl.service"
import type { Document as ApiDocument, DocumentACL, GranteeType, PermissionSet } from "@/lib/types"

interface ShareDocumentDialogProps {
  document: ApiDocument | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onPermissionsChanged?: () => void
}

export function ShareDocumentDialog({
  document,
  open,
  onOpenChange,
  onPermissionsChanged,
}: ShareDocumentDialogProps) {
  const { createShare } = useDocumentShareService()
  const aclService = useDocumentACLService()

  // Tab state
  const [activeTab, setActiveTab] = useState<'link' | 'users'>('link')

  // Public Link tab state
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

  // User Access tab state
  const [acls, setAcls] = useState<DocumentACL[]>([])
  const [aclsLoading, setAclsLoading] = useState(false)
  const [newUserEmail, setNewUserEmail] = useState("")
  const [newUserPermissions, setNewUserPermissions] = useState<PermissionSet>({
    can_view: true,
    can_edit: false,
    can_delete: false,
    can_share: false,
  })
  const [grantingPermission, setGrantingPermission] = useState(false)
  const [revokingId, setRevokingId] = useState<string | null>(null)
  const [makePublic, setMakePublic] = useState(false)

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
      setActiveTab('link')
      setAcls([])
      setNewUserEmail("")
      setNewUserPermissions({
        can_view: true,
        can_edit: false,
        can_delete: false,
        can_share: false,
      })
      setMakePublic(false)
    }
  }, [open])

  // Load ACLs when switching to users tab
  useEffect(() => {
    if (open && activeTab === 'users' && document?.id) {
      loadAcls()
    }
  }, [open, activeTab, document?.id])

  const loadAcls = async () => {
    if (!document?.id) return

    setAclsLoading(true)
    try {
      const response = await aclService.listDocumentACLs(document.id)
      if (response.error) {
        toast.error(response.error)
      } else if (response.data) {
        setAcls(response.data.acls || [])
        // Check if there's an 'everyone' ACL
        const everyoneAcl = response.data.acls?.find(
          (acl: DocumentACL) => acl.grantee_type === 'everyone'
        )
        setMakePublic(!!everyoneAcl)
      }
    } catch (error) {
      console.error('Failed to load ACLs:', error)
      toast.error("Error loading access permissions")
    } finally {
      setAclsLoading(false)
    }
  }

  const handleGrantPermission = async () => {
    if (!document?.id || !newUserEmail.trim()) {
      toast.error("Please enter an email address")
      return
    }

    setGrantingPermission(true)
    try {
      const response = await aclService.grantPermission(document.id, {
        grantee_type: 'user',
        grantee_id: newUserEmail.trim(), // Backend will resolve email to user ID
        permissions: newUserPermissions,
        source: 'manual',
      })

      if (response.error) {
        toast.error(response.error)
      } else {
        toast.success(`Permission granted to ${newUserEmail}`)
        setNewUserEmail("")
        setNewUserPermissions({
          can_view: true,
          can_edit: false,
          can_delete: false,
          can_share: false,
        })
        await loadAcls()
        onPermissionsChanged?.()
      }
    } catch (error) {
      console.error('Failed to grant permission:', error)
      toast.error("Error granting permission")
    } finally {
      setGrantingPermission(false)
    }
  }

  const handleRevokePermission = async (aclId: string, granteeName?: string) => {
    if (!document?.id) return

    setRevokingId(aclId)
    try {
      const response = await aclService.revokeByACLId(document.id, aclId)
      if (response.error) {
        toast.error(response.error)
      } else {
        toast.success(`Access revoked${granteeName ? ` for ${granteeName}` : ''}`)
        await loadAcls()
        onPermissionsChanged?.()
      }
    } catch (error) {
      console.error('Failed to revoke permission:', error)
      toast.error("Error revoking permission")
    } finally {
      setRevokingId(null)
    }
  }

  const handleTogglePublic = async () => {
    if (!document?.id) return

    setAclsLoading(true)
    try {
      if (makePublic) {
        // Remove public access
        const response = await aclService.makePrivate(document.id)
        if (response.error) {
          toast.error(response.error)
        } else {
          toast.success("Document is now private")
          setMakePublic(false)
          await loadAcls()
          onPermissionsChanged?.()
        }
      } else {
        // Make public to tenant
        const response = await aclService.makePublicInTenant(document.id)
        if (response.error) {
          toast.error(response.error)
        } else {
          toast.success("Document is now visible to all team members")
          setMakePublic(true)
          await loadAcls()
          onPermissionsChanged?.()
        }
      }
    } catch (error) {
      console.error('Failed to toggle public access:', error)
      toast.error("Error updating access")
    } finally {
      setAclsLoading(false)
    }
  }

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

  // Helper to get permission badge
  const getPermissionBadges = (acl: DocumentACL) => {
    const badges = []
    if (acl.can_view) badges.push({ key: 'view', label: 'View', variant: 'secondary' as const })
    if (acl.can_edit) badges.push({ key: 'edit', label: 'Edit', variant: 'default' as const })
    if (acl.can_delete) badges.push({ key: 'delete', label: 'Delete', variant: 'destructive' as const })
    if (acl.can_share) badges.push({ key: 'share', label: 'Share', variant: 'outline' as const })
    return badges
  }

  // Filter out 'everyone' from user list (shown separately)
  const userAcls = acls.filter(acl => acl.grantee_type === 'user')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[550px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Share Document
          </DialogTitle>
          <DialogDescription>
            Manage access for "{document.title}"
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'link' | 'users')}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="link" className="flex items-center gap-2">
              <Link className="h-4 w-4" />
              Public Link
            </TabsTrigger>
            <TabsTrigger value="users" className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              User Access
            </TabsTrigger>
          </TabsList>

          {/* PUBLIC LINK TAB */}
          <TabsContent value="link" className="mt-4">
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
          </TabsContent>

          {/* USER ACCESS TAB */}
          <TabsContent value="users" className="mt-4 space-y-6">
            {aclsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <>
                {/* Public to Team Toggle */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label className="flex items-center gap-2">
                        <Globe className="h-4 w-4" />
                        Visible to Team
                      </Label>
                      <p className="text-xs text-muted-foreground">
                        All team members can view this document
                      </p>
                    </div>
                    <Switch
                      checked={makePublic}
                      onCheckedChange={handleTogglePublic}
                    />
                  </div>
                </div>

                <Separator />

                {/* Add User Section */}
                <div className="space-y-4">
                  <h4 className="text-sm font-medium flex items-center gap-2">
                    <UserPlus className="h-4 w-4" />
                    Grant Access to User
                  </h4>

                  <div className="space-y-3">
                    <div className="space-y-2">
                      <Label>User Email</Label>
                      <Input
                        type="email"
                        placeholder="user@example.com"
                        value={newUserEmail}
                        onChange={(e) => setNewUserEmail(e.target.value)}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label>Permissions</Label>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="flex items-center space-x-2">
                          <Checkbox
                            id="perm-view"
                            checked={newUserPermissions.can_view}
                            onCheckedChange={(checked) =>
                              setNewUserPermissions(prev => ({ ...prev, can_view: !!checked }))
                            }
                          />
                          <label htmlFor="perm-view" className="text-sm flex items-center gap-1.5">
                            <Eye className="h-3.5 w-3.5" />
                            View
                          </label>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Checkbox
                            id="perm-edit"
                            checked={newUserPermissions.can_edit}
                            onCheckedChange={(checked) =>
                              setNewUserPermissions(prev => ({ ...prev, can_edit: !!checked }))
                            }
                          />
                          <label htmlFor="perm-edit" className="text-sm flex items-center gap-1.5">
                            <Edit className="h-3.5 w-3.5" />
                            Edit
                          </label>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Checkbox
                            id="perm-delete"
                            checked={newUserPermissions.can_delete}
                            onCheckedChange={(checked) =>
                              setNewUserPermissions(prev => ({ ...prev, can_delete: !!checked }))
                            }
                          />
                          <label htmlFor="perm-delete" className="text-sm flex items-center gap-1.5">
                            <Trash2 className="h-3.5 w-3.5" />
                            Delete
                          </label>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Checkbox
                            id="perm-share"
                            checked={newUserPermissions.can_share}
                            onCheckedChange={(checked) =>
                              setNewUserPermissions(prev => ({ ...prev, can_share: !!checked }))
                            }
                          />
                          <label htmlFor="perm-share" className="text-sm flex items-center gap-1.5">
                            <Share2 className="h-3.5 w-3.5" />
                            Share
                          </label>
                        </div>
                      </div>
                    </div>

                    <Button
                      onClick={handleGrantPermission}
                      disabled={grantingPermission || !newUserEmail.trim()}
                      className="w-full"
                    >
                      {grantingPermission ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Granting...
                        </>
                      ) : (
                        <>
                          <UserPlus className="mr-2 h-4 w-4" />
                          Grant Access
                        </>
                      )}
                    </Button>
                  </div>
                </div>

                <Separator />

                {/* Current Access List */}
                <div className="space-y-3">
                  <h4 className="text-sm font-medium flex items-center gap-2">
                    <Users className="h-4 w-4" />
                    Current Access ({userAcls.length})
                  </h4>

                  {userAcls.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No users have been granted direct access yet.
                    </p>
                  ) : (
                    <ScrollArea className="h-[200px]">
                      <div className="space-y-2 pr-4">
                        {userAcls.map((acl) => (
                          <div
                            key={acl.id}
                            className="flex items-center justify-between p-3 bg-muted/50 rounded-lg"
                          >
                            <div className="space-y-1">
                              <p className="text-sm font-medium">
                                {acl.grantee_name || acl.grantee_id || 'Unknown User'}
                              </p>
                              <div className="flex flex-wrap gap-1">
                                {getPermissionBadges(acl).map(badge => (
                                  <Badge key={badge.key} variant={badge.variant} className="text-xs">
                                    {badge.label}
                                  </Badge>
                                ))}
                              </div>
                              {acl.expires_at && (
                                <p className="text-xs text-muted-foreground flex items-center gap-1">
                                  <Clock className="h-3 w-3" />
                                  Expires: {new Date(acl.expires_at).toLocaleDateString()}
                                </p>
                              )}
                            </div>
                            <Button
                              size="icon"
                              variant="ghost"
                              onClick={() => handleRevokePermission(acl.id, acl.grantee_name)}
                              disabled={revokingId === acl.id}
                              className="text-destructive hover:text-destructive"
                            >
                              {revokingId === acl.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <X className="h-4 w-4" />
                              )}
                            </Button>
                          </div>
                        ))}
                      </div>
                    </ScrollArea>
                  )}
                </div>
              </>
            )}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
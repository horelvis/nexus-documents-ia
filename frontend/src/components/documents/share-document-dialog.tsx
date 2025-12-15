"use client"

import { useState, useEffect, useCallback } from "react"
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Switch } from "@/components/ui/switch"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { toast } from "sonner"
import { Copy, Mail, Link, Eye, Download, Lock, Clock, Users, Shield, Loader2, UserPlus, Trash2, Edit, Share2, Globe, X, Check, ChevronsUpDown, Search } from "lucide-react"
import { useDocumentShareService } from "@/lib/services/document-share.service"
import { useDocumentACLService } from "@/lib/services/document-acl.service"
import { useTeamService, type TeamMember } from "@/lib/services/team.service"
import type { Document as ApiDocument, DocumentACL, GranteeType, PermissionSet } from "@/lib/types"
import { cn } from "@/lib/utils"

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
  const { t } = useTranslation()
  const { createShare } = useDocumentShareService()
  const aclService = useDocumentACLService()
  const teamService = useTeamService()

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
  const [newUserPermissions, setNewUserPermissions] = useState<PermissionSet>({
    can_view: true,
    can_edit: false,
    can_delete: false,
    can_share: false,
  })
  const [grantingPermission, setGrantingPermission] = useState(false)
  const [revokingId, setRevokingId] = useState<string | null>(null)
  const [makePublic, setMakePublic] = useState(false)

  // User selector state
  const [userSelectorOpen, setUserSelectorOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<TeamMember | null>(null)
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([])
  const [loadingMembers, setLoadingMembers] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")

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
      setSelectedUser(null)
      setSearchQuery("")
      setNewUserPermissions({
        can_view: true,
        can_edit: false,
        can_delete: false,
        can_share: false,
      })
      setMakePublic(false)
    }
  }, [open])

  // Load team members when switching to users tab
  const loadTeamMembers = useCallback(async () => {
    setLoadingMembers(true)
    try {
      const response = await teamService.getTeamMembers()
      if (response.error) {
        console.error('Failed to load team members:', response.error)
      } else if (response.data) {
        setTeamMembers(response.data)
      }
    } catch (error) {
      console.error('Failed to load team members:', error)
    } finally {
      setLoadingMembers(false)
    }
  }, [teamService])

  // Load ACLs for the document
  const loadAcls = useCallback(async () => {
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
  }, [document?.id, aclService])

  // Load ACLs and team members when switching to users tab
  useEffect(() => {
    if (open && activeTab === 'users' && document?.id) {
      loadAcls()
      loadTeamMembers()
    }
  }, [open, activeTab, document?.id, loadAcls, loadTeamMembers])

  const handleGrantPermission = async () => {
    if (!document?.id || !selectedUser) {
      toast.error(t('shareDialog.toasts.selectUser'))
      return
    }

    setGrantingPermission(true)
    try {
      const response = await aclService.grantPermission(document.id, {
        grantee_type: 'user',
        grantee_id: selectedUser.id,
        permissions: newUserPermissions,
        source: 'manual',
      })

      if (response.error) {
        toast.error(response.error)
      } else {
        toast.success(t('shareDialog.toasts.permissionGranted', { name: selectedUser.full_name || selectedUser.email }))
        setSelectedUser(null)
        setSearchQuery("")
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
      toast.error(t('shareDialog.toasts.grantError'))
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
        toast.success(granteeName
          ? t('shareDialog.toasts.accessRevokedFor', { name: granteeName })
          : t('shareDialog.toasts.accessRevoked')
        )
        await loadAcls()
        onPermissionsChanged?.()
      }
    } catch (error) {
      console.error('Failed to revoke permission:', error)
      toast.error(t('shareDialog.toasts.revokeError'))
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
          toast.success(t('shareDialog.toasts.documentPrivate'))
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
          toast.success(t('shareDialog.toasts.documentPublic'))
          setMakePublic(true)
          await loadAcls()
          onPermissionsChanged?.()
        }
      }
    } catch (error) {
      console.error('Failed to toggle public access:', error)
      toast.error(t('shareDialog.toasts.updateAccessError'))
    } finally {
      setAclsLoading(false)
    }
  }

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

  // Helper to get permission badge
  const getPermissionBadges = (acl: DocumentACL) => {
    const badges = []
    if (acl.can_view) badges.push({ key: 'view', label: t('shareDialog.usersTab.view'), variant: 'secondary' as const })
    if (acl.can_edit) badges.push({ key: 'edit', label: t('shareDialog.usersTab.edit'), variant: 'default' as const })
    if (acl.can_delete) badges.push({ key: 'delete', label: t('shareDialog.usersTab.delete'), variant: 'destructive' as const })
    if (acl.can_share) badges.push({ key: 'share', label: t('shareDialog.usersTab.share'), variant: 'outline' as const })
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
            {t('shareDialog.title')}
          </DialogTitle>
          <DialogDescription>
            {t('shareDialog.description', { title: document.title })}
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'link' | 'users')}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="link" className="flex items-center gap-2">
              <Link className="h-4 w-4" />
              {t('shareDialog.tabs.publicLink')}
            </TabsTrigger>
            <TabsTrigger value="users" className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              {t('shareDialog.tabs.userAccess')}
            </TabsTrigger>
          </TabsList>

          {/* PUBLIC LINK TAB */}
          <TabsContent value="link" className="mt-4">
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
                        {t('shareDialog.usersTab.visibleToTeam')}
                      </Label>
                      <p className="text-xs text-muted-foreground">
                        {t('shareDialog.usersTab.visibleToTeamDesc')}
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
                    {t('shareDialog.usersTab.grantAccess')}
                  </h4>

                  <div className="space-y-3">
                    <div className="space-y-2">
                      <Label>{t('shareDialog.usersTab.selectTeamUser')}</Label>
                      <Popover open={userSelectorOpen} onOpenChange={setUserSelectorOpen}>
                        <PopoverTrigger asChild>
                          <Button
                            variant="outline"
                            role="combobox"
                            aria-expanded={userSelectorOpen}
                            className="w-full justify-between"
                          >
                            {selectedUser ? (
                              <div className="flex items-center gap-2">
                                <Avatar className="h-6 w-6">
                                  <AvatarFallback className="text-xs">
                                    {(selectedUser.full_name || selectedUser.email).substring(0, 2).toUpperCase()}
                                  </AvatarFallback>
                                </Avatar>
                                <span className="truncate">
                                  {selectedUser.full_name || selectedUser.email}
                                </span>
                              </div>
                            ) : (
                              <span className="text-muted-foreground">{t('shareDialog.usersTab.searchUser')}</span>
                            )}
                            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-[350px] p-0" align="start">
                          <Command>
                            <CommandInput
                              placeholder={t('shareDialog.usersTab.searchByNameOrEmail')}
                              value={searchQuery}
                              onValueChange={setSearchQuery}
                            />
                            <CommandList>
                              {loadingMembers ? (
                                <div className="flex items-center justify-center py-6">
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                </div>
                              ) : teamMembers.length === 0 ? (
                                <CommandEmpty>{t('shareDialog.usersTab.noUsersFound')}</CommandEmpty>
                              ) : (
                                <CommandGroup>
                                  {teamMembers
                                    .filter(member => {
                                      if (!searchQuery) return true
                                      const query = searchQuery.toLowerCase()
                                      return (
                                        member.email.toLowerCase().includes(query) ||
                                        (member.full_name?.toLowerCase().includes(query))
                                      )
                                    })
                                    .filter(member => {
                                      // Exclude users that already have ACLs
                                      return !acls.some(acl =>
                                        acl.grantee_type === 'user' && acl.grantee_id === member.id
                                      )
                                    })
                                    .map((member) => (
                                      <CommandItem
                                        key={member.id}
                                        value={member.email}
                                        onSelect={() => {
                                          setSelectedUser(member)
                                          setUserSelectorOpen(false)
                                        }}
                                      >
                                        <div className="flex items-center gap-3 w-full">
                                          <Avatar className="h-8 w-8">
                                            <AvatarFallback>
                                              {(member.full_name || member.email).substring(0, 2).toUpperCase()}
                                            </AvatarFallback>
                                          </Avatar>
                                          <div className="flex-1 overflow-hidden">
                                            <p className="text-sm font-medium truncate">
                                              {member.full_name || t('shareDialog.usersTab.noName')}
                                            </p>
                                            <p className="text-xs text-muted-foreground truncate">
                                              {member.email}
                                            </p>
                                          </div>
                                          <Badge variant="secondary" className="text-xs">
                                            {member.role}
                                          </Badge>
                                          {selectedUser?.id === member.id && (
                                            <Check className="h-4 w-4 text-primary" />
                                          )}
                                        </div>
                                      </CommandItem>
                                    ))}
                                </CommandGroup>
                              )}
                            </CommandList>
                          </Command>
                        </PopoverContent>
                      </Popover>
                    </div>

                    <div className="space-y-2">
                      <Label>{t('shareDialog.usersTab.permissions')}</Label>
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
                            {t('shareDialog.usersTab.view')}
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
                            {t('shareDialog.usersTab.edit')}
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
                            {t('shareDialog.usersTab.delete')}
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
                            {t('shareDialog.usersTab.share')}
                          </label>
                        </div>
                      </div>
                    </div>

                    <Button
                      onClick={handleGrantPermission}
                      disabled={grantingPermission || !selectedUser}
                      className="w-full"
                    >
                      {grantingPermission ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          {t('shareDialog.usersTab.granting')}
                        </>
                      ) : (
                        <>
                          <UserPlus className="mr-2 h-4 w-4" />
                          {t('shareDialog.usersTab.grantAccessBtn')}
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
                    {t('shareDialog.usersTab.currentAccess', { count: userAcls.length })}
                  </h4>

                  {userAcls.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      {t('shareDialog.usersTab.noDirectAccess')}
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
                                {acl.grantee_name || acl.grantee_id || t('shareDialog.usersTab.unknownUser')}
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
                                  {t('shareDialog.usersTab.expiresOn', { date: new Date(acl.expires_at).toLocaleDateString() })}
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
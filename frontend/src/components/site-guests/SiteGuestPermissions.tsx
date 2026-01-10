"use client"

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import {
  useSiteGuestService, SiteGuest, SiteGuestPermission
} from '@/lib/services/site-guest.service'
import { Loader2, Plus, Trash2, File, Folder, Eye, Download, Upload, FolderOpen } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { es, enUS, fr } from 'date-fns/locale'
import { useTranslation } from '@/lib/i18n/hooks'
import { DocumentPickerDialog, SelectedItem } from '@/components/documents/document-picker-dialog'

interface SiteGuestPermissionsProps {
  guest: SiteGuest
  open: boolean
  onClose: () => void
}

type PermissionType = 'view' | 'download' | 'upload'

export function SiteGuestPermissions({ guest, open, onClose }: SiteGuestPermissionsProps) {
  const { t, language } = useTranslation()
  const [permissions, setPermissions] = useState<SiteGuestPermission[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Document picker
  const [showDocumentPicker, setShowDocumentPicker] = useState(false)
  const [selectedItems, setSelectedItems] = useState<SelectedItem[]>([])
  const [permissionType, setPermissionType] = useState<PermissionType>('view')
  const [expiresAt, setExpiresAt] = useState('')
  const [isAdding, setIsAdding] = useState(false)

  const siteGuestService = useSiteGuestService()

  // Get date-fns locale based on current language
  const getDateLocale = () => {
    switch (language) {
      case 'es': return es
      case 'fr': return fr
      default: return enUS
    }
  }

  const loadPermissions = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await siteGuestService.listGuestPermissions(guest.id)
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setPermissions(response.data.permissions)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error loading permissions')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (open && guest) {
      loadPermissions()
    }
  }, [open, guest])

  const handleDocumentPickerConfirm = (items: SelectedItem[]) => {
    setSelectedItems(items)
    setShowDocumentPicker(false)
  }

  const handleAddPermissions = async () => {
    if (selectedItems.length === 0) return

    setIsAdding(true)
    setError(null)

    let successCount = 0
    let errorCount = 0

    try {
      for (const item of selectedItems) {
        let response

        if (item.type === 'folder') {
          response = await siteGuestService.grantFolderPermission(guest.id, {
            folder_path: item.path || item.id,
            permission_type: permissionType,
            expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined
          })
        } else {
          response = await siteGuestService.grantDocumentPermission(guest.id, {
            document_id: item.id,
            permission_type: permissionType,
            expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined
          })
        }

        if (response.error) {
          errorCount++
        } else {
          successCount++
        }
      }

      if (errorCount > 0) {
        setError(`${successCount} permissions granted, ${errorCount} failed`)
      }

      // Reset form
      setSelectedItems([])
      setPermissionType('view')
      setExpiresAt('')
      loadPermissions()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error adding permissions')
    } finally {
      setIsAdding(false)
    }
  }

  const removeSelectedItem = (index: number) => {
    setSelectedItems(prev => prev.filter((_, i) => i !== index))
  }

  const handleRevokePermission = async (permission: SiteGuestPermission) => {
    if (!confirm('Are you sure you want to revoke this permission?')) return

    try {
      const response = await siteGuestService.revokePermission(guest.id, permission.id)
      if (response.error) {
        alert(`Error: ${response.error}`)
      } else {
        loadPermissions()
      }
    } catch (err) {
      alert('Failed to revoke permission')
    }
  }

  const getPermissionIcon = (type: string) => {
    switch (type) {
      case 'view': return <Eye className="h-4 w-4" />
      case 'download': return <Download className="h-4 w-4" />
      case 'upload': return <Upload className="h-4 w-4" />
      default: return null
    }
  }

  const getPermissionBadge = (type: string) => {
    const colors: Record<string, string> = {
      view: 'bg-blue-100 text-blue-800',
      download: 'bg-green-100 text-green-800',
      upload: 'bg-purple-100 text-purple-800'
    }
    return (
      <Badge variant="secondary" className={colors[type] || ''}>
        {getPermissionIcon(type)}
        <span className="ml-1 capitalize">{type}</span>
      </Badge>
    )
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-[700px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('siteGuest.permissionsDialog.title').replace('{name}', guest.name || guest.email)}</DialogTitle>
          <DialogDescription>
            {t('siteGuest.permissionsDialog.description')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {error && (
            <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-md">
              {error}
            </div>
          )}

          {/* Add Permission Form - Microsoft SharePoint Style */}
          <div className="p-4 border rounded-lg space-y-4 bg-muted/50">
            {/* Step 1: Select documents/folders */}
            <div>
              <Label className="text-sm font-medium mb-2 block">
                {t('siteGuest.permissionsDialog.selectDocuments') || '1. Select documents or folders'}
              </Label>
              <Button
                variant="outline"
                onClick={() => setShowDocumentPicker(true)}
                className="w-full justify-start"
              >
                <FolderOpen className="h-4 w-4 mr-2" />
                {t('siteGuest.permissionsDialog.browseDocuments') || 'Browse Documents...'}
              </Button>

              {/* Selected items preview */}
              {selectedItems.length > 0 && (
                <div className="mt-3 space-y-2">
                  <div className="text-sm text-muted-foreground">
                    {selectedItems.length} {t('siteGuest.permissionsDialog.itemsSelected') || 'items selected'}:
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selectedItems.map((item, index) => (
                      <Badge
                        key={`${item.type}:${item.id}`}
                        variant="secondary"
                        className="flex items-center gap-1 pr-1"
                      >
                        {item.type === 'folder' ? (
                          <Folder className="h-3 w-3" />
                        ) : (
                          <File className="h-3 w-3" />
                        )}
                        <span className="max-w-[150px] truncate">{item.name}</span>
                        <button
                          onClick={() => removeSelectedItem(index)}
                          className="ml-1 p-0.5 rounded hover:bg-muted"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Step 2: Permission type */}
            <div className="flex gap-4">
              <div className="flex-1">
                <Label className="text-sm font-medium mb-2 block">
                  {t('siteGuest.permissionsDialog.permissionTypeLabel') || '2. Permission type'}
                </Label>
                <Select value={permissionType} onValueChange={(v) => setPermissionType(v as PermissionType)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="view">
                      <div className="flex items-center gap-2">
                        <Eye className="h-4 w-4" />
                        {t('siteGuest.guests.permissions.view') || 'View only'}
                      </div>
                    </SelectItem>
                    <SelectItem value="download">
                      <div className="flex items-center gap-2">
                        <Download className="h-4 w-4" />
                        {t('siteGuest.guests.permissions.download') || 'Download'}
                      </div>
                    </SelectItem>
                    <SelectItem value="upload">
                      <div className="flex items-center gap-2">
                        <Upload className="h-4 w-4" />
                        {t('siteGuest.guests.permissions.upload') || 'Upload'}
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex-1">
                <Label className="text-sm font-medium mb-2 block">
                  {t('siteGuest.permissionsDialog.expiresAtLabel') || '3. Expires (optional)'}
                </Label>
                <Input
                  type="date"
                  value={expiresAt}
                  onChange={(e) => setExpiresAt(e.target.value)}
                  min={new Date().toISOString().split('T')[0]}
                />
              </div>
            </div>

            {/* Grant button */}
            <div className="flex justify-end">
              <Button
                onClick={handleAddPermissions}
                disabled={isAdding || selectedItems.length === 0}
              >
                {isAdding && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {isAdding
                  ? t('siteGuest.permissionsDialog.granting') || 'Granting...'
                  : `${t('siteGuest.permissionsDialog.grant') || 'Grant'} ${selectedItems.length > 0 ? `(${selectedItems.length})` : ''}`
                }
              </Button>
            </div>
          </div>

          {/* Permissions List */}
          {isLoading ? (
            <div className="text-center py-8">
              <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
              <p className="text-muted-foreground">{t('common.loading')}</p>
            </div>
          ) : permissions.length === 0 ? (
            <div className="text-center py-8 border rounded-lg">
              <p className="text-muted-foreground">
                {t('siteGuest.permissionsDialog.noPermissions.description')}
              </p>
            </div>
          ) : (
            <div className="border rounded-lg">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('siteGuest.permissionsDialog.table.type')}</TableHead>
                    <TableHead>{t('siteGuest.permissionsDialog.table.resource')}</TableHead>
                    <TableHead>{t('siteGuest.permissionsDialog.table.permission')}</TableHead>
                    <TableHead>{t('siteGuest.permissionsDialog.grantedAt')}</TableHead>
                    <TableHead>{t('siteGuest.permissionsDialog.table.expires')}</TableHead>
                    <TableHead className="w-[50px]"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {permissions.map((permission) => (
                    <TableRow key={permission.id}>
                      <TableCell>
                        {permission.document_id ? (
                          <div className="flex items-center gap-2">
                            <File className="h-4 w-4 text-muted-foreground" />
                            {t('siteGuest.permissionsDialog.resourceType.document')}
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <Folder className="h-4 w-4 text-muted-foreground" />
                            {t('siteGuest.permissionsDialog.resourceType.folder')}
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate">
                        {permission.document_id ? (
                          <span title={permission.document_id}>
                            {permission.document_title || permission.document_filename || permission.document_id}
                          </span>
                        ) : (
                          <code className="text-xs">{permission.folder_path}</code>
                        )}
                      </TableCell>
                      <TableCell>
                        {getPermissionBadge(permission.permission_type)}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {formatDistanceToNow(new Date(permission.granted_at), { addSuffix: true, locale: getDateLocale() })}
                      </TableCell>
                      <TableCell className="text-sm">
                        {permission.expires_at ? (
                          new Date(permission.expires_at) < new Date() ? (
                            <Badge variant="destructive">{t('common.expired') || 'Expired'}</Badge>
                          ) : (
                            formatDistanceToNow(new Date(permission.expires_at), { addSuffix: true, locale: getDateLocale() })
                          )
                        ) : (
                          <span className="text-muted-foreground">{t('siteGuest.permissionsDialog.noExpiration')}</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRevokePermission(permission)}
                          title={t('siteGuest.permissionsDialog.revoke')}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('common.close')}
          </Button>
        </DialogFooter>
      </DialogContent>

      {/* Document Picker Dialog */}
      <DocumentPickerDialog
        open={showDocumentPicker}
        onClose={() => setShowDocumentPicker(false)}
        onConfirm={handleDocumentPickerConfirm}
        title={t('siteGuest.permissionsDialog.selectDocumentsTitle') || 'Select Documents'}
        description={t('siteGuest.permissionsDialog.selectDocumentsDescription') || 'Browse and select documents or folders to share with this guest'}
        multiSelect={true}
        allowFolders={true}
        allowDocuments={true}
      />
    </Dialog>
  )
}

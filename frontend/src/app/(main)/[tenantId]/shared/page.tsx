"use client"

import { useState, useEffect } from "react"
import { useParams } from "next/navigation"
import { 
  IconShare2, 
  IconSearch,
  IconFilter,
  IconLoader2,
  IconAlertCircle,
  IconCheck,
  IconInfoCircle,
  IconEye
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useNotifications } from "@/contexts/notifications-context"
import { useSharedDocumentsService, SharedDocument } from "@/lib/services/shared-documents.service"
import { Skeleton } from "@/components/ui/skeleton"
import { SharedDocumentsDataTable } from "@/components/shared/shared-documents-data-table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert"

export default function SharedDocumentsPage() {
  const params = useParams()
  const tenantId = params.tenantId as string

  const [sharedDocuments, setSharedDocuments] = useState<SharedDocument[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [totalShares, setTotalShares] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  
  // Dialog states
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [revokeDialogOpen, setRevokeDialogOpen] = useState(false)
  const [selectedShare, setSelectedShare] = useState<SharedDocument | null>(null)
  const [editPermissions, setEditPermissions] = useState<string[]>([])
  const [editExpiresAt, setEditExpiresAt] = useState<string>('')
  
  const { addNotification } = useNotifications()
  const sharedDocumentsService = useSharedDocumentsService()

  // Load shared documents
  const loadSharedDocuments = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await sharedDocumentsService.getSharedDocuments({
        page: currentPage,
        per_page: 10,
        is_active: selectedFilter === 'all' ? undefined : selectedFilter === 'active'
      })
      
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        // Filter by search query on client side if provided
        let shares = response.data.shares
        if (searchQuery) {
          shares = shares.filter(share => 
            share.document_title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
            share.document_filename?.toLowerCase().includes(searchQuery.toLowerCase()) ||
            share.recipient_email?.toLowerCase().includes(searchQuery.toLowerCase()) ||
            share.recipient_name?.toLowerCase().includes(searchQuery.toLowerCase())
          )
        }
        setSharedDocuments(shares)
        setTotalShares(response.data.total)
        setTotalPages(Math.ceil(response.data.total / response.data.per_page))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load shared documents')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadSharedDocuments()
  }, [currentPage, selectedFilter])

  // Search on Enter key
  const handleSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      setCurrentPage(1)
      loadSharedDocuments()
    }
  }

  // Copy share link
  const handleCopyLink = async (share: SharedDocument) => {
    try {
      await navigator.clipboard.writeText(share.share_url)
      addNotification({
        type: 'success',
        title: 'Link Copied',
        message: 'Share link copied to clipboard'
      })
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Copy Failed',
        message: 'Failed to copy link to clipboard'
      })
    }
  }

  // Open share link
  const handleOpenLink = (share: SharedDocument) => {
    window.open(share.share_url, '_blank')
  }

  // Edit share
  const handleEditShare = (share: SharedDocument) => {
    setSelectedShare(share)
    // Convert permissions object to array of strings for UI
    const perms = share.permissions || {}
    const permArray: string[] = []
    if (perms.view !== false) permArray.push('view')
    if (perms.download) permArray.push('download')
    if (perms.edit) permArray.push('edit')
    setEditPermissions(permArray.length > 0 ? permArray : ['view'])
    setEditExpiresAt(share.expires_at?.split('T')[0] || '')
    setEditDialogOpen(true)
  }

  // Save edit
  const handleSaveEdit = async () => {
    if (!selectedShare) return
    
    try {
      // Convert permissions array back to object
      const permissionsObj: Record<string, boolean> = {
        view: editPermissions.includes('view'),
        download: editPermissions.includes('download'),
        edit: editPermissions.includes('edit')
      }
      
      const response = await sharedDocumentsService.updateShare(selectedShare.id, {
        permissions: permissionsObj,
        expires_at: editExpiresAt || null
      })
      
      if (response.error) {
        addNotification({
          type: 'error',
          title: 'Update Failed',
          message: response.error
        })
      } else {
        addNotification({
          type: 'success',
          title: 'Share Updated',
          message: 'Share permissions have been updated successfully'
        })
        loadSharedDocuments()
        setEditDialogOpen(false)
      }
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Update Failed',
        message: 'Failed to update share permissions'
      })
    }
  }

  // Revoke share
  const handleRevokeShare = (share: SharedDocument) => {
    setSelectedShare(share)
    setRevokeDialogOpen(true)
  }

  // Confirm revoke
  const handleConfirmRevoke = async () => {
    if (!selectedShare) return
    
    try {
      const response = await sharedDocumentsService.revokeShare(selectedShare.id)
      
      if (response.error) {
        addNotification({
          type: 'error',
          title: 'Revoke Failed',
          message: response.error
        })
      } else {
        addNotification({
          type: 'success',
          title: 'Access Revoked',
          message: 'Document access has been revoked successfully'
        })
        loadSharedDocuments()
        setRevokeDialogOpen(false)
      }
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Revoke Failed',
        message: 'Failed to revoke document access'
      })
    }
  }

  // Calculate stats
  const activeShares = sharedDocuments.filter(d => d.is_active && (!d.expires_at || new Date(d.expires_at) > new Date())).length
  const totalViews = sharedDocuments.reduce((sum, d) => sum + d.current_access_count, 0)
  const expiringSoon = sharedDocuments.filter(d => {
    if (!d.expires_at || !d.is_active) return false
    const daysUntilExpiry = Math.ceil((new Date(d.expires_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
    return daysUntilExpiry <= 7 && daysUntilExpiry > 0
  }).length

  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
          <div>
            <h1 className="text-3xl font-bold mb-2">Shared Documents</h1>
            <p className="text-muted-foreground">
              Manage documents shared with external parties
            </p>
          </div>
        </div>

        {/* Info Alert */}
        <Alert className="mb-6">
          <IconInfoCircle className="h-4 w-4" />
          <AlertTitle>Share documents from the library</AlertTitle>
          <AlertDescription>
            To share a document, go to the Document Library or Search page and use the share option on any document.
          </AlertDescription>
        </Alert>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <IconShare2 className="h-8 w-8 text-blue-500" />
                <div className="ml-3">
                  <p className="text-sm font-medium text-muted-foreground">Total Shared</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? <Skeleton className="h-8 w-12" /> : totalShares}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <IconCheck className="h-8 w-8 text-green-500" />
                <div className="ml-3">
                  <p className="text-sm font-medium text-muted-foreground">Active Links</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? <Skeleton className="h-8 w-12" /> : activeShares}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <IconEye className="h-8 w-8 text-purple-500" />
                <div className="ml-3">
                  <p className="text-sm font-medium text-muted-foreground">Total Views</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? <Skeleton className="h-8 w-12" /> : totalViews}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center">
                <IconAlertCircle className="h-8 w-8 text-orange-500" />
                <div className="ml-3">
                  <p className="text-sm font-medium text-muted-foreground">Expiring Soon</p>
                  <p className="text-2xl font-bold">
                    {isLoading ? <Skeleton className="h-8 w-12" /> : expiringSoon}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Search and Filter */}
        <Card className="mb-6">
          <CardContent className="p-6">
            <div className="flex flex-col sm:flex-row gap-4">
              <div className="flex-1 flex gap-2">
                <div className="flex-1 relative">
                  <IconSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
                  <Input
                    placeholder="Search by document name or recipient..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={handleSearch}
                    className="pl-10"
                  />
                </div>
                <Button onClick={loadSharedDocuments} variant="outline">
                  Search
                </Button>
              </div>
              
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline">
                    <IconFilter className="mr-2 h-4 w-4" />
                    Filter: {selectedFilter === 'all' ? 'All' : selectedFilter.charAt(0).toUpperCase() + selectedFilter.slice(1)}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  <DropdownMenuItem onClick={() => setSelectedFilter('all')}>
                    All Documents
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setSelectedFilter('active')}>
                    Active
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setSelectedFilter('inactive')}>
                    Inactive
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </CardContent>
        </Card>

        {/* Loading State */}
        {isLoading && (
          <div className="flex justify-center items-center py-12">
            <IconLoader2 className="h-8 w-8 animate-spin text-purple-600 dark:text-purple-400" />
            <span className="ml-2">Loading shared documents...</span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <Card className="text-center py-12">
            <CardContent>
              <p className="text-red-600 mb-4">{error}</p>
              <Button onClick={loadSharedDocuments} variant="outline">
                Try Again
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Shared Documents Table */}
        {!isLoading && !error && (
          <Card>
            <CardContent className="p-6">
              <SharedDocumentsDataTable
                data={sharedDocuments}
                onCopyLink={handleCopyLink}
                onOpenLink={handleOpenLink}
                onEditShare={handleEditShare}
                onRevokeShare={handleRevokeShare}
              />
            </CardContent>
          </Card>
        )}
        
        {!isLoading && !error && sharedDocuments.length === 0 && (
          <Card className="text-center py-12">
            <CardContent>
              <IconShare2 className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">No shared documents found</h3>
              <p className="text-muted-foreground mb-4">
                {searchQuery || selectedFilter !== 'all' 
                  ? 'Try adjusting your search or filter criteria.'
                  : 'Go to the Document Library to share your first document.'
                }
              </p>
            </CardContent>
          </Card>
        )}

        {/* Edit Permissions Dialog */}
        <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Edit Share Permissions</DialogTitle>
              <DialogDescription>
                Update permissions and expiration for this shared document
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Document</Label>
                <p className="text-sm text-muted-foreground">{selectedShare?.document_title || selectedShare?.document_filename}</p>
              </div>
              
              <div className="space-y-2">
                <Label>Permissions</Label>
                <div className="space-y-2">
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="view"
                      checked={editPermissions.includes('view')}
                      onCheckedChange={(checked) => {
                        if (checked) {
                          setEditPermissions([...editPermissions, 'view'])
                        } else {
                          setEditPermissions(editPermissions.filter(p => p !== 'view'))
                        }
                      }}
                    />
                    <label htmlFor="view" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                      View documents
                    </label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="download"
                      checked={editPermissions.includes('download')}
                      onCheckedChange={(checked) => {
                        if (checked) {
                          setEditPermissions([...editPermissions, 'download'])
                        } else {
                          setEditPermissions(editPermissions.filter(p => p !== 'download'))
                        }
                      }}
                    />
                    <label htmlFor="download" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                      Download documents
                    </label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="edit"
                      checked={editPermissions.includes('edit')}
                      onCheckedChange={(checked) => {
                        if (checked) {
                          setEditPermissions([...editPermissions, 'edit'])
                        } else {
                          setEditPermissions(editPermissions.filter(p => p !== 'edit'))
                        }
                      }}
                    />
                    <label htmlFor="edit" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                      Edit documents
                    </label>
                  </div>
                </div>
              </div>
              
              <div>
                <Label>Expiration Date</Label>
                <Input 
                  type="date" 
                  value={editExpiresAt}
                  onChange={(e) => setEditExpiresAt(e.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
                Cancel
              </Button>
              <Button onClick={handleSaveEdit}>
                Save Changes
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Revoke Access Dialog */}
        <Dialog open={revokeDialogOpen} onOpenChange={setRevokeDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Revoke Document Access</DialogTitle>
              <DialogDescription>
                Are you sure you want to revoke access to this document? This action cannot be undone.
              </DialogDescription>
            </DialogHeader>
            <div className="py-4">
              <p className="font-medium">{selectedShare?.document_title || selectedShare?.document_filename}</p>
              <p className="text-sm text-muted-foreground mt-1">
                Shared with: {selectedShare?.recipient_email || selectedShare?.recipient_name || 'Public link'}
              </p>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setRevokeDialogOpen(false)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={handleConfirmRevoke}>
                Revoke Access
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

      </div>
    </div>
  )
}
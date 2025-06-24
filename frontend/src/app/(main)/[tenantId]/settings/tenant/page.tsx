"use client"

import { useState, useEffect } from "react"
import { useParams } from "next/navigation"
import { 
  IconDatabase, 
  IconRefresh, 
  IconTrash, 
  IconAlertTriangle,
  IconLoader2,
  IconCheck,
  IconX,
  IconInfoCircle,
  IconDownload,
  IconTool
} from "@tabler/icons-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { useUser } from "@/contexts/user-context"
import { useNotifications } from "@/contexts/app-state-context"
import { useTenantService } from "@/lib/services/tenant.service"
import { formatBytes } from "@/lib/utils"

export default function TenantSettingsPage() {
  const params = useParams()
  const tenantId = params.tenantId as string
  const { user } = useUser()
  const { addNotification } = useNotifications()
  const tenantService = useTenantService()

  // States
  const [isLoading, setIsLoading] = useState(true)
  const [tenantInfo, setTenantInfo] = useState<any>(null)
  const [tenantStats, setTenantStats] = useState<any>(null)
  const [reindexStatus, setReindexStatus] = useState<any>(null)
  const [isReindexing, setIsReindexing] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteConfirmText, setDeleteConfirmText] = useState("")
  const [isDeleting, setIsDeleting] = useState(false)
  const [activeTab, setActiveTab] = useState("general")

  // Check if user is admin
  const isAdmin = user?.is_superuser || false

  // Load initial data
  useEffect(() => {
    loadTenantData()
  }, [])

  const loadTenantData = async () => {
    setIsLoading(true)
    try {
      const [infoResponse, statsResponse, indexResponse] = await Promise.all([
        tenantService.getCurrentTenant(),
        tenantService.getTenantStats(),
        tenantService.getReindexStatus()
      ])

      if (!infoResponse.error) setTenantInfo(infoResponse.data)
      if (!statsResponse.error) setTenantStats(statsResponse.data)
      if (!indexResponse.error) setReindexStatus(indexResponse.data)
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Error loading tenant data',
        message: 'Failed to load tenant information'
      })
    } finally {
      setIsLoading(false)
    }
  }

  // Reindex operations
  const handleReindexMissing = async () => {
    setIsReindexing(true)
    try {
      const response = await tenantService.reindexMissingDocuments()
      
      if (response.error) {
        throw new Error(response.error)
      }

      addNotification({
        type: 'success',
        title: 'Reindexing completed',
        message: `Successfully reindexed ${response.data?.successful || 0} documents`
      })

      // Reload status
      const statusResponse = await tenantService.getReindexStatus()
      if (!statusResponse.error) setReindexStatus(statusResponse.data)
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Reindexing failed',
        message: error.message || 'Failed to reindex documents'
      })
    } finally {
      setIsReindexing(false)
    }
  }

  const handleForceReindex = async () => {
    if (!confirm('This will reindex ALL documents and may take a long time. Continue?')) {
      return
    }

    setIsReindexing(true)
    try {
      const response = await tenantService.forceReindexAll()
      
      if (response.error) {
        throw new Error(response.error)
      }

      addNotification({
        type: 'success',
        title: 'Reindexing started',
        message: 'Full reindexing has been started in the background'
      })
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Failed to start reindexing',
        message: error.message || 'Failed to start reindexing process'
      })
    } finally {
      setIsReindexing(false)
    }
  }

  // Delete operations
  const handleDeleteAllDocuments = async () => {
    if (deleteConfirmText !== "DELETE ALL DOCUMENTS") return

    setIsDeleting(true)
    try {
      const response = await tenantService.deleteAllDocuments()
      
      if (response.error) {
        throw new Error(response.error)
      }

      addNotification({
        type: 'success',
        title: 'Documents deleted',
        message: `Deleted ${response.data?.deleted_count || 0} documents`
      })

      setDeleteDialogOpen(false)
      setDeleteConfirmText("")
      
      // Reload stats
      loadTenantData()
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Deletion failed',
        message: error.message || 'Failed to delete documents'
      })
    } finally {
      setIsDeleting(false)
    }
  }

  const handleClearVectorDB = async () => {
    if (!confirm('This will clear all vector embeddings. Documents will need to be reindexed. Continue?')) {
      return
    }

    setIsDeleting(true)
    try {
      const response = await tenantService.clearVectorDatabase()
      
      if (response.error) {
        throw new Error(response.error)
      }

      addNotification({
        type: 'success',
        title: 'Vector database cleared',
        message: 'All vector embeddings have been removed'
      })

      // Reload status
      loadTenantData()
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Clear failed',
        message: error.message || 'Failed to clear vector database'
      })
    } finally {
      setIsDeleting(false)
    }
  }

  // Maintenance operations
  const handleRunMaintenance = async () => {
    setIsLoading(true)
    try {
      const response = await tenantService.runMaintenance()
      
      if (response.error) {
        throw new Error(response.error)
      }

      addNotification({
        type: 'success',
        title: 'Maintenance completed',
        message: `Performed ${response.data?.operations_performed?.length || 0} operations in ${response.data?.duration_seconds || 0}s`
      })
    } catch (error) {
      addNotification({
        type: 'error',
        title: 'Maintenance failed',
        message: error.message || 'Failed to run maintenance'
      })
    } finally {
      setIsLoading(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <IconLoader2 className="h-8 w-8 animate-spin" />
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="p-6">
        <Alert>
          <IconAlertTriangle className="h-4 w-4" />
          <AlertTitle>Access Denied</AlertTitle>
          <AlertDescription>
            Only administrators can access tenant settings.
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="container max-w-6xl py-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Tenant Settings</h1>
        <p className="text-muted-foreground">
          Manage your organization's data and system settings
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="indexing">Search Index</TabsTrigger>
          <TabsTrigger value="data">Data Management</TabsTrigger>
          <TabsTrigger value="maintenance">Maintenance</TabsTrigger>
        </TabsList>

        <TabsContent value="general">
          <div className="grid gap-6">
            {/* Tenant Info */}
            <Card>
              <CardHeader>
                <CardTitle>Organization Information</CardTitle>
                <CardDescription>Basic information about your organization</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Organization Name</p>
                    <p className="text-lg">{tenantInfo?.display_name || tenantInfo?.name}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Created</p>
                    <p className="text-lg">
                      {tenantInfo?.created_at ? new Date(tenantInfo.created_at).toLocaleDateString() : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Users</p>
                    <p className="text-lg">{tenantStats?.total_users || 0}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">Total Documents</p>
                    <p className="text-lg">{tenantStats?.total_documents || 0}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Storage Usage */}
            <Card>
              <CardHeader>
                <CardTitle>Storage Usage</CardTitle>
                <CardDescription>Monitor your storage consumption</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between mb-2">
                      <span className="text-sm font-medium">
                        {formatBytes(tenantStats?.storage_used_bytes || 0)} of {formatBytes(tenantStats?.storage_limit_bytes || 0)}
                      </span>
                      <span className="text-sm text-muted-foreground">
                        {tenantStats?.storage_limit_bytes > 0 
                          ? Math.round((tenantStats.storage_used_bytes / tenantStats.storage_limit_bytes) * 100) 
                          : 0}%
                      </span>
                    </div>
                    <Progress 
                      value={tenantStats?.storage_limit_bytes > 0 
                        ? (tenantStats.storage_used_bytes / tenantStats.storage_limit_bytes) * 100 
                        : 0} 
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="indexing">
          <div className="grid gap-6">
            {/* Index Status */}
            <Card>
              <CardHeader>
                <CardTitle>Search Index Status</CardTitle>
                <CardDescription>Monitor and manage your search index</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-4">
                    <div className="text-center p-4 border rounded-lg">
                      <p className="text-2xl font-bold">{reindexStatus?.total_documents || 0}</p>
                      <p className="text-sm text-muted-foreground">Total Documents</p>
                    </div>
                    <div className="text-center p-4 border rounded-lg">
                      <p className="text-2xl font-bold text-green-600">
                        {reindexStatus?.indexed_documents || 0}
                      </p>
                      <p className="text-sm text-muted-foreground">Indexed</p>
                    </div>
                    <div className="text-center p-4 border rounded-lg">
                      <p className="text-2xl font-bold text-orange-600">
                        {reindexStatus?.missing_documents || 0}
                      </p>
                      <p className="text-sm text-muted-foreground">Missing</p>
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-4 bg-muted rounded-lg">
                    <div className="flex items-center gap-2">
                      <IconInfoCircle className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">
                        Index Status: 
                        <Badge variant={reindexStatus?.status === 'ready' ? 'success' : 'warning'} className="ml-2">
                          {reindexStatus?.status || 'Unknown'}
                        </Badge>
                      </span>
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <Button
                      onClick={handleReindexMissing}
                      disabled={isReindexing || reindexStatus?.missing_documents === 0}
                    >
                      {isReindexing ? (
                        <>
                          <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                          Reindexing...
                        </>
                      ) : (
                        <>
                          <IconRefresh className="mr-2 h-4 w-4" />
                          Reindex Missing Documents
                        </>
                      )}
                    </Button>

                    <Button
                      variant="outline"
                      onClick={handleForceReindex}
                      disabled={isReindexing}
                    >
                      <IconDatabase className="mr-2 h-4 w-4" />
                      Force Full Reindex
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="data">
          <div className="grid gap-6">
            <Alert>
              <IconAlertTriangle className="h-4 w-4" />
              <AlertTitle>Danger Zone</AlertTitle>
              <AlertDescription>
                These actions are irreversible. Please proceed with caution.
              </AlertDescription>
            </Alert>

            {/* Delete All Documents */}
            <Card className="border-destructive/50">
              <CardHeader>
                <CardTitle className="text-destructive">Delete All Documents</CardTitle>
                <CardDescription>
                  Permanently remove all documents from your organization
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  variant="destructive"
                  onClick={() => setDeleteDialogOpen(true)}
                >
                  <IconTrash className="mr-2 h-4 w-4" />
                  Delete All Documents
                </Button>
              </CardContent>
            </Card>

            {/* Clear Vector Database */}
            <Card className="border-destructive/50">
              <CardHeader>
                <CardTitle className="text-destructive">Clear Search Index</CardTitle>
                <CardDescription>
                  Remove all search embeddings. Documents will need to be reindexed.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  variant="destructive"
                  onClick={handleClearVectorDB}
                  disabled={isDeleting}
                >
                  <IconDatabase className="mr-2 h-4 w-4" />
                  Clear Vector Database
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="maintenance">
          <div className="grid gap-6">
            {/* Maintenance Operations */}
            <Card>
              <CardHeader>
                <CardTitle>System Maintenance</CardTitle>
                <CardDescription>
                  Run maintenance operations to optimize system performance
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-4 bg-muted rounded-lg">
                  <h4 className="font-medium mb-2">Maintenance tasks include:</h4>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    <li>• Optimize database tables and indexes</li>
                    <li>• Clean up orphaned files in storage</li>
                    <li>• Remove expired temporary data</li>
                    <li>• Compact vector database</li>
                  </ul>
                </div>

                <Button
                  onClick={handleRunMaintenance}
                  disabled={isLoading}
                >
                  <IconTool className="mr-2 h-4 w-4" />
                  Run Maintenance
                </Button>
              </CardContent>
            </Card>

            {/* Backup */}
            <Card>
              <CardHeader>
                <CardTitle>Data Backup</CardTitle>
                <CardDescription>
                  Create a backup of your organization data
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button variant="outline" disabled>
                  <IconDownload className="mr-2 h-4 w-4" />
                  Create Backup (Coming Soon)
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Are you absolutely sure?</DialogTitle>
            <DialogDescription>
              This action will permanently delete all documents in your organization.
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <Alert className="border-destructive/50">
              <IconAlertTriangle className="h-4 w-4 text-destructive" />
              <AlertDescription>
                Type <strong>DELETE ALL DOCUMENTS</strong> to confirm
              </AlertDescription>
            </Alert>
            
            <Input
              placeholder="Type confirmation text"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
            />
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDeleteDialogOpen(false)
                setDeleteConfirmText("")
              }}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteAllDocuments}
              disabled={deleteConfirmText !== "DELETE ALL DOCUMENTS" || isDeleting}
            >
              {isDeleting ? (
                <>
                  <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete All Documents'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
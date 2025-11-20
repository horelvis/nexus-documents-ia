"use client"

import { useState, useEffect, useCallback } from "react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import {
  IconFileText,
  IconEdit,
  IconClock,
  IconUser,
  IconCheck,
  IconX
} from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useToast } from "@/hooks/use-toast"
import { useApiClient } from "@/lib/api-client"

interface Template {
  id: string
  name: string
  description?: string
  category: string
  status: string
  created_at?: string
  updated_at?: string
  template_file_name?: string
  template_file_mime?: string
}

interface DriveStatus {
  connected: boolean
  google_email?: string
  expires_at?: string
}

const formatTimestamp = (value?: string) => {
  if (!value) return "Unknown"
  return new Date(value).toLocaleDateString()
}

export default function TemplatesPage() {
  const params = useParams<{ tenantId: string }>()
  const tenantId = params?.tenantId ?? ""
  const router = useRouter()
  const { toast } = useToast()
  const apiClient = useApiClient()

  const [isLoading, setIsLoading] = useState(true)
  const [templates, setTemplates] = useState<Template[]>([])
  const [error, setError] = useState<string | null>(null)
  const [editingSessions, setEditingSessions] = useState<Set<string>>(new Set())
  const [driveStatus, setDriveStatus] = useState<DriveStatus | null>(null)
  const [driveLoading, setDriveLoading] = useState(true)

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await apiClient.get<Template[]>('/engine-templates?status=active')
      if (response.error) {
        throw new Error(response.error)
      }

      const items = Array.isArray(response.data) ? response.data : []
      const normalized: Template[] = items.map((item: Template) => ({
        id: item.id,
        name: item.name,
        description: item.description,
        category: item.category,
        status: item.status,
        created_at: item.created_at,
        updated_at: item.updated_at,
        template_file_name: item.template_file_name,
        template_file_mime: item.template_file_mime,
      }))

      setTemplates(normalized)
    } catch (err) {
      console.error('[templates] load error', err)
      const message = 'Unable to load templates right now. Please try again later.'
      setError(message)
      toast({
        title: 'Error loading templates',
        description: message,
        variant: 'destructive',
      })
    } finally {
      setIsLoading(false)
    }
  }, [apiClient, toast])

  const fetchDriveStatus = useCallback(async () => {
    setDriveLoading(true)
    try {
      const response = await apiClient.get<DriveStatus>('/google-drive/status')
      if (response.error) {
        throw new Error(response.error)
      }
      setDriveStatus(response.data || { connected: false })
    } catch (err) {
      console.error('[templates] drive status error', err)
      setDriveStatus({ connected: false })
    } finally {
      setDriveLoading(false)
    }
  }, [apiClient])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    fetchDriveStatus()
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'google-drive-connected' || event.data?.type === 'google-drive-error') {
        fetchDriveStatus()
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [fetchDriveStatus])

  const handleConnectGoogleDrive = async () => {
    try {
      const response = await apiClient.get<{ authorization_url?: string }>('/google-drive/oauth-url')
      if (response.error || !response.data?.authorization_url) {
        throw new Error(response.error || 'Failed to initiate Google Drive connection')
      }
      window.location.href = response.data.authorization_url
    } catch (err) {
      console.error('[templates] connect drive error', err)
      toast({
        title: 'Cannot connect Google Drive',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      })
    }
  }

  const startEditing = async (template: Template) => {
    if (driveLoading) {
      toast({
        title: 'Checking Google Drive',
        description: 'Please wait while we verify your Drive connection',
      })
      return
    }

    if (!driveStatus?.connected) {
      toast({
        title: 'Connect Google Drive first',
        description: 'You must connect your Google account to edit templates.',
        variant: 'destructive',
      })
      return
    }

    setEditingSessions(prev => new Set([...prev, template.id]))

    try {
      const response = await apiClient.post(`/engine-templates/${template.id}/edit-sessions`, {
        reason: 'Template edit requested from library',
      })

      if (response.error || !response.data) {
        throw new Error(response.error || 'Failed to create editing session')
      }

      toast({
        title: 'Edit session created',
        description: `Opening Google Docs for ${template.name}`,
      })

      window.open(
        response.data.google_doc_edit_url,
        'googledocs',
        'width=1200,height=800,scrollbars=yes,resizable=yes'
      )
    } catch (err) {
      console.error('[templates] start edit error', err)
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to start editing session',
        variant: 'destructive',
      })
    } finally {
      setEditingSessions(prev => {
        const next = new Set(prev)
        next.delete(template.id)
        return next
      })
    }
  }

  if (isLoading) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex justify-center items-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Document Templates</h1>
          <p className="text-muted-foreground">
            Manage and edit document templates stored in the Nexus backend
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" asChild>
            <Link href={`/${tenantId}/templates/sessions`}>
              <IconClock className="mr-2 h-4 w-4" />
              Edit Sessions
            </Link>
          </Button>
          <Button onClick={() => router.push(`/${tenantId}/documents?upload=template`)}>
            Upload Template
          </Button>
        </div>
      </div>

      {!driveLoading && !driveStatus?.connected && (
        <Card className="border-dashed border-primary/30 bg-primary/5">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-5">
            <div>
              <h2 className="text-base font-semibold">Connect Google Drive</h2>
              <p className="text-sm text-muted-foreground">
                You need to grant access so we can create temporary Google Docs for editing.
              </p>
            </div>
            <Button onClick={handleConnectGoogleDrive}>Connect Google Drive</Button>
          </CardContent>
        </Card>
      )}

      {error && (
        <Card>
          <CardContent className="flex items-center gap-3 py-4 text-destructive">
            <IconX className="h-4 w-4" />
            <span>{error}</span>
          </CardContent>
        </Card>
      )}

      {templates.length === 0 && !error ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground space-y-2">
            <p className="font-medium">Aún no hay plantillas para este tenant.</p>
            <p className="text-sm">
              Sube una nueva plantilla ODT usando el botón "Upload Template" o conviértela desde{' '}
              <Link className="underline text-primary" href={`/${tenantId}/documents`}>
                la biblioteca de documentos
              </Link>.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {templates.map((template) => (
            <Card key={template.id} className="h-full">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center space-x-2">
                    <IconFileText className="w-5 h-5 text-primary" />
                    <CardTitle className="text-lg">{template.name}</CardTitle>
                  </div>
                  <Badge variant="outline">{template.category}</Badge>
                </div>
                <CardDescription className="line-clamp-2">
                  {template.description || 'No description provided'}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground line-clamp-4">
                  {template.description || 'No description provided'}
                </p>

                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <div className="flex items-center space-x-1">
                    <IconClock className="w-3 h-3" />
                    <span>Updated {formatTimestamp(template.updated_at || template.created_at)}</span>
                  </div>
                  {template.status === 'active' ? (
                    <div className="flex items-center space-x-1 text-green-600">
                      <IconCheck className="w-3 h-3" />
                      <span>Active</span>
                    </div>
                  ) : (
                    <Badge variant="outline">{template.status}</Badge>
                  )}
                </div>

                <div className="text-xs text-muted-foreground">
                  Source file: {template.template_file_name || 'No ODT uploaded yet'}
                </div>

                <div className="flex space-x-2">
                  <Button
                    onClick={() => startEditing(template)}
                    disabled={editingSessions.has(template.id)}
                    className="flex-1"
                  >
                    {editingSessions.has(template.id) ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                        Preparing...
                      </>
                    ) : (
                      <>
                        <IconEdit className="w-4 h-4 mr-2" />
                        Edit Template
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card className="mt-8">
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <IconUser className="w-5 h-5" />
            <span>How Template Editing Works</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>1. Click "Edit Template" to request a Google Docs session from the backend.</p>
          <p>2. Edit the temporary document in Google Docs with full formatting support.</p>
          <p>3. When you finish, finalize the session so the ODT is stored again.</p>
          <p>4. Temporary documents automatically expire after a few hours.</p>
        </CardContent>
      </Card>
    </div>
  )
}

"use client"

import { useState, useEffect } from "react"
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
import { useTranslation } from "@/lib/i18n/hooks"

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

export default function TemplatesPage() {
  const params = useParams<{ tenantId: string }>()
  const tenantId = params?.tenantId ?? ""
  const router = useRouter()
  const { toast } = useToast()
  const apiClient = useApiClient()
  const { t, language } = useTranslation()

  const [isLoading, setIsLoading] = useState(true)
  const [templates, setTemplates] = useState<Template[]>([])
  const [error, setError] = useState<string | null>(null)
  const [editingSessions, setEditingSessions] = useState<Set<string>>(new Set())
  const [driveStatus, setDriveStatus] = useState<DriveStatus | null>(null)
  const [driveLoading, setDriveLoading] = useState(true)

  const formatTimestamp = (value?: string) => {
    if (!value) return t('templatesPage.templateCard.unknown')
    const locale = language === 'es' ? 'es-ES' : 'en-US';
    return new Date(value).toLocaleDateString(locale)
  }

  const loadData = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await apiClient.get<Template[]>('/engine-templates?status=active')
      if (response.error) {
        setError(response.error)
        return
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
      setError('Error loading templates')
    } finally {
      setIsLoading(false)
    }
  }

  const fetchDriveStatus = async () => {
    setDriveLoading(true)
    try {
      const response = await apiClient.get<DriveStatus>('/google-drive/status')
      if (response.error) {
        setDriveStatus({ connected: false })
        return
      }
      setDriveStatus(response.data || { connected: false })
    } catch (err) {
      setDriveStatus({ connected: false })
    } finally {
      setDriveLoading(false)
    }
  }

  // Load data on mount
  useEffect(() => {
    loadData()
    fetchDriveStatus()
  }, [])

  // Listen for Google Drive connection events
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'google-drive-connected' || event.data?.type === 'google-drive-error') {
        fetchDriveStatus()
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [])

  const handleConnectGoogleDrive = async () => {
    try {
      const response = await apiClient.get<{ authorization_url?: string }>('/google-drive/oauth-url')
      if (response.error || !response.data?.authorization_url) {
        throw new Error(response.error || t('templatesPage.toast.connectDriveFailed.description'))
      }
      window.location.href = response.data.authorization_url
    } catch (err) {
      console.error('[templates] connect drive error', err)
      toast({
        title: t('templatesPage.toast.connectDriveFailed.title'),
        description: err instanceof Error ? err.message : t('templatesPage.genericError'),
        variant: 'destructive',
      })
    }
  }

  const startEditing = async (template: Template) => {
    if (driveLoading) {
      toast({
        title: t('templatesPage.toast.checkingDrive.title'),
        description: t('templatesPage.toast.checkingDrive.description'),
      })
      return
    }

    if (!driveStatus?.connected) {
      toast({
        title: t('templatesPage.toast.connectDriveFirst.title'),
        description: t('templatesPage.toast.connectDriveFirst.description'),
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
        throw new Error(response.error || t('templatesPage.toast.editSessionFailed.description'))
      }

      toast({
        title: t('templatesPage.toast.editSessionCreated.title'),
        description: t('templatesPage.toast.editSessionCreated.description', { templateName: template.name }),
      })

      window.open(
        response.data.google_doc_edit_url,
        'googledocs',
        'width=1200,height=800,scrollbars=yes,resizable=yes'
      )
    } catch (err) {
      console.error('[templates] start edit error', err)
      toast({
        title: t('templatesPage.toast.editSessionFailed.title'),
        description: err instanceof Error ? err.message : t('templatesPage.toast.editSessionFailed.description'),
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
          <h1 className="text-3xl font-bold">{t('templatesPage.title')}</h1>
          <p className="text-muted-foreground">
            {t('templatesPage.subtitle')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" asChild>
            <Link href={`/${tenantId}/templates/sessions`}>
              <IconClock className="mr-2 h-4 w-4" />
              {t('templatesPage.editSessionsButton')}
            </Link>
          </Button>
          <Button onClick={() => router.push(`/${tenantId}/documents?upload=template`)}>
            {t('templatesPage.uploadTemplateButton')}
          </Button>
        </div>
      </div>

      {!driveLoading && !driveStatus?.connected && (
        <Card className="border-dashed border-primary/30 bg-primary/5">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-5">
            <div>
              <h2 className="text-base font-semibold">{t('templatesPage.connectGoogleDrive.title')}</h2>
              <p className="text-sm text-muted-foreground">
                {t('templatesPage.connectGoogleDrive.description')}
              </p>
            </div>
            <Button onClick={handleConnectGoogleDrive}>{t('templatesPage.connectGoogleDrive.button')}</Button>
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
            <p className="font-medium">{t('templatesPage.noTemplates.title')}</p>
            <p className="text-sm">
              {t('templatesPage.noTemplates.description1')}{' '}
              <Link className="underline text-primary" href={`/${tenantId}/documents`}>
                {t('templatesPage.noTemplates.documentsLibrary')}
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
                  {template.description || t('templatesPage.templateCard.noDescription')}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground line-clamp-4">
                  {template.description || t('templatesPage.templateCard.noDescription')}
                </p>

                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <div className="flex items-center space-x-1">
                    <IconClock className="w-3 h-3" />
                    <span>{t('templatesPage.templateCard.updated')} {formatTimestamp(template.updated_at || template.created_at)}</span>
                  </div>
                  {template.status === 'active' ? (
                    <div className="flex items-center space-x-1 text-green-600">
                      <IconCheck className="w-3 h-3" />
                      <span>{t('templatesPage.templateCard.active')}</span>
                    </div>
                  ) : (
                    <Badge variant="outline">{template.status}</Badge>
                  )}
                </div>

                <div className="text-xs text-muted-foreground">
                  {t('templatesPage.templateCard.sourceFile')}{template.template_file_name || t('templatesPage.templateCard.noOdtUploaded')}
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
                        {t('templatesPage.templateCard.preparingButton')}
                      </>
                    ) : (
                      <>
                        <IconEdit className="w-4 h-4 mr-2" />
                        {t('templatesPage.templateCard.editTemplateButton')}
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
            <span>{t('templatesPage.howItWorks.title')}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>{t('templatesPage.howItWorks.step1')}</p>
          <p>{t('templatesPage.howItWorks.step2')}</p>
          <p>{t('templatesPage.howItWorks.step3')}</p>
          <p>{t('templatesPage.howItWorks.step4')}</p>
        </CardContent>
      </Card>
    </div>
  )
}

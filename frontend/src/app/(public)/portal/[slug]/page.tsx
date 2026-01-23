"use client"

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useSiteGuest } from '@/contexts/site-guest-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Loader2, Mail, KeyRound, LogOut, File, Folder, Eye, Download,
  RefreshCw
} from 'lucide-react'
import { PortalDocument, PortalContentResponse, PortalShare } from '@/lib/services/site-guest.service'
import { formatDistanceToNow } from 'date-fns'
import { es, enUS, fr } from 'date-fns/locale'
import { useTranslation } from '@/lib/i18n/hooks'

type ViewState = 'loading' | 'login' | 'otp' | 'content' | 'error'

export default function PortalPage() {
  const params = useParams()
  const router = useRouter()
  const slug = params.slug as string
  const { t, language } = useTranslation()

  const tSafe = (key: string, fallback: string) => {
    try {
      const value = t(key)
      return value && value !== key ? value : fallback
    } catch {
      return fallback
    }
  }

  const {
    tenant, guest, sessionToken, isLoading: contextLoading,
    setTenant, login, logout, portalService
  } = useSiteGuest()

  const [viewState, setViewState] = useState<ViewState>('loading')
  const [error, setError] = useState<string | null>(null)

  // Login form
  const [email, setEmail] = useState('')
  const [isRequestingOTP, setIsRequestingOTP] = useState(false)

  // OTP form
  const [otpCode, setOtpCode] = useState('')
  const [otpExpiry, setOtpExpiry] = useState(0)
  const [isVerifying, setIsVerifying] = useState(false)

  // Content summary (shares + legacy folders/docs)
  const [content, setContent] = useState<PortalContentResponse | null>(null)
  const [isLoadingContent, setIsLoadingContent] = useState(false)

  // Sidebar selection + share documents (loaded on demand)
  const [selectedShareId, setSelectedShareId] = useState<string | null>(null)
  const [selectedShare, setSelectedShare] = useState<PortalShare | null>(null)
  const [shareDocuments, setShareDocuments] = useState<PortalDocument[]>([])
  const [isLoadingShare, setIsLoadingShare] = useState(false)
  const [shareError, setShareError] = useState<string | null>(null)

  // Get date-fns locale based on current language
  const getDateLocale = () => {
    switch (language) {
      case 'es': return es
      case 'fr': return fr
      default: return enUS
    }
  }

  // Load tenant info on mount
  useEffect(() => {
    const loadTenant = async () => {
      try {
        const response = await portalService.getTenantBySlug(slug)
        if (response.error) {
          setError(response.error)
          setViewState('error')
        } else if (response.data) {
          setTenant(response.data)
          // If already logged in, show content
          if (sessionToken && guest) {
            setViewState('content')
          } else {
            setViewState('login')
          }
        }
      } catch (err) {
        setError(t('siteGuest.portal.error.description'))
        setViewState('error')
      }
    }

    if (!contextLoading) {
      if (sessionToken && guest) {
        setViewState('content')
      } else {
        loadTenant()
      }
    }
  }, [slug, contextLoading, sessionToken, guest, portalService, setTenant])

  // Load content when logged in
  useEffect(() => {
    const loadContent = async () => {
      if (viewState !== 'content' || !sessionToken) return

      setIsLoadingContent(true)
      try {
        const response = await portalService.getContent()
        if (response.data) {
          setContent(response.data)
        } else if (response.error) {
          setError(response.error)
        }
      } catch (err) {
        setError(t('siteGuest.portal.error.description'))
      } finally {
        setIsLoadingContent(false)
      }
    }

    loadContent()
  }, [viewState, sessionToken, portalService])

  // Auto-select the first share when content arrives (sidebar default)
  useEffect(() => {
    if (viewState !== 'content') return
    if (!content?.shares?.length) return
    if (selectedShareId) return

    setSelectedShareId(content.shares[0].id)
    setSelectedShare(content.shares[0])
  }, [content, viewState, selectedShareId])

  // Load documents for selected share (on demand)
  useEffect(() => {
    const loadShare = async () => {
      if (viewState !== 'content' || !sessionToken) return
      if (!selectedShareId) return

      setIsLoadingShare(true)
      setShareError(null)
      try {
        const resp = await portalService.getShareDocuments(selectedShareId)
        if (resp.error) {
          setShareError(resp.error)
          setShareDocuments([])
        } else if (resp.data) {
          setSelectedShare(resp.data.share)
          setShareDocuments(resp.data.documents || [])
        }
      } catch (err) {
        setShareError(tSafe('siteGuest.portal.error.description', 'Error al cargar'))
        setShareDocuments([])
      } finally {
        setIsLoadingShare(false)
      }
    }

    loadShare()
  }, [selectedShareId, viewState, sessionToken, portalService])

  const handleRequestOTP = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsRequestingOTP(true)
    setError(null)

    try {
      const response = await portalService.requestOTP(slug, email)
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        if (response.data.success) {
          setOtpExpiry(response.data.expires_in_seconds)
          setViewState('otp')
        } else {
          setError(response.data.message)
        }
      }
    } catch (err) {
      setError(t('siteGuest.portal.error.description'))
    } finally {
      setIsRequestingOTP(false)
    }
  }

  const handleVerifyOTP = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsVerifying(true)
    setError(null)

    try {
      const response = await portalService.verifyOTP(slug, email, otpCode)
      if (response.error) {
        setError(t('siteGuest.portal.otp.invalidCode'))
      } else if (response.data) {
        if (response.data.success && response.data.session_token && response.data.guest) {
          login(response.data.session_token, response.data.guest)
          setViewState('content')
        } else {
          setError(t('siteGuest.portal.otp.invalidCode'))
        }
      }
    } catch (err) {
      setError(t('siteGuest.portal.otp.invalidCode'))
    } finally {
      setIsVerifying(false)
    }
  }

  const handleLogout = async () => {
    await logout()
    setViewState('login')
    setContent(null)
    setSelectedShareId(null)
    setSelectedShare(null)
    setShareDocuments([])
  }

  const handleViewDocument = async (doc: PortalDocument) => {
    router.push(`/portal/${slug}/documents/${doc.id}/view`)
  }

  const handleDownloadDocument = (doc: PortalDocument) => {
    const url = portalService.getDocumentDownloadUrl(doc.id)
    // Add auth header via fetch and trigger download
    window.open(url, '_blank')
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  // Loading state
  if (viewState === 'loading' || contextLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-primary" />
          <p className="text-muted-foreground">
            {tSafe('siteGuest.portal.loading', 'Cargando…')}
          </p>
        </div>
      </div>
    )
  }

  // Error state
  if (viewState === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="w-full max-w-md shadow-sm border-gray-200">
          <CardHeader className="text-center">
            <CardTitle className="text-destructive">{t('siteGuest.portal.error.title')}</CardTitle>
            <CardDescription>{error || t('siteGuest.portal.error.description')}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }

  // Login form
  if (viewState === 'login') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <div className="flex items-center justify-center gap-2 pb-2">
              <img
                src="/android-chrome-192x192.png"
                alt="NouxCubeIA"
                className="h-7 w-7"
              />
              <span className="text-sm font-medium text-muted-foreground">NouxCubeIA</span>
            </div>
            {tenant?.logo_url && (
              <img
                src={tenant.logo_url}
                alt={tenant.tenant_name}
                className="h-12 mx-auto mb-4 object-contain"
              />
            )}
            <CardTitle>{tenant?.tenant_name || t('siteGuest.portal.title')}</CardTitle>
            <CardDescription>
              {tenant?.welcome_message || t('siteGuest.portal.login.invitedOnly')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleRequestOTP} className="space-y-4">
              {error && (
                <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-md">
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">{t('siteGuest.portal.login.emailLabel')}</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={t('siteGuest.portal.login.emailPlaceholder')}
                    className="pl-10"
                    required
                  />
                </div>
              </div>

              <Button type="submit" className="w-full" disabled={isRequestingOTP}>
                {isRequestingOTP && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {isRequestingOTP ? t('siteGuest.portal.login.sending') : t('siteGuest.portal.login.sendCode')}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    )
  }

  // OTP verification
  if (viewState === 'otp') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <CardTitle>{t('siteGuest.portal.otp.title')}</CardTitle>
            <CardDescription>
              {t('siteGuest.portal.otp.subtitle').replace('{email}', email)}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleVerifyOTP} className="space-y-4">
              {error && (
                <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-md">
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="otp">{t('siteGuest.portal.otp.codeLabel')}</Label>
                <div className="relative">
                  <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="otp"
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))}
                    placeholder={t('siteGuest.portal.otp.codePlaceholder')}
                    className="pl-10 text-center text-2xl tracking-[0.5em]"
                    required
                  />
                </div>
                <p className="text-xs text-muted-foreground text-center">
                  {t('siteGuest.portal.otp.expiresIn').replace('{minutes}', String(Math.floor(otpExpiry / 60)))}
                </p>
              </div>

              <Button type="submit" className="w-full" disabled={isVerifying || otpCode.length !== 6}>
                {isVerifying && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {isVerifying ? t('siteGuest.portal.otp.verifying') : t('siteGuest.portal.otp.verify')}
              </Button>

              <Button
                type="button"
                variant="ghost"
                className="w-full"
                onClick={() => {
                  setViewState('login')
                  setOtpCode('')
                  setError(null)
                }}
              >
                {t('siteGuest.portal.otp.backToLogin')}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Content view
  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="container mx-auto px-4 lg:px-6 py-4 flex justify-between items-center">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              <img
                src="/android-chrome-192x192.png"
                alt="NouxCubeIA"
                className="h-8 w-8"
              />
              {tenant?.logo_url && (
                <img src={tenant.logo_url} alt="" className="h-8 object-contain" />
              )}
            </div>
            <div>
              <h1 className="font-semibold text-foreground">{tenant?.tenant_name}</h1>
              <p className="text-sm text-muted-foreground">
                {guest?.name || guest?.email}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setIsLoadingContent(true)
                portalService.getContent().then(r => {
                  if (r.data) setContent(r.data)
                  setIsLoadingContent(false)
                })
                if (selectedShareId) {
                  setIsLoadingShare(true)
                  portalService.getShareDocuments(selectedShareId).then(resp => {
                    if (resp.data) {
                      setSelectedShare(resp.data.share)
                      setShareDocuments(resp.data.documents || [])
                      setShareError(null)
                    } else if (resp.error) {
                      setShareError(resp.error)
                    }
                    setIsLoadingShare(false)
                  })
                }
              }}
              disabled={isLoadingContent}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${isLoadingContent ? 'animate-spin' : ''}`} />
              {t('siteGuest.portal.content.refresh')}
            </Button>
            <Button variant="outline" onClick={handleLogout}>
              <LogOut className="h-4 w-4 mr-2" />
              {t('siteGuest.portal.content.logout')}
            </Button>
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 grid md:grid-cols-[280px_1fr]">
        {/* Sidebar */}
        <aside className="border-b md:border-b-0 md:border-r bg-card/40">
          <div className="p-4">
            <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Colecciones
            </h2>
          </div>
          <ScrollArea className="h-[calc(100vh-73px)] md:h-[calc(100vh-73px)]">
            <div className="px-2 pb-4 space-y-1">
              {content?.shares?.length ? (
                content.shares.map((share) => {
                  const isActive = selectedShareId === share.id
                  return (
                    <button
                      key={share.id}
                      className={[
                        "w-full text-left rounded-md px-3 py-2 transition-colors",
                        isActive ? "bg-primary/10 text-foreground" : "hover:bg-muted/60 text-foreground",
                      ].join(" ")}
                      onClick={() => {
                        setSelectedShareId(share.id)
                        setSelectedShare(share)
                      }}
                    >
                      <div className="flex items-start gap-2">
                        <Folder className="h-4 w-4 mt-0.5 text-violet-500" />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-medium truncate">{share.name}</span>
                            <Badge variant="secondary" className="shrink-0">
                              {share.document_count}
                            </Badge>
                          </div>
                          {share.description ? (
                            <p className="text-xs text-muted-foreground truncate">{share.description}</p>
                          ) : null}
                        </div>
                      </div>
                    </button>
                  )
                })
              ) : (
                <div className="px-3 py-8 text-sm text-muted-foreground">
                  No hay colecciones todavía.
                </div>
              )}
            </div>
          </ScrollArea>
        </aside>

        {/* Main */}
        <main className="p-4 md:p-6">
          {isLoadingContent ? (
            <div className="text-center py-12">
              <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
              <p className="text-muted-foreground">{tSafe('common.loading', 'Cargando…')}</p>
            </div>
          ) : !content || ((content.total_shares ?? 0) === 0 && content.total_documents === 0 && content.total_folders === 0) ? (
            <Card>
              <CardContent className="text-center py-12">
                <img
                  src="/illustrations/documents-empty.svg"
                  alt="Documentos"
                  className="mx-auto mb-5 h-40 w-auto"
                />
                <p className="text-muted-foreground">{t('siteGuest.portal.content.noContent.description')}</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <h2 className="text-xl font-bold truncate">
                    {selectedShare?.name || tSafe('siteGuest.portal.content.title', 'Documentos')}
                  </h2>
                  {selectedShare?.description ? (
                    <p className="text-sm text-muted-foreground truncate">{selectedShare.description}</p>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {tSafe('siteGuest.portal.content.welcome', 'Contenido compartido')}
                    </p>
                  )}
                </div>
                {selectedShare ? (
                  <Badge variant="outline" className="shrink-0">
                    {selectedShare.permission_type === 'download'
                      ? 'Ver y descargar'
                      : selectedShare.permission_type === 'upload'
                        ? 'Subir'
                        : 'Solo ver'}
                  </Badge>
                ) : null}
              </div>

              {shareError ? (
                <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-md">
                  {shareError}
                </div>
              ) : null}

              {isLoadingShare ? (
                <div className="text-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
                  <p className="text-muted-foreground">{tSafe('common.loading', 'Cargando…')}</p>
                </div>
              ) : selectedShareId ? (
                shareDocuments.length ? (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg flex items-center gap-2">
                        <File className="h-5 w-5" />
                        Documentos ({shareDocuments.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="p-0">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>{tSafe('siteGuest.portal.content.table.name', 'Nombre')}</TableHead>
                            <TableHead>{tSafe('siteGuest.portal.content.table.type', 'Tipo')}</TableHead>
                            <TableHead>{tSafe('siteGuest.portal.content.table.size', 'Tamaño')}</TableHead>
                            <TableHead>{tSafe('siteGuest.portal.content.table.updated', 'Actualizado')}</TableHead>
                            <TableHead className="w-[100px]">{tSafe('common.actions', 'Acciones')}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {shareDocuments.map((doc) => (
                            <TableRow key={doc.id}>
                              <TableCell>
                                <div className="flex items-center gap-2">
                                  <File className="h-4 w-4 text-muted-foreground" />
                                  <span className="font-medium">{doc.title || doc.filename}</span>
                                </div>
                              </TableCell>
                              <TableCell>
                                <Badge variant="secondary">{doc.file_type.toUpperCase()}</Badge>
                              </TableCell>
                              <TableCell className="text-muted-foreground">
                                {formatFileSize(doc.file_size)}
                              </TableCell>
                              <TableCell className="text-muted-foreground">
                                {formatDistanceToNow(new Date(doc.updated_at), { addSuffix: true, locale: getDateLocale() })}
                              </TableCell>
                              <TableCell>
                                <div className="flex gap-1">
                                  {doc.can_view && (
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => handleViewDocument(doc)}
                                      title={tSafe('siteGuest.portal.content.actions.view', 'Ver')}
                                    >
                                      <Eye className="h-4 w-4" />
                                    </Button>
                                  )}
                                  {doc.can_download && (
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => handleDownloadDocument(doc)}
                                      title={tSafe('siteGuest.portal.content.actions.download', 'Descargar')}
                                    >
                                      <Download className="h-4 w-4" />
                                    </Button>
                                  )}
                                </div>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                ) : (
                  <Card>
                    <CardContent className="text-center py-12">
                      <img
                        src="/illustrations/documents-empty.svg"
                        alt="Documentos"
                        className="mx-auto mb-5 h-40 w-auto"
                      />
                      <p className="text-muted-foreground">Esta colección no tiene documentos.</p>
                    </CardContent>
                  </Card>
                )
              ) : (
                <Card>
                  <CardContent className="text-center py-12">
                    <img
                      src="/illustrations/documents-empty.svg"
                      alt="Documentos"
                      className="mx-auto mb-5 h-40 w-auto"
                    />
                    <p className="text-muted-foreground">Selecciona una colección para ver sus documentos.</p>
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

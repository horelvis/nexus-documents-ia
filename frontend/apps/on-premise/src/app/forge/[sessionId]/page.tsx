'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import {
  IconFileText, IconDownload, IconDeviceFloppy, IconArrowLeft,
  IconRefresh, IconAlertCircle, IconCheck, IconClock,
} from '@tabler/icons-react'
import {
  SidebarProvider, SidebarInset,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@nexus/shared/ui'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import {
  getCachedForgeSession,
  getSessionInfo,
  renderDocument,
  persistDocument,
  downloadDocument,
} from '@/lib/services/forge.service'
import type { ForgeField, ForgeMetadata, ForgeOutputInfo } from '@/lib/types/emma'

type PageState = 'loading' | 'editing' | 'rendering' | 'rendered' | 'persisting' | 'persisted' | 'error' | 'expired'

function getInputType(fieldType: string): string {
  switch (fieldType) {
    case 'date': return 'date'
    case 'number':
    case 'currency': return 'number'
    case 'email': return 'email'
    case 'phone': return 'tel'
    default: return 'text'
  }
}

function getConfidenceColor(c: number): string {
  if (c >= 0.8) return 'text-emerald-600'
  if (c >= 0.6) return 'text-amber-500'
  return 'text-red-500'
}

export default function ForgeDetailPage() {
  const params = useParams()
  const sessionId = params.sessionId as string

  const [pageState, setPageState] = useState<PageState>('loading')
  const [error, setError] = useState<string | null>(null)

  // Session data
  const [sourceTitle, setSourceTitle] = useState('')
  const [documentType, setDocumentType] = useState('')
  const [confidence, setConfidence] = useState(0)
  const [fields, setFields] = useState<ForgeField[]>([])
  const [outputs, setOutputs] = useState<Record<string, ForgeOutputInfo>>({})

  // Form state: field_name → value
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({})

  // Load session
  useEffect(() => {
    async function loadSession() {
      setPageState('loading')
      setError(null)

      // Try sessionStorage first (fast)
      const cached = getCachedForgeSession(sessionId)
      if (cached) {
        applySessionData(cached)
        return
      }

      // Fallback: API
      const response = await getSessionInfo(sessionId)
      if (response.error) {
        if (response.error.includes('404') || response.error.includes('not found')) {
          setPageState('expired')
        } else {
          setError(response.error)
          setPageState('error')
        }
        return
      }

      if (response.data) {
        applySessionData({
          action: 'analyze',
          session_id: sessionId,
          source_title: response.data.source_title,
          document_type: response.data.document_type,
          confidence: response.data.confidence,
          fields: response.data.fields,
          status: response.data.status,
          field_values: response.data.field_values,
          outputs: response.data.outputs,
        })
      }
    }

    loadSession()
  }, [sessionId])

  function applySessionData(data: ForgeMetadata) {
    setSourceTitle(data.source_title)
    setDocumentType(data.document_type)
    setConfidence(data.confidence)
    setFields(data.fields || [])

    // Pre-populate form: use suggested_value > current_value
    const initial: Record<string, string> = {}
    for (const f of data.fields || []) {
      initial[f.field_name] = f.suggested_value || f.current_value || ''
    }
    if (data.field_values) {
      Object.assign(initial, data.field_values)
    }
    setFieldValues(initial)

    if (data.outputs && Object.keys(data.outputs).length > 0) {
      setOutputs(data.outputs)
      setPageState(data.status === 'persisted' ? 'persisted' : 'rendered')
    } else {
      setPageState('editing')
    }
  }

  function handleFieldChange(fieldName: string, value: string) {
    setFieldValues(prev => ({ ...prev, [fieldName]: value }))
  }

  async function handleRender() {
    setPageState('rendering')
    setError(null)
    try {
      const response = await renderDocument(sessionId, fieldValues, ['docx', 'pdf'])
      if (response.error) {
        setError(response.error)
        setPageState('editing')
      } else if (response.data) {
        setOutputs(response.data.outputs)
        setPageState('rendered')
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error inesperado')
      setPageState('editing')
    }
  }

  async function handlePersist() {
    setPageState('persisting')
    setError(null)
    try {
      const response = await persistDocument(sessionId)
      if (response.error) {
        setError(response.error)
        setPageState('rendered')
      } else {
        setPageState('persisted')
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error inesperado')
      setPageState('rendered')
    }
  }

  function handleDownload(format: 'docx' | 'pdf') {
    downloadDocument(sessionId, format)
  }

  // --- Expired state ---
  if (pageState === 'expired') {
    return (
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <PageHeader>
            <span className="text-sm font-medium">Document Forge</span>
          </PageHeader>
          <div className="flex flex-col items-center justify-center p-12 text-center">
            <IconClock className="h-12 w-12 text-muted-foreground mb-4" />
            <h2 className="text-lg font-semibold mb-2">Sesion expirada</h2>
            <p className="text-muted-foreground mb-4">
              La sesion ha expirado (TTL 30 min). Vuelve al chat para analizar el documento de nuevo.
            </p>
            <Link href="/">
              <Button><IconArrowLeft className="h-4 w-4 mr-2" /> Volver al chat</Button>
            </Link>
          </div>
        </SidebarInset>
      </SidebarProvider>
    )
  }

  // --- Loading state ---
  if (pageState === 'loading') {
    return (
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <PageHeader>
            <span className="text-sm font-medium">Document Forge</span>
          </PageHeader>
          <div className="flex items-center justify-center p-12">
            <IconRefresh className="h-6 w-6 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">Cargando sesion...</span>
          </div>
        </SidebarInset>
      </SidebarProvider>
    )
  }

  // --- Main layout ---
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <nav className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/" className="hover:text-foreground transition-colors">Inicio</Link>
            <span>/</span>
            <span className="text-foreground font-medium">Document Forge</span>
          </nav>
        </PageHeader>
        <div className="p-6 max-w-4xl mx-auto space-y-6">

          {/* Header Card */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <IconFileText className="h-6 w-6 text-primary" />
                  <div>
                    <h1 className="text-lg font-semibold">{sourceTitle}</h1>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge variant="outline">{documentType}</Badge>
                      <span className={`text-sm font-medium ${getConfidenceColor(confidence)}`}>
                        {(confidence * 100).toFixed(0)}% confianza
                      </span>
                    </div>
                  </div>
                </div>
                <Link href="/">
                  <Button variant="ghost" size="sm">
                    <IconArrowLeft className="h-4 w-4 mr-1" /> Chat
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>

          {/* Error */}
          {error && (
            <Card className="border-red-200 bg-red-50/50">
              <CardContent className="p-4 flex items-center gap-2">
                <IconAlertCircle className="h-5 w-5 text-red-500" />
                <span className="text-red-700">{error}</span>
              </CardContent>
            </Card>
          )}

          {/* Fields Form */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Campos del documento ({fields.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {fields.map((field) => (
                <div key={field.field_name} className="space-y-1.5">
                  <Label htmlFor={field.field_name} className="flex items-center gap-1">
                    {field.label}
                    {field.required && <span className="text-red-500">*</span>}
                    <Badge variant="outline" className="ml-2 text-[10px]">{field.field_type}</Badge>
                  </Label>
                  {field.context_hint && (
                    <p className="text-xs text-muted-foreground">{field.context_hint}</p>
                  )}
                  {field.field_type === 'enum' && field.options ? (
                    <Select
                      value={fieldValues[field.field_name] || ''}
                      onValueChange={(value) => handleFieldChange(field.field_name, value)}
                      disabled={pageState === 'rendering' || pageState === 'persisting'}
                    >
                      <SelectTrigger id={field.field_name}>
                        <SelectValue placeholder={field.current_value || 'Seleccionar...'} />
                      </SelectTrigger>
                      <SelectContent>
                        {field.options.map((opt) => (
                          <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      id={field.field_name}
                      type={getInputType(field.field_type)}
                      value={fieldValues[field.field_name] || ''}
                      placeholder={field.current_value}
                      onChange={(e) => handleFieldChange(field.field_name, e.target.value)}
                      disabled={pageState === 'rendering' || pageState === 'persisting'}
                    />
                  )}
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Persisted success */}
          {pageState === 'persisted' && (
            <Card className="border-emerald-200 bg-emerald-50/50">
              <CardContent className="p-4 flex items-center gap-2">
                <IconCheck className="h-5 w-5 text-emerald-600" />
                <span className="text-emerald-800 font-medium">
                  Documento guardado permanentemente e indexado en el sistema.
                </span>
              </CardContent>
            </Card>
          )}

          {/* Action Bar */}
          {(() => {
            const isRenderedOrPersisted = pageState === 'rendered' || pageState === 'persisted'
            const isPersisted = pageState === 'persisted'
            const isPersisting = pageState === 'persisting'
            const isRendering = pageState === 'rendering'
            return (
              <div className="flex items-center gap-3 flex-wrap sticky bottom-4 bg-background/95 backdrop-blur p-4 rounded-lg border shadow-sm">
                <Button
                  onClick={handleRender}
                  disabled={isRendering || isPersisting}
                >
                  {isRendering ? (
                    <><IconRefresh className="h-4 w-4 mr-2 animate-spin" /> Generando...</>
                  ) : (
                    <><IconFileText className="h-4 w-4 mr-2" /> Generar documento</>
                  )}
                </Button>

                {isRenderedOrPersisted && (
                  <>
                    <Separator orientation="vertical" className="h-8" />
                    {outputs.docx && (
                      <Button variant="outline" size="sm" onClick={() => handleDownload('docx')}>
                        <IconDownload className="h-4 w-4 mr-1" /> DOCX
                      </Button>
                    )}
                    {outputs.pdf && (
                      <Button variant="outline" size="sm" onClick={() => handleDownload('pdf')}>
                        <IconDownload className="h-4 w-4 mr-1" /> PDF
                      </Button>
                    )}
                    {!isPersisted && (
                      <>
                        <Separator orientation="vertical" className="h-8" />
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={handlePersist}
                          disabled={isPersisting}
                        >
                          {isPersisting ? (
                            <><IconRefresh className="h-4 w-4 mr-1 animate-spin" /> Guardando...</>
                          ) : (
                            <><IconDeviceFloppy className="h-4 w-4 mr-1" /> Guardar en sistema</>
                          )}
                        </Button>
                      </>
                    )}
                  </>
                )}
              </div>
            )
          })()}

        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}

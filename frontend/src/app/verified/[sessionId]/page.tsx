'use client'

/**
 * Verified Document Detail Page
 *
 * Full-page view of a Verified Generation result with per-claim evidence sources,
 * confidence gauge, download actions, and global sources table.
 *
 * Data is read from sessionStorage (saved by VerifiedDocumentResult when user
 * clicks "Ver más detalles"). If not found, shows a fallback message.
 */

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import {
  IconCircleCheck,
  IconCircleX,
  IconFileCheck,
  IconLoader2,
  IconAlertTriangle,
  IconWorld,
  IconPaperclip,
  IconFile,
  IconFileTypePdf,
  IconFileTypeDocx,
  IconScale,
  IconArrowLeft,
  IconInbox,
} from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
  Button,
  Badge,
  Card,
  CardContent,
} from '@/components/ui'
import { useAuth } from '@/contexts/auth-context'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import { cn } from '@/lib/utils'
import { API_CONFIG } from '@/lib/config'
import { recoverVerifiedSession } from '@/lib/services/verified-generation.service'
import type {
  VerifiedGenerationMetadata,
  VerifiedClaimInfo,
  VerifiedSource,
  DoiValidation,
} from '@/lib/types/emma'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getGaugeColor(pct: number) {
  if (pct >= 70) return { text: 'text-emerald-500', stroke: 'stroke-emerald-500' }
  if (pct >= 40) return { text: 'text-amber-500', stroke: 'stroke-amber-500' }
  return { text: 'text-red-500', stroke: 'stroke-red-500' }
}

function getStatusConfig(status: string) {
  switch (status) {
    case 'verified':
      return {
        label: 'VERIFICADO',
        icon: <IconCircleCheck className="h-3.5 w-3.5" />,
        borderColor: 'border-l-emerald-500',
        bgColor: 'bg-emerald-50 dark:bg-emerald-950/40',
        badgeColor: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400',
      }
    case 'corrected':
      return {
        label: 'CORREGIDO',
        icon: <IconAlertTriangle className="h-3.5 w-3.5" />,
        borderColor: 'border-l-amber-500',
        bgColor: 'bg-amber-50 dark:bg-amber-950/40',
        badgeColor: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400',
      }
    default:
      return {
        label: 'RECHAZADO',
        icon: <IconCircleX className="h-3.5 w-3.5" />,
        borderColor: 'border-l-destructive',
        bgColor: 'bg-red-50 dark:bg-red-950/40',
        badgeColor: 'bg-red-100 text-red-700 dark:bg-destructive/20 dark:text-destructive',
      }
  }
}

function getSourceIcon(source: VerifiedSource) {
  if (source.roj || source.ecli) {
    return <IconScale className="h-3.5 w-3.5 text-purple-500" />
  }
  const type = source.source || 'internal'
  if (type === 'web') {
    return <IconWorld className="h-3.5 w-3.5 text-blue-500" />
  }
  if (type === 'uploaded') {
    return <IconPaperclip className="h-3.5 w-3.5 text-amber-500" />
  }
  if (type === 'doi' || type === 'crossref') {
    return <IconFileCheck className="h-3.5 w-3.5 text-green-600" />
  }
  if (type === 'doi_invalid') {
    return <IconCircleX className="h-3.5 w-3.5 text-red-500" />
  }
  if (type === 'doi_mismatch') {
    return <IconAlertTriangle className="h-3.5 w-3.5 text-amber-500" />
  }
  if (type === 'citation_unverified') {
    return <IconAlertTriangle className="h-3.5 w-3.5 text-gray-400" />
  }
  return <IconFile className="h-3.5 w-3.5 text-gray-400" />
}

function getSourceLabel(source: VerifiedSource): string {
  if (source.roj || source.ecli) return 'Jurisprudencia'
  const type = source.source || 'internal'
  if (type === 'web') return 'Web'
  if (type === 'uploaded') return 'Cargado'
  if (type === 'doi') return 'DOI Validado'
  if (type === 'crossref') return 'CrossRef'
  if (type === 'doi_invalid') return 'DOI Inválido'
  if (type === 'doi_mismatch') return 'DOI No Corresponde'
  if (type === 'citation_unverified') return 'Cita No Verificada'
  return 'Interno'
}

// ============================================================================
// Main Page Component
// ============================================================================

export default function VerifiedDetailPage() {
  const { isLoaded, isAuthenticated } = useAuth()
  const params = useParams()
  const sessionId = params.sessionId as string

  const [verified, setVerified] = useState<VerifiedGenerationMetadata | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)

  // Load data from sessionStorage, fall back to backend API
  useEffect(() => {
    if (!sessionId) return
    const stored = sessionStorage.getItem(`verified_session_${sessionId}`)
    if (stored) {
      try {
        setVerified(JSON.parse(stored))
        return
      } catch {
        // fall through to API
      }
    }

    // No sessionStorage data — try recovering from backend (Redis)
    recoverVerifiedSession(sessionId).then(data => {
      if (data && data.status === 'completed') {
        const recovered: VerifiedGenerationMetadata = {
          session_id: data.session_id,
          topic: data.topic || '',
          claims: data.claims || [],
          current_phase: 'complete',
          verified_count: data.verified_count || 0,
          rejected_count: data.rejected_count || 0,
          total_claims: data.total_claims || 0,
          document_text: data.document_text,
          execution_time_ms: data.execution_time_ms,
          average_confidence: data.average_confidence,
          sources: data.sources,
          doi_validations: data.doi_validations,
          source_filenames: data.source_filenames,
          source_summary: data.source_summary,
        }
        setVerified(recovered)
        // Cache in sessionStorage for subsequent renders
        sessionStorage.setItem(`verified_session_${sessionId}`, JSON.stringify(recovered))
      } else {
        setNotFound(true)
      }
    })
  }, [sessionId])

  // Download handler (same as VerifiedDocumentResult)
  async function downloadFile(format: 'pdf' | 'docx') {
    if (!sessionId) return
    setIsDownloading(true)
    try {
      const stored = typeof window !== 'undefined' ? sessionStorage.getItem('nexus_sso_tokens') : null
      const token = stored ? JSON.parse(stored).access_token : null
      const endpoint = format === 'pdf'
        ? API_CONFIG.ENDPOINTS.EMMA_VERIFIED_SESSION_PDF(sessionId)
        : API_CONFIG.ENDPOINTS.EMMA_VERIFIED_SESSION_DOCX(sessionId)
      const url = `/api/v1${endpoint}`
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token || ''}` },
      })
      if (!response.ok) throw new Error(`${format.toUpperCase()} generation failed`)
      const blob = await response.blob()
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = `informe_verificado_${sessionId.slice(0, 8)}.${format}`
      a.click()
      URL.revokeObjectURL(blobUrl)
    } catch {
      // silent fail — could add toast here
    } finally {
      setIsDownloading(false)
    }
  }

  // ── Auth guard ──────────────────────────────────────────────────────────
  if (!isLoaded) {
    return (
      <div className="flex h-screen items-center justify-center">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  // ── Not found state ─────────────────────────────────────────────────────
  if (notFound) {
    return (
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <PageHeader>
            <nav className="flex items-center gap-2 text-sm text-muted-foreground">
              <Link href="/" className="hover:text-foreground transition-colors">Inicio</Link>
              <span>/</span>
              <span className="text-foreground font-medium">Verificación</span>
            </nav>
          </PageHeader>
          <main className="flex-1 overflow-auto p-4 md:p-6">
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <IconInbox className="h-12 w-12 text-muted-foreground/40 mb-4" />
              <h2 className="text-lg font-semibold mb-2">Sesión no encontrada</h2>
              <p className="text-sm text-muted-foreground mb-6 max-w-md">
                Los datos de esta verificación no están disponibles. Esto puede ocurrir si la
                página se abrió en una nueva pestaña o si la sesión ha expirado.
              </p>
              <Button asChild variant="outline">
                <Link href="/" className="gap-2">
                  <IconArrowLeft className="h-4 w-4" />
                  Volver al chat
                </Link>
              </Button>
            </div>
          </main>
        </SidebarInset>
      </SidebarProvider>
    )
  }

  // ── Loading state (waiting for sessionStorage parse) ────────────────────
  if (!verified) {
    return (
      <div className="flex h-screen items-center justify-center">
        <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  // ── Derived data ────────────────────────────────────────────────────────
  const {
    claims,
    execution_time_ms,
    average_confidence,
    sources,
    topic,
  } = verified

  // Recompute stats from actual claims array (backend counts may include regenerated claims)
  const verifiedCount = claims.filter(c => c.status === 'verified').length
  const correctedCount = claims.filter(c => c.status === 'corrected').length
  const rejectedCount = claims.filter(c => c.status === 'rejected').length
  const totalClaims = claims.length
  const confidencePct = Math.round((average_confidence || 0) * 100)
  const gauge = getGaugeColor(confidencePct)

  // Collect all per-claim sources for the global table
  const allClaimSources: VerifiedSource[] = []
  const seenSourceIds = new Set<string>()
  for (const claim of claims) {
    if (claim.evidence_sources) {
      for (const src of claim.evidence_sources) {
        const key = src.id || src.title || src.roj || ''
        if (key && !seenSourceIds.has(key)) {
          seenSourceIds.add(key)
          allClaimSources.push(src)
        }
      }
    }
  }
  // Merge with global sources (dedup by id)
  const globalSources = [...allClaimSources]
  if (sources) {
    for (const src of sources) {
      const key = src.id || src.title || ''
      if (key && !seenSourceIds.has(key)) {
        seenSourceIds.add(key)
        globalSources.push(src)
      }
    }
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <nav className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/" className="hover:text-foreground transition-colors">Inicio</Link>
            <span>/</span>
            <Link href="/" className="hover:text-foreground transition-colors">Verificación</Link>
            <span>/</span>
            <span className="text-foreground font-medium truncate max-w-[200px]">{topic}</span>
          </nav>
        </PageHeader>

        <main className="flex-1 overflow-auto p-4 md:p-6">
          <div className="max-w-4xl mx-auto space-y-6">

            {/* ── Header Card ─────────────────────────────────────────── */}
            <Card>
              <CardContent className="p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-full bg-emerald-500/10 flex items-center justify-center shrink-0">
                      <IconFileCheck className="h-6 w-6 text-emerald-600" />
                    </div>
                    <div>
                      <h1 className="text-xl font-semibold">Informe de Verificación</h1>
                      <p className="text-sm text-muted-foreground mt-0.5">{topic}</p>
                      {verified.source_filenames && verified.source_filenames.length > 0 && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          <span className="font-medium">
                            {verified.source_filenames.length === 1 ? 'Fuente:' : 'Fuentes:'}
                          </span>{' '}
                          {verified.source_filenames.join(', ')}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground mt-1">
                        Sesión: {sessionId.slice(0, 16)}…
                        {execution_time_ms
                          ? ` · ${execution_time_ms < 1000 ? `${Math.round(execution_time_ms)}ms` : `${(execution_time_ms / 1000).toFixed(1)}s`}`
                          : ''}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Button variant="outline" size="sm" onClick={() => downloadFile('pdf')} disabled={isDownloading} className="gap-1.5">
                      <IconFileTypePdf className="h-4 w-4 text-red-500" />
                      PDF
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => downloadFile('docx')} disabled={isDownloading} className="gap-1.5">
                      <IconFileTypeDocx className="h-4 w-4 text-blue-500" />
                      DOCX
                    </Button>
                  </div>
                </div>

                {/* Status badges */}
                <div className="flex flex-wrap gap-2 mt-4">
                  <Badge variant="outline" className="text-xs bg-emerald-500/10 text-emerald-600 border-emerald-500/20">
                    <IconCircleCheck className="h-3 w-3 mr-1" />
                    {verifiedCount} verificados
                  </Badge>
                  {correctedCount > 0 && (
                    <Badge variant="outline" className="text-xs bg-amber-500/10 text-amber-600 border-amber-500/20">
                      <IconAlertTriangle className="h-3 w-3 mr-1" />
                      {correctedCount} corregidos
                    </Badge>
                  )}
                  {rejectedCount > 0 && (
                    <Badge variant="outline" className="text-xs bg-destructive/10 text-destructive border-destructive/20">
                      <IconCircleX className="h-3 w-3 mr-1" />
                      {rejectedCount} rechazados
                    </Badge>
                  )}
                  <Badge variant="outline" className="text-xs">
                    {totalClaims} claims totales
                  </Badge>
                </div>
              </CardContent>
            </Card>

            {/* ── Source Summary ───────────────────────────────────────── */}
            {verified.source_summary && (
              <Card>
                <CardContent className="p-4">
                  <p className="text-xs font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wider mb-1">Resumen del documento fuente</p>
                  <p className="text-sm text-muted-foreground leading-relaxed">{verified.source_summary}</p>
                </CardContent>
              </Card>
            )}

            {/* ── Confidence Gauge + Stats Grid ───────────────────────── */}
            <Card>
              <CardContent className="p-6">
                <div className="flex flex-col md:flex-row items-center gap-6">
                  {/* Gauge */}
                  <div className="relative inline-flex items-center justify-center w-36 h-36 shrink-0">
                    <svg className="w-36 h-36 -rotate-90" viewBox="0 0 120 120">
                      <circle cx="60" cy="60" r="52" fill="none" strokeWidth="8" className="stroke-muted" />
                      <circle
                        cx="60" cy="60" r="52" fill="none" strokeWidth="8"
                        strokeDasharray={`${2 * Math.PI * 52}`}
                        strokeDashoffset={`${2 * Math.PI * 52 * (1 - (average_confidence || 0))}`}
                        strokeLinecap="round"
                        className={cn('transition-all duration-1000', gauge.stroke)}
                      />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className={cn('text-4xl font-bold', gauge.text)}>{confidencePct}%</span>
                      <span className="text-[10px] text-muted-foreground uppercase tracking-wider">confianza</span>
                    </div>
                  </div>

                  {/* Stats grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 flex-1 w-full">
                    <div className="text-center p-3 rounded-lg bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20">
                      <div className="text-2xl font-bold text-emerald-600">{verifiedCount}</div>
                      <div className="text-[10px] uppercase tracking-wider text-emerald-600/70">Verificados</div>
                    </div>
                    <div className="text-center p-3 rounded-lg bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
                      <div className="text-2xl font-bold text-amber-600">{correctedCount}</div>
                      <div className="text-[10px] uppercase tracking-wider text-amber-600/70">Corregidos</div>
                    </div>
                    <div className="text-center p-3 rounded-lg bg-red-50 dark:bg-destructive/10 border border-red-200 dark:border-destructive/20">
                      <div className="text-2xl font-bold text-red-600 dark:text-destructive">{rejectedCount}</div>
                      <div className="text-[10px] uppercase tracking-wider text-red-600/70 dark:text-destructive/70">Rechazados</div>
                    </div>
                    <div className="text-center p-3 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20">
                      <div className={cn('text-2xl font-bold', gauge.text)}>{confidencePct}%</div>
                      <div className="text-[10px] uppercase tracking-wider text-blue-600/70">Confianza</div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* ── Claims Detail ───────────────────────────────────────── */}
            <Card>
              <CardContent className="p-6">
                <h2 className="text-base font-semibold mb-4">
                  Detalle de Claims ({claims.length})
                </h2>
                <div className="space-y-4">
                  {claims.map((claim, idx) => (
                    <ClaimDetailCard key={claim.claim_id} claim={claim} index={idx + 1} />
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* ── Global Sources Table ────────────────────────────────── */}
            {globalSources.length > 0 && (
              <Card>
                <CardContent className="p-6">
                  <h2 className="text-base font-semibold mb-4">
                    Fuentes Consultadas ({globalSources.length})
                  </h2>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left">
                          <th className="pb-2 font-medium text-muted-foreground w-32">Tipo</th>
                          <th className="pb-2 font-medium text-muted-foreground">Título / ID</th>
                          <th className="pb-2 font-medium text-muted-foreground w-40">ROJ / ECLI</th>
                          <th className="pb-2 font-medium text-muted-foreground w-20 text-right">Enlace</th>
                        </tr>
                      </thead>
                      <tbody>
                        {globalSources.map((source, idx) => (
                          <GlobalSourceRow key={source.id || idx} source={source} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* ── DOI Validation ──────────────────────────────────────── */}
            {verified.doi_validations && verified.doi_validations.length > 0 && (
              <Card>
                <CardContent className="p-6">
                  <h2 className="text-base font-semibold mb-4">
                    Validación Bibliográfica ({verified.doi_validations.filter(d => d.valid).length}/{verified.doi_validations.length} DOIs válidos)
                  </h2>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left">
                          <th className="pb-2 font-medium text-muted-foreground w-20">Estado</th>
                          <th className="pb-2 font-medium text-muted-foreground w-48">DOI</th>
                          <th className="pb-2 font-medium text-muted-foreground">Publicación</th>
                        </tr>
                      </thead>
                      <tbody>
                        {verified.doi_validations.map((dv, idx) => (
                          <DoiValidationRow key={idx} validation={dv} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* ── Footer ──────────────────────────────────────────────── */}
            <div className="text-center py-4">
              <p className="text-xs text-muted-foreground">
                Generado por NouxCubeIA
                {execution_time_ms
                  ? ` — Tiempo de ejecución: ${execution_time_ms < 1000 ? `${Math.round(execution_time_ms)}ms` : `${(execution_time_ms / 1000).toFixed(1)}s`}`
                  : ''}
              </p>
              <Button asChild variant="ghost" size="sm" className="mt-2 gap-1.5">
                <Link href="/">
                  <IconArrowLeft className="h-3.5 w-3.5" />
                  Volver al chat
                </Link>
              </Button>
            </div>
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

// ─── Claim Detail Card ───────────────────────────────────────────────────────

function ClaimDetailCard({ claim, index }: { claim: VerifiedClaimInfo; index: number }) {
  const config = getStatusConfig(claim.status)
  const isRejected = claim.status === 'rejected'
  const isCorrected = claim.status === 'corrected'

  return (
    <div className={cn('border-l-[3px] rounded-r-lg p-4', config.borderColor, config.bgColor)}>
      {/* Claim header */}
      <div className="flex items-start justify-between gap-3">
        <p className={cn(
          'text-sm leading-relaxed flex-1 text-gray-800 dark:text-gray-200',
          isRejected && 'line-through text-muted-foreground'
        )}>
          <span className="font-bold text-gray-500 dark:text-gray-400">#{index}</span>{' '}
          {claim.claim_text}
        </p>
        <div className="flex items-center gap-2 shrink-0">
          {claim.confidence !== undefined && (
            <span className="text-xs font-mono text-muted-foreground">
              {Math.round(claim.confidence * 100)}%
            </span>
          )}
          <Badge className={cn('text-[10px] px-2 py-0.5 font-mono uppercase gap-1', config.badgeColor)}>
            {config.icon}
            {config.label}
          </Badge>
          {claim.verification_type && (
            <Badge variant="outline" className={cn('text-[9px] px-1.5 py-0 font-mono',
              claim.verification_type === 'corroborated' ? 'bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20' :
              claim.verification_type === 'fidelity_only' ? 'bg-amber-50 text-amber-600 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20' :
              'bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20'
            )}>
              {claim.verification_type === 'corroborated' ? 'Corroborado' :
               claim.verification_type === 'fidelity_only' ? 'Fidelidad' : 'Verificado'}
            </Badge>
          )}
        </div>
      </div>

      {/* Original text for corrected claims */}
      {isCorrected && claim.original_text && (
        <p className="text-xs text-amber-600/70 dark:text-amber-400/70 mt-2 pl-3 border-l-2 border-amber-300 italic">
          Original: {claim.original_text}
        </p>
      )}

      {/* Verification reason */}
      {claim.verification_reason && (
        <p className="text-[11px] text-gray-600 dark:text-gray-300 mt-2 pl-3 border-l-2 border-gray-300 dark:border-gray-600 italic leading-relaxed">
          {claim.verification_reason}
        </p>
      )}

      {/* Per-claim evidence sources */}
      {claim.evidence_sources && claim.evidence_sources.length > 0 && (
        <div className="mt-3 pt-3 border-t border-dashed border-current/10">
          <p className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-2 font-medium">
            Fuentes de validación
          </p>
          <div className="space-y-1.5">
            {claim.evidence_sources.map((src, i) => (
              <EvidenceSourceRow key={src.id || i} source={src} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Evidence Source Row (per-claim) ─────────────────────────────────────────

function EvidenceSourceRow({ source }: { source: VerifiedSource }) {
  const icon = getSourceIcon(source)
  const label = getSourceLabel(source)
  const title = source.title || source.roj || source.id

  return (
    <div className="flex items-center gap-2 text-xs">
      {icon}
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className="truncate flex-1 text-gray-800 dark:text-gray-200">{title}</span>
      {source.roj && (
        <span className="text-[10px] font-mono text-purple-500 shrink-0">{source.roj}</span>
      )}
      {source.url ? (
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-500 hover:underline shrink-0"
        >
          &#x2197;
        </a>
      ) : (
        <span className="text-muted-foreground shrink-0">—</span>
      )}
    </div>
  )
}

// ─── Global Source Row (table) ───────────────────────────────────────────────

function GlobalSourceRow({ source }: { source: VerifiedSource }) {
  const icon = getSourceIcon(source)
  const label = getSourceLabel(source)

  return (
    <tr className="border-b border-muted/50">
      <td className="py-2.5 align-top">
        <span className="flex items-center gap-1.5">
          {icon}
          <span className="text-muted-foreground">{label}</span>
        </span>
      </td>
      <td className="py-2.5 align-top text-gray-800 dark:text-gray-200">
        {source.title || source.id}
      </td>
      <td className="py-2.5 align-top text-xs font-mono text-purple-600 dark:text-purple-400">
        {source.roj || source.ecli || '—'}
      </td>
      <td className="py-2.5 align-top text-right">
        {source.url ? (
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-500 hover:underline"
          >
            &#x2197;
          </a>
        ) : '—'}
      </td>
    </tr>
  )
}

// ─── DOI Validation Row ──────────────────────────────────────────────────────

function DoiValidationRow({ validation }: { validation: DoiValidation }) {
  const meta = validation.metadata

  return (
    <tr className="border-b border-muted/50">
      <td className="py-2.5 align-top">
        {validation.valid ? (
          <span className="flex items-center gap-1.5 text-emerald-600">
            <IconCircleCheck className="h-3.5 w-3.5" />
            Válido
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-red-500">
            <IconCircleX className="h-3.5 w-3.5" />
            Inválido
          </span>
        )}
      </td>
      <td className="py-2.5 align-top font-mono text-xs">
        {validation.valid ? (
          <a
            href={`https://doi.org/${validation.doi}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-500 hover:underline"
          >
            {validation.doi}
          </a>
        ) : (
          <span className="text-red-400">{validation.doi}</span>
        )}
      </td>
      <td className="py-2.5 align-top">
        {meta?.title ? (
          <>
            <span>{meta.title}</span>
            {meta.authors && meta.authors.length > 0 && (
              <span className="text-muted-foreground"> — {meta.authors.slice(0, 3).join(', ')}</span>
            )}
            {meta.year && <span className="text-muted-foreground"> ({meta.year})</span>}
          </>
        ) : (
          <span className="text-muted-foreground italic">No se pudo resolver</span>
        )}
      </td>
    </tr>
  )
}

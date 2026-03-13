'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  IconCircleCheck,
  IconCircleX,
  IconCopy,
  IconCheck,
  IconFileCheck,
  IconDownload,
  IconLoader2,
  IconAlertTriangle,
  IconWorld,
  IconPaperclip,
  IconFile,
  IconFileTypePdf,
  IconFileTypeDocx,
  IconZoomIn,
  IconZoomOut,
  IconZoomReset,
  IconPrinter,
  IconExternalLink,
  IconScale,
  IconEdit,
  IconLock,
  IconSend,
} from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { VerifiedGenerationMetadata, VerifiedSource, VerificationType, VerifiedClaimInfo } from '@/lib/types/emma'
import type { ReviewDecision } from '@/lib/services/verified-generation.service'
import { API_CONFIG } from '@/lib/config'
import { DocumentViewer, verifiedToViewerDocument } from '@/components/document-viewer'

interface VerifiedDocumentResultProps {
  content: string
  verified: VerifiedGenerationMetadata
  /** HITL: callback to submit review decisions and resume generation */
  onSubmitReview?: (decisions: ReviewDecision[]) => void
  /** HITL: whether the resume stream is loading */
  isResuming?: boolean
}

const ZOOM_STEP = 0.1
const ZOOM_MIN = 0.5
const ZOOM_MAX = 2.0

export function VerifiedDocumentResult({ content, verified, onSubmitReview, isResuming }: VerifiedDocumentResultProps) {
  const router = useRouter()
  const [copied, setCopied] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [fitZoom, setFitZoom] = useState(0.65)
  const [zoom, setZoom] = useState<number | null>(null)
  const effectiveZoom = zoom ?? fitZoom
  const { claims, verified_count, rejected_count, total_claims, execution_time_ms, average_confidence } = verified

  // HITL review state
  const isReviewPhase = verified.current_phase === 'review'
  const [reviewDecisions, setReviewDecisions] = useState<Record<string, ReviewDecision>>({})

  const handleReviewDecision = (claimId: string, action: 'approve' | 'reject' | 'edit', editedText?: string) => {
    setReviewDecisions(prev => ({
      ...prev,
      [claimId]: { claim_id: claimId, action, edited_text: editedText },
    }))
  }

  const handleSubmitReview = () => {
    if (!onSubmitReview) return
    // Build decisions: only include claims that need review + have a decision
    const decisions = claims
      .filter(c => c.needs_review)
      .map(c => reviewDecisions[c.claim_id] || { claim_id: c.claim_id, action: 'approve' as const })
    onSubmitReview(decisions)
  }

  const reviewClaimsCount = claims.filter(c => c.needs_review).length
  const decisionsCount = Object.keys(reviewDecisions).length

  const handleViewDetails = () => {
    if (!verified.session_id) return
    sessionStorage.setItem(
      `verified_session_${verified.session_id}`,
      JSON.stringify(verified)
    )
    router.push(`/verified/${verified.session_id}`)
  }
  const documentText = verified.document_text || content
  const correctedCount = claims.filter(c => c.status === 'corrected').length

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(documentText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // fallback
    }
  }

  const downloadFile = async (format: 'pdf' | 'docx') => {
    if (!verified.session_id) return
    setIsDownloading(true)
    try {
      const stored = typeof window !== 'undefined' ? sessionStorage.getItem('nexus_sso_tokens') : null
      const token = stored ? JSON.parse(stored).access_token : null
      const endpoint = format === 'pdf'
        ? API_CONFIG.ENDPOINTS.EMMA_VERIFIED_SESSION_PDF(verified.session_id)
        : API_CONFIG.ENDPOINTS.EMMA_VERIFIED_SESSION_DOCX(verified.session_id)
      const url = `/api/v1${endpoint}`
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token || ''}` },
      })
      if (!response.ok) throw new Error(`${format.toUpperCase()} generation failed`)
      const blob = await response.blob()
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = blobUrl
      a.download = `informe_verificado_${verified.session_id.slice(0, 8)}.${format}`
      a.click()
      URL.revokeObjectURL(blobUrl)
    } catch {
      // silent fail
    } finally {
      setIsDownloading(false)
    }
  }

  const confidencePct = Math.round((average_confidence || 0) * 100)
  const gaugeColor = confidencePct >= 70
    ? 'text-emerald-500'
    : confidencePct >= 40
      ? 'text-amber-500'
      : 'text-red-500'

  const now = new Date()
  const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`

  return (
    <div className={cn('bg-card border rounded-xl overflow-hidden')}>
      {/* Header bar with actions */}
      <div className="flex items-center justify-between p-4 border-b bg-emerald-500/5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center">
            <IconFileCheck className="h-5 w-5 text-emerald-600" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-sm">Documento Verificado</h3>
              {verified.session_id && (
                <button
                  onClick={handleViewDetails}
                  className="text-xs text-emerald-600 hover:text-emerald-700 hover:underline flex items-center gap-0.5"
                >
                  Ver más detalles
                  <IconExternalLink className="h-3 w-3" />
                </button>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {total_claims} claims analizados
              {execution_time_ms ? ` · ${execution_time_ms < 1000 ? `${Math.round(execution_time_ms)}ms` : `${(execution_time_ms / 1000).toFixed(1)}s`}` : ''}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {/* Zoom controls */}
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setZoom(Math.max(effectiveZoom - ZOOM_STEP, ZOOM_MIN))} disabled={effectiveZoom <= ZOOM_MIN} title="Alejar">
            <IconZoomOut className="h-4 w-4" />
          </Button>
          <span className="text-xs font-mono text-muted-foreground w-10 text-center">{Math.round(effectiveZoom * 100)}%</span>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setZoom(Math.min(effectiveZoom + ZOOM_STEP, ZOOM_MAX))} disabled={effectiveZoom >= ZOOM_MAX} title="Acercar">
            <IconZoomIn className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setZoom(null)} title="Ajustar al ancho">
            <IconZoomReset className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => window.print()} title="Imprimir">
            <IconPrinter className="h-4 w-4" />
          </Button>

          <Separator orientation="vertical" className="h-5 mx-1" />

          {/* Copy & Download */}
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopy}
            className="gap-1.5"
          >
            {copied ? <IconCheck className="h-3.5 w-3.5" /> : <IconCopy className="h-3.5 w-3.5" />}
            {copied ? 'Copiado' : 'Copiar'}
          </Button>
          {verified.session_id && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isDownloading}
                  className="gap-1.5"
                >
                  {isDownloading
                    ? <IconLoader2 className="h-3.5 w-3.5 animate-spin" />
                    : <IconDownload className="h-3.5 w-3.5" />
                  }
                  Descargar
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => downloadFile('pdf')} className="gap-2">
                  <IconFileTypePdf className="h-4 w-4 text-red-500" />
                  PDF
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => downloadFile('docx')} className="gap-2">
                  <IconFileTypeDocx className="h-4 w-4 text-blue-500" />
                  Word (.docx)
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      {/* Confidence Gauge + Stats */}
      <div className="p-6 text-center">
        <div className="relative inline-flex items-center justify-center w-32 h-32">
          <svg className="w-32 h-32 -rotate-90" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" fill="none" strokeWidth="8" className="stroke-muted" />
            <circle
              cx="60" cy="60" r="52" fill="none" strokeWidth="8"
              strokeDasharray={`${2 * Math.PI * 52}`}
              strokeDashoffset={`${2 * Math.PI * 52 * (1 - (average_confidence || 0))}`}
              strokeLinecap="round"
              className={cn('transition-all duration-1000', gaugeColor.replace('text-', 'stroke-'))}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={cn('text-3xl font-bold', gaugeColor)}>{confidencePct}%</span>
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">confianza</span>
          </div>
        </div>

        <div className="flex justify-center gap-3 mt-3">
          <Badge variant="outline" className="text-xs bg-emerald-500/10 text-emerald-600 border-emerald-500/20">
            <IconCircleCheck className="h-3 w-3 mr-1" />
            {verified_count} verificados
          </Badge>
          {correctedCount > 0 && (
            <Badge variant="outline" className="text-xs bg-amber-500/10 text-amber-600 border-amber-500/20">
              <IconAlertTriangle className="h-3 w-3 mr-1" />
              {correctedCount} corregidos
            </Badge>
          )}
          {rejected_count > 0 && (
            <Badge variant="outline" className="text-xs bg-destructive/10 text-destructive border-destructive/20">
              <IconCircleX className="h-3 w-3 mr-1" />
              {rejected_count} rechazados
            </Badge>
          )}
        </div>
      </div>

      {/* Document Viewer */}
      <DocumentViewer documents={[verifiedToViewerDocument(verified)]} zoom={effectiveZoom} onFitZoomCalculated={setFitZoom}>
        {/* ── Informe de Verificación ── */}
        <h2 className="text-base font-bold mb-3">Informe de Verificación</h2>
        <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5 mb-5">
          <p><span className="font-semibold text-gray-700 dark:text-gray-300">Tema:</span> {verified.topic}</p>
          {verified.source_filenames && verified.source_filenames.length > 0 && (
            <p>
              <span className="font-semibold text-gray-700 dark:text-gray-300">
                {verified.source_filenames.length === 1 ? 'Documento fuente:' : 'Documentos fuente:'}
              </span>{' '}
              {verified.source_filenames.join(', ')}
            </p>
          )}
          <p><span className="font-semibold text-gray-700 dark:text-gray-300">Fecha:</span> {dateStr}</p>
          <p><span className="font-semibold text-gray-700 dark:text-gray-300">Sesión:</span> {verified.session_id.slice(0, 16)}…</p>
        </div>

        {/* ── Source Summary ── */}
        {verified.source_summary && (
          <div className="mb-5 p-3 bg-blue-50/50 dark:bg-blue-500/5 rounded-md border border-blue-200 dark:border-blue-500/20">
            <p className="text-[10px] font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wider mb-1">Resumen del documento fuente</p>
            <p className="text-xs text-gray-600 dark:text-gray-300 leading-relaxed">{verified.source_summary}</p>
          </div>
        )}

        {/* ── Stats Grid ── */}
        <div className="grid grid-cols-4 gap-2 mb-6">
          <div className="text-center p-2 rounded-md bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20">
            <div className="text-lg font-bold text-emerald-600">{verified_count}</div>
            <div className="text-[10px] uppercase tracking-wider text-emerald-600/70">Verificados</div>
          </div>
          <div className="text-center p-2 rounded-md bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
            <div className="text-lg font-bold text-amber-600">{correctedCount}</div>
            <div className="text-[10px] uppercase tracking-wider text-amber-600/70">Corregidos</div>
          </div>
          <div className="text-center p-2 rounded-md bg-red-50 dark:bg-destructive/10 border border-red-200 dark:border-destructive/20">
            <div className="text-lg font-bold text-red-600 dark:text-destructive">{rejected_count}</div>
            <div className="text-[10px] uppercase tracking-wider text-red-600/70 dark:text-destructive/70">Rechazados</div>
          </div>
          <div className="text-center p-2 rounded-md bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20">
            <div className={cn('text-lg font-bold', gaugeColor)}>{confidencePct}%</div>
            <div className="text-[10px] uppercase tracking-wider text-blue-600/70">Confianza</div>
          </div>
        </div>

        {/* ── Documento Verificado ── */}
        <h3 className="text-sm font-bold mb-3 pb-2 border-b">Documento Verificado</h3>
        <div className="bg-gray-50/50 dark:bg-muted/30 rounded-md border p-4 mb-6">
          {claims.map((claim, idx) => (
            <p key={claim.claim_id} className={cn(
              'text-sm leading-relaxed',
              idx < claims.length - 1 && 'mb-3',
              claim.status === 'rejected' && 'line-through text-gray-400 dark:text-muted-foreground/60'
            )}>
              {claim.claim_text}
            </p>
          ))}
        </div>

        {/* ── HITL Review Banner ── */}
        {isReviewPhase && (
          <div className="mb-4 p-3 bg-amber-50/80 dark:bg-amber-500/10 rounded-md border border-amber-200 dark:border-amber-500/20">
            <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 mb-1">
              Revisión requerida — {reviewClaimsCount} claim{reviewClaimsCount !== 1 ? 's' : ''} por debajo del umbral de confianza ({Math.round((verified.confidence_threshold || 0.75) * 100)}%)
            </p>
            <p className="text-[10px] text-amber-600/70 dark:text-amber-400/60">
              Aprueba, rechaza o edita los claims marcados. Los claims con alta confianza se aprueban automáticamente.
            </p>
          </div>
        )}

        {/* ── Detalle de Claims ── */}
        <h3 className="text-sm font-bold mb-3 pb-2 border-b">
          {isReviewPhase ? 'Revisión de Claims' : 'Detalle de Claims'} ({claims.length})
        </h3>
        <div className="space-y-3 mb-6">
          {claims.map((claim, idx) => (
            <ClaimDetail
              key={claim.claim_id}
              claim={claim}
              index={idx + 1}
              isReviewPhase={isReviewPhase}
              reviewDecision={reviewDecisions[claim.claim_id]}
              onReviewDecision={handleReviewDecision}
            />
          ))}
        </div>

        {/* ── HITL Submit Review Button ── */}
        {isReviewPhase && onSubmitReview && (
          <div className="mb-6 flex justify-center">
            <button
              onClick={handleSubmitReview}
              disabled={isResuming}
              className={cn(
                'flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-semibold transition-all',
                'bg-emerald-600 text-white hover:bg-emerald-700 shadow-md hover:shadow-lg',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              {isResuming ? (
                <>
                  <IconLoader2 className="h-4 w-4 animate-spin" />
                  Generando documento...
                </>
              ) : (
                <>
                  <IconSend className="h-4 w-4" />
                  Enviar revisión y generar documento
                </>
              )}
            </button>
          </div>
        )}

        {/* ── Fuentes Consultadas ── */}
        {verified.sources && verified.sources.length > 0 && (
          <>
            <h3 className="text-sm font-bold mb-3 pb-2 border-b">
              Fuentes Consultadas ({verified.sources.length})
            </h3>
            <table className="w-full text-xs mb-6">
              <thead>
                <tr className="border-b text-left">
                  <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400 w-20">Tipo</th>
                  <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400">Título / ID</th>
                  <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400 w-20 text-right">URL</th>
                </tr>
              </thead>
              <tbody>
                {verified.sources.map((source, idx) => (
                  <SourceRow key={source.id || idx} source={source} />
                ))}
              </tbody>
            </table>
          </>
        )}

        {/* ── Validación Bibliográfica (DOI) ── */}
        {verified.doi_validations && verified.doi_validations.length > 0 && (
          <>
            <h3 className="text-sm font-bold mb-3 pb-2 border-b">
              Validación Bibliográfica ({verified.doi_validations.filter(d => d.valid).length}/{verified.doi_validations.length} DOIs válidos)
            </h3>
            <table className="w-full text-xs mb-6">
              <thead>
                <tr className="border-b text-left">
                  <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400 w-16">Estado</th>
                  <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400">DOI</th>
                  <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400">Publicación</th>
                </tr>
              </thead>
              <tbody>
                {verified.doi_validations.map((dv, idx) => (
                  <tr key={idx} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="py-1.5 align-top">
                      {dv.valid ? (
                        <span className="inline-flex items-center gap-1 text-green-600">
                          <IconCircleCheck className="h-3 w-3" /> Válido
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-red-500">
                          <IconCircleX className="h-3 w-3" /> Inválido
                        </span>
                      )}
                    </td>
                    <td className="py-1.5 align-top font-mono text-[10px]">
                      {dv.valid ? (
                        <a href={`https://doi.org/${dv.doi}`} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
                          {dv.doi}
                        </a>
                      ) : (
                        <span className="text-red-400">{dv.doi}</span>
                      )}
                    </td>
                    <td className="py-1.5 align-top text-gray-600 dark:text-gray-300">
                      {dv.metadata?.title ? (
                        <>
                          {dv.metadata.title}
                          {dv.metadata.authors && dv.metadata.authors.length > 0 && (
                            <span className="text-gray-400"> — {dv.metadata.authors.slice(0, 3).join(', ')}</span>
                          )}
                          {dv.metadata.year && <span className="text-gray-400"> ({dv.metadata.year})</span>}
                        </>
                      ) : (
                        <span className="text-gray-400 italic">No se pudo resolver</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {/* ── Metodología ── */}
        <h3 className="text-sm font-bold mb-3 pb-2 border-b">Metodología de Verificación</h3>
        <p className="text-[10px] text-gray-500 dark:text-gray-400 mb-3 leading-relaxed">
          Cada afirmación se evalúa en dos niveles independientes, siguiendo principios de{' '}
          <em>SAFE</em> (Google DeepMind, 2024), <em>CoVe</em> (Meta, 2024) y <em>FFCI</em> (Koto et al.):
        </p>
        <table className="w-full text-[10px] mb-4">
          <thead>
            <tr className="border-b text-left">
              <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400 w-28">Tipo</th>
              <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400">Significado</th>
              <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400 w-20 text-center">Conf. máx.</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-gray-100 dark:border-gray-800">
              <td className="py-1.5 align-top">
                <Badge variant="outline" className="text-[8px] px-1 py-0 font-mono bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400 border-amber-200 dark:border-amber-500/20">
                  Fidelidad
                </Badge>
              </td>
              <td className="py-1.5 align-top text-gray-600 dark:text-gray-300">
                La afirmación representa fielmente el documento fuente (NLI entailment), pero no se encontró evidencia independiente.
              </td>
              <td className="py-1.5 align-top text-center font-bold text-amber-600">80%</td>
            </tr>
            <tr className="border-b border-gray-100 dark:border-gray-800">
              <td className="py-1.5 align-top">
                <Badge variant="outline" className="text-[8px] px-1 py-0 font-mono bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20">
                  Corroborado
                </Badge>
              </td>
              <td className="py-1.5 align-top text-gray-600 dark:text-gray-300">
                Fiel al documento fuente <strong>y</strong> respaldada por evidencia independiente (otros documentos, legislación, web).
              </td>
              <td className="py-1.5 align-top text-center font-bold text-emerald-600">100%</td>
            </tr>
            <tr className="border-b border-gray-100 dark:border-gray-800">
              <td className="py-1.5 align-top">
                <Badge variant="outline" className="text-[8px] px-1 py-0 font-mono bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400 border-blue-200 dark:border-blue-500/20">
                  Verificado
                </Badge>
              </td>
              <td className="py-1.5 align-top text-gray-600 dark:text-gray-300">
                Sin documento fuente. Respaldada exclusivamente por evidencia independiente externa.
              </td>
              <td className="py-1.5 align-top text-center font-bold text-blue-600">100%</td>
            </tr>
          </tbody>
        </table>
        <p className="text-[9px] text-gray-400 dark:text-gray-500 leading-relaxed mb-6">
          <strong>Tier 1 — Fidelidad:</strong> Evaluación NLI que verifica si la afirmación está contenida (<em>entailed</em>) en el texto fuente, basada en FACTS Grounding (Google DeepMind, 2024). Confianza limitada al 80% porque la fuente de generación y verificación coinciden.
          {' '}<strong>Tier 2 — Corroboración externa:</strong> Búsqueda en fuentes independientes (excluyendo documentos fuente), siguiendo SAFE (Google DeepMind, 2024) y CoVe (Meta, 2024).
        </p>

        {/* ── Footer ── */}
        <div className="pt-3 border-t text-center">
          <p className="text-[10px] text-gray-400 dark:text-gray-500">
            Generado por NouxCubeIA
            {execution_time_ms ? ` — Tiempo de ejecución: ${Math.round(execution_time_ms)}ms` : ''}
          </p>
        </div>
      </DocumentViewer>
    </div>
  )
}

/** Claim detail card matching PDF "Detalle de Claims" — all info always visible */
function ClaimDetail({
  claim,
  index,
  isReviewPhase = false,
  reviewDecision,
  onReviewDecision,
}: {
  claim: VerifiedGenerationMetadata['claims'][0]
  index: number
  isReviewPhase?: boolean
  reviewDecision?: ReviewDecision
  onReviewDecision?: (claimId: string, action: 'approve' | 'reject' | 'edit', editedText?: string) => void
}) {
  const [isEditing, setIsEditing] = useState(false)
  const [editText, setEditText] = useState(claim.claim_text)

  const isVerified = claim.status === 'verified'
  const isCorrected = claim.status === 'corrected'
  const isRejected = claim.status === 'rejected'
  const needsReview = claim.needs_review && isReviewPhase
  const isAutoApproved = claim.auto_approved || (!claim.needs_review && isReviewPhase)

  // In review phase, override colors based on decision
  const decisionAction = reviewDecision?.action
  const effectiveRejected = isRejected || decisionAction === 'reject'
  const effectiveEdited = decisionAction === 'edit'

  const borderColor = effectiveRejected
    ? 'border-l-destructive'
    : effectiveEdited
      ? 'border-l-blue-500'
      : needsReview
        ? 'border-l-amber-500'
        : isVerified
          ? 'border-l-emerald-500'
          : isCorrected
            ? 'border-l-amber-500'
            : 'border-l-destructive'

  const bgColor = effectiveRejected
    ? 'bg-red-50/50 dark:bg-destructive/5'
    : effectiveEdited
      ? 'bg-blue-50/50 dark:bg-blue-500/5'
      : needsReview
        ? 'bg-amber-50/30 dark:bg-amber-500/5'
        : isVerified
          ? 'bg-emerald-50/50 dark:bg-emerald-500/5'
          : isCorrected
            ? 'bg-amber-50/50 dark:bg-amber-500/5'
            : 'bg-red-50/50 dark:bg-destructive/5'

  const statusLabel = effectiveRejected ? 'RECHAZADO'
    : effectiveEdited ? 'EDITADO'
    : isVerified ? 'VERIFICADO'
    : isCorrected ? 'CORREGIDO'
    : 'RECHAZADO'
  const statusColor = effectiveRejected
    ? 'bg-red-100 text-red-700 dark:bg-destructive/20 dark:text-destructive'
    : effectiveEdited
      ? 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400'
      : isVerified
        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400'
        : isCorrected
          ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400'
          : 'bg-red-100 text-red-700 dark:bg-destructive/20 dark:text-destructive'

  const statusIcon = effectiveRejected
    ? <IconCircleX className="h-3 w-3" />
    : effectiveEdited
      ? <IconEdit className="h-3 w-3" />
      : isVerified
        ? <IconCircleCheck className="h-3 w-3" />
        : isCorrected
          ? <IconAlertTriangle className="h-3 w-3" />
          : <IconCircleX className="h-3 w-3" />

  const vType = claim.verification_type
  const vTypeLabel = vType === 'corroborated' ? 'Corroborado'
    : vType === 'fidelity_only' ? 'Fidelidad'
    : vType === 'independent' ? 'Verificado'
    : null
  const vTypeColor = vType === 'corroborated'
    ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/20'
    : vType === 'fidelity_only'
      ? 'bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400 border-amber-200 dark:border-amber-500/20'
      : 'bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400 border-blue-200 dark:border-blue-500/20'

  const handleEditConfirm = () => {
    if (onReviewDecision && editText.trim()) {
      onReviewDecision(claim.claim_id, 'edit', editText.trim())
      setIsEditing(false)
    }
  }

  return (
    <div className={cn('border-l-[3px] rounded-r-md p-3', borderColor, bgColor)}>
      <div className="flex items-start justify-between gap-2">
        <p className={cn(
          'text-xs leading-relaxed flex-1',
          effectiveRejected && 'line-through text-gray-400'
        )}>
          <span className="font-bold text-gray-500 dark:text-gray-400">#{index}</span>{' '}
          {effectiveEdited && reviewDecision?.edited_text ? reviewDecision.edited_text : claim.claim_text}
        </p>
        <div className="flex items-center gap-1.5 shrink-0">
          {claim.confidence !== undefined && (
            <span className="text-[10px] font-mono text-gray-500">{Math.round(claim.confidence * 100)}%</span>
          )}
          {/* Auto-approved lock icon in review phase */}
          {isAutoApproved && isReviewPhase && (
            <IconLock className="h-3 w-3 text-emerald-500" title="Aprobado automáticamente" />
          )}
          <Badge className={cn('text-[9px] px-1.5 py-0 font-mono uppercase gap-1', statusColor)}>
            {statusIcon}
            {statusLabel}
          </Badge>
          {vTypeLabel && (
            <Badge variant="outline" className={cn('text-[8px] px-1 py-0 font-mono', vTypeColor)}>
              {vTypeLabel}
            </Badge>
          )}
        </div>
      </div>

      {/* Original text for corrected claims — always visible */}
      {isCorrected && claim.original_text && (
        <p className="text-[10px] text-amber-600/70 dark:text-amber-400/70 mt-1.5 pl-3 border-l-2 border-amber-300 italic">
          Original: {claim.original_text}
        </p>
      )}

      {/* Verification reason */}
      {claim.verification_reason && (
        <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-1.5 leading-relaxed italic">
          {claim.verification_reason}
        </p>
      )}

      {/* Per-claim evidence sources */}
      {claim.evidence_sources && claim.evidence_sources.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {claim.evidence_sources.slice(0, 3).map((src, i) => (
            <ClaimSourceChip key={src.id || i} source={src} />
          ))}
          {claim.evidence_sources.length > 3 && (
            <span className="text-[10px] text-muted-foreground self-center">
              +{claim.evidence_sources.length - 3} más
            </span>
          )}
        </div>
      )}

      {/* ── HITL Review Actions ── */}
      {needsReview && onReviewDecision && (
        <div className="mt-2.5 pt-2 border-t border-amber-200/50 dark:border-amber-500/20">
          {isEditing ? (
            <div className="space-y-2">
              <textarea
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                className="w-full text-xs p-2 rounded-md border bg-white dark:bg-muted resize-y min-h-[60px]"
                rows={3}
              />
              <div className="flex gap-1.5">
                <Button size="sm" variant="default" className="h-6 text-[10px] px-2 gap-1" onClick={handleEditConfirm}>
                  <IconCheck className="h-3 w-3" /> Confirmar
                </Button>
                <Button size="sm" variant="ghost" className="h-6 text-[10px] px-2" onClick={() => { setIsEditing(false); setEditText(claim.claim_text) }}>
                  Cancelar
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <Button
                size="sm"
                variant={decisionAction === 'approve' ? 'default' : 'outline'}
                className={cn(
                  'h-6 text-[10px] px-2 gap-1',
                  decisionAction === 'approve' && 'bg-emerald-600 hover:bg-emerald-700 text-white'
                )}
                onClick={() => onReviewDecision(claim.claim_id, 'approve')}
              >
                <IconCircleCheck className="h-3 w-3" /> Aprobar
              </Button>
              <Button
                size="sm"
                variant={decisionAction === 'reject' ? 'destructive' : 'outline'}
                className="h-6 text-[10px] px-2 gap-1"
                onClick={() => onReviewDecision(claim.claim_id, 'reject')}
              >
                <IconCircleX className="h-3 w-3" /> Rechazar
              </Button>
              <Button
                size="sm"
                variant={decisionAction === 'edit' ? 'default' : 'outline'}
                className={cn(
                  'h-6 text-[10px] px-2 gap-1',
                  decisionAction === 'edit' && 'bg-blue-600 hover:bg-blue-700 text-white'
                )}
                onClick={() => setIsEditing(true)}
              >
                <IconEdit className="h-3 w-3" /> Editar
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Compact chip for a per-claim evidence source */
function ClaimSourceChip({ source }: { source: VerifiedSource }) {
  const type = source.source || 'internal'
  const isWeb = type === 'web' || type === 'public_knowledge'
  const isJurisprudence = !!source.roj || !!source.ecli
  const isDoi = type === 'doi' || type === 'crossref'
  const isDoiInvalid = type === 'doi_invalid'
  const isDoiMismatch = type === 'doi_mismatch'

  const icon = isJurisprudence
    ? <IconScale className="h-2.5 w-2.5 text-purple-500 shrink-0" />
    : isDoi
      ? <IconFileCheck className="h-2.5 w-2.5 text-green-600 shrink-0" />
      : isDoiInvalid
        ? <IconCircleX className="h-2.5 w-2.5 text-red-500 shrink-0" />
        : isDoiMismatch
          ? <IconAlertTriangle className="h-2.5 w-2.5 text-amber-500 shrink-0" />
          : isWeb
            ? <IconWorld className="h-2.5 w-2.5 text-blue-500 shrink-0" />
            : <IconFile className="h-2.5 w-2.5 text-gray-400 shrink-0" />

  const label = source.title || source.roj || source.id
  const truncated = label && label.length > 30 ? label.slice(0, 28) + '…' : label

  const chip = (
    <span className="inline-flex items-center gap-1 text-[10px] bg-muted/50 rounded px-1.5 py-0.5 max-w-[200px]">
      {icon}
      <span className="truncate">{truncated}</span>
    </span>
  )

  if (source.url) {
    return (
      <a href={source.url} target="_blank" rel="noopener noreferrer" className="hover:opacity-80">
        {chip}
      </a>
    )
  }
  return chip
}

/** Source row as table row matching PDF "Fuentes Consultadas" */
function SourceRow({ source }: { source: VerifiedSource }) {
  const sourceType = source.source || 'internal'
  const icon = sourceType === 'web' || sourceType === 'public_knowledge'
    ? <IconWorld className="h-3 w-3 text-blue-500 inline" />
    : sourceType === 'uploaded'
      ? <IconPaperclip className="h-3 w-3 text-amber-500 inline" />
      : sourceType === 'doi' || sourceType === 'crossref'
        ? <IconFileCheck className="h-3 w-3 text-green-600 inline" />
        : sourceType === 'doi_invalid'
          ? <IconCircleX className="h-3 w-3 text-red-500 inline" />
          : sourceType === 'doi_mismatch'
            ? <IconAlertTriangle className="h-3 w-3 text-amber-500 inline" />
            : <IconFile className="h-3 w-3 text-gray-400 inline" />
  const label = sourceType === 'web' || sourceType === 'public_knowledge' ? 'Web'
    : sourceType === 'uploaded' ? 'Cargado'
    : sourceType === 'doi' ? 'DOI Validado'
    : sourceType === 'crossref' ? 'CrossRef'
    : sourceType === 'doi_invalid' ? 'DOI Inválido'
    : sourceType === 'doi_mismatch' ? 'DOI No Corresponde'
    : sourceType === 'citation_unverified' ? 'Cita No Verificada'
    : 'Interno'

  return (
    <tr className="border-b border-gray-100 dark:border-gray-800">
      <td className="py-1.5 align-top">
        <span className="flex items-center gap-1">
          {icon}
          <span className="text-gray-500">{label}</span>
        </span>
      </td>
      <td className="py-1.5 align-top">
        {source.title || source.id}
      </td>
      <td className="py-1.5 align-top text-right text-gray-400">
        {source.url ? (
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-500 hover:underline"
          >
            ↗
          </a>
        ) : '—'}
      </td>
    </tr>
  )
}

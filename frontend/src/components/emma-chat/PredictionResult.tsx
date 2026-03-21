'use client'

import { useState } from 'react'
import {
  IconDownload,
  IconLoader2,
  IconAlertTriangle,
  IconCircleCheck,
  IconCircleX,
  IconScale,
  IconFileTypePdf,
  IconFileTypeDocx,
  IconZoomIn,
  IconZoomOut,
  IconZoomReset,
  IconPrinter,
  IconChevronDown,
  IconChevronRight,
  IconGavel,
  IconFile,
  IconWorld,
  IconPaperclip,
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
import { PredictiveAnalysisMetadata, PredictiveFactorInfo, PredictiveMatchInfo, PredictiveSource } from '@/lib/types/emma'
import { downloadPredictivePdf, downloadPredictiveDocx } from '@/lib/services/predictive-analysis.service'
import { DocumentViewer, predictiveToViewerDocument } from '@/components/document-viewer'

interface PredictionResultProps {
  metadata: PredictiveAnalysisMetadata
  className?: string
}

/**
 * Prediction result with paper-sheet document viewer matching verified design.
 */
const ZOOM_STEP = 0.1
const ZOOM_MIN = 0.5
const ZOOM_MAX = 2.0

export function PredictionResult({ metadata, className }: PredictionResultProps) {
  const [isDownloading, setIsDownloading] = useState(false)
  const [fitZoom, setFitZoom] = useState(0.65)
  const [zoom, setZoom] = useState<number | null>(null)
  const effectiveZoom = zoom ?? fitZoom

  const {
    probability,
    primary_outcome,
    outcome_probabilities,
    factors,
    recommendation,
    disclaimer,
    execution_time_ms,
    session_id,
    tenant_id,
  } = metadata

  const probabilityPct = Math.round((probability || 0) * 100)

  const downloadFile = async (format: 'pdf' | 'docx') => {
    if (!session_id || !tenant_id) return
    setIsDownloading(true)
    try {
      const blob = format === 'pdf'
        ? await downloadPredictivePdf(session_id, tenant_id)
        : await downloadPredictiveDocx(session_id, tenant_id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `informe_predictivo_${session_id.slice(0, 8)}.${format}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error(`${format.toUpperCase()} download failed:`, err)
    } finally {
      setIsDownloading(false)
    }
  }

  // Translate outcome labels
  const outcomeLabels: Record<string, string> = {
    favorable: 'Favorable',
    unfavorable: 'Desfavorable',
    mixed: 'Mixto',
    neutral: 'Neutral',
    positive: 'Positivo',
    negative: 'Negativo',
    uncertain: 'Incierto',
  }
  const translateOutcome = (key: string) => outcomeLabels[key.toLowerCase()] || key

  // Color based on probability
  const gaugeColor = probabilityPct >= 70
    ? 'text-emerald-500'
    : probabilityPct >= 40
      ? 'text-amber-500'
      : 'text-red-500'

  const weightedCount = factors.filter(f => f.status === 'weighted').length
  const rejectedCount = factors.filter(f => f.status === 'rejected').length
  const insufficientEvidence = weightedCount === 0
  const hasJurisprudence = metadata.sources?.some(s => s.source === 'jurisprudence') ?? false

  const now = new Date()
  const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`

  return (
    <div className={cn('bg-card border rounded-xl overflow-hidden', className)}>
      {/* Header bar with actions */}
      <div className="flex items-center justify-between p-4 border-b bg-blue-500/5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-blue-500/10 flex items-center justify-center">
            <IconScale className="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <h3 className="font-semibold text-sm">Análisis Predictivo</h3>
            <p className="text-xs text-muted-foreground">
              {factors.length} factores analizados
              {execution_time_ms ? ` · ${(execution_time_ms / 1000).toFixed(1)}s` : ''}
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

          {session_id && (
            <>
              <Separator orientation="vertical" className="h-5 mx-1" />

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
            </>
          )}
        </div>
      </div>

      {/* Probability Gauge */}
      <div className="p-6 text-center">
        {insufficientEvidence ? (
          /* Insufficient evidence state */
          <div className="flex flex-col items-center gap-3">
            <div className="relative inline-flex items-center justify-center w-32 h-32">
              <svg className="w-32 h-32 -rotate-90" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="52" fill="none" strokeWidth="8" className="stroke-muted" />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <IconAlertTriangle className="h-8 w-8 text-amber-500 mb-1" />
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider">sin datos</span>
              </div>
            </div>
            <p className="text-sm text-muted-foreground max-w-xs">
              Evidencia insuficiente para generar una predicción fiable.
              Todos los factores fueron rechazados por falta de documentación de soporte.
            </p>
          </div>
        ) : (
          /* Normal gauge */
          <>
            <div className="relative inline-flex items-center justify-center w-32 h-32">
              <svg className="w-32 h-32 -rotate-90" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="52" fill="none" strokeWidth="8" className="stroke-muted" />
                <circle
                  cx="60" cy="60" r="52" fill="none" strokeWidth="8"
                  strokeDasharray={`${2 * Math.PI * 52}`}
                  strokeDashoffset={`${2 * Math.PI * 52 * (1 - (probability || 0))}`}
                  strokeLinecap="round"
                  className={cn('transition-all duration-1000', gaugeColor.replace('text-', 'stroke-'))}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className={cn('text-3xl font-bold', gaugeColor)}>{probabilityPct}%</span>
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider">probabilidad</span>
              </div>
            </div>

            {primary_outcome && (
              <p className="mt-3 text-sm font-medium">
                Predicción: <span className="text-blue-600">{translateOutcome(primary_outcome)}</span>
              </p>
            )}

            {/* Outcome probabilities */}
            {outcome_probabilities && Object.keys(outcome_probabilities).length > 1 && (
              <div className="flex justify-center gap-3 mt-3">
                {Object.entries(outcome_probabilities)
                  .sort(([, a], [, b]) => b - a)
                  .map(([key, value]) => (
                    <Badge key={key} variant="outline" className="text-xs">
                      {translateOutcome(key)}: {Math.round(value * 100)}%
                    </Badge>
                  ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Document Viewer */}
      <DocumentViewer documents={[predictiveToViewerDocument(metadata)]} zoom={effectiveZoom} onFitZoomCalculated={setFitZoom}>
        {/* ── Informe Predictivo ── */}
        <h2 className="text-base font-bold mb-3">Informe de Análisis Predictivo</h2>
        <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5 mb-5">
          <p><span className="font-semibold text-gray-700 dark:text-gray-300">Tema:</span> {metadata.case_description || 'N/A'}</p>
          <p><span className="font-semibold text-gray-700 dark:text-gray-300">Fecha:</span> {dateStr}</p>
          {session_id && <p><span className="font-semibold text-gray-700 dark:text-gray-300">Sesión:</span> {session_id.slice(0, 16)}…</p>}
        </div>

        {/* ── Stats Grid ── */}
        <div className="grid grid-cols-4 gap-2 mb-6">
          <div className="text-center p-2 rounded-md bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20">
            <div className={cn('text-lg font-bold', insufficientEvidence ? 'text-muted-foreground' : gaugeColor)}>
              {insufficientEvidence ? '—' : `${probabilityPct}%`}
            </div>
            <div className="text-[10px] uppercase tracking-wider text-blue-600/70">Probabilidad</div>
          </div>
          <div className="text-center p-2 rounded-md bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20">
            <div className="text-lg font-bold text-emerald-600">{weightedCount}</div>
            <div className="text-[10px] uppercase tracking-wider text-emerald-600/70">Ponderados</div>
          </div>
          <div className="text-center p-2 rounded-md bg-red-50 dark:bg-destructive/10 border border-red-200 dark:border-destructive/20">
            <div className="text-lg font-bold text-red-600 dark:text-destructive">{rejectedCount}</div>
            <div className="text-[10px] uppercase tracking-wider text-red-600/70 dark:text-destructive/70">Rechazados</div>
          </div>
          <div className="text-center p-2 rounded-md bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
            <div className="text-lg font-bold text-amber-600">
              {primary_outcome ? translateOutcome(primary_outcome) : '—'}
            </div>
            <div className="text-[10px] uppercase tracking-wider text-amber-600/70">Resultado</div>
          </div>
        </div>

        {/* ── Predicción ── */}
        {outcome_probabilities && Object.keys(outcome_probabilities).length > 0 && (
          <>
            <h3 className="text-sm font-bold mb-3 pb-2 border-b">Distribución de Resultados</h3>
            <div className="space-y-2 mb-6">
              {Object.entries(outcome_probabilities)
                .sort(([, a], [, b]) => b - a)
                .map(([key, value]) => {
                  const pct = Math.round(value * 100)
                  const barColor = key.toLowerCase() === 'favorable' || key.toLowerCase() === 'positive'
                    ? 'bg-emerald-500'
                    : key.toLowerCase() === 'unfavorable' || key.toLowerCase() === 'negative'
                      ? 'bg-red-500'
                      : 'bg-amber-500'
                  return (
                    <div key={key} className="flex items-center gap-3">
                      <span className="text-xs w-24 text-right text-gray-600 dark:text-gray-400">{translateOutcome(key)}</span>
                      <div className="flex-1 h-2 bg-gray-100 dark:bg-muted rounded-full overflow-hidden">
                        <div className={cn('h-full rounded-full transition-all', barColor)} style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs font-mono w-10 text-gray-500">{pct}%</span>
                    </div>
                  )
                })}
            </div>
          </>
        )}

        {/* ── Recomendación ── */}
        {recommendation && (
          <>
            <h3 className="text-sm font-bold mb-3 pb-2 border-b">Recomendación</h3>
            <div className="bg-gray-50/50 dark:bg-muted/30 rounded-md border p-4 mb-6">
              <p className="text-sm leading-relaxed">{recommendation}</p>
            </div>
          </>
        )}

        {/* ── Detalle de Factores ── */}
        <h3 className="text-sm font-bold mb-3 pb-2 border-b">
          Detalle de Factores ({factors.length})
        </h3>
        <div className="space-y-3 mb-6">
          {factors.map((factor, idx) => (
            <FactorDetail key={factor.factor_id || idx} factor={factor} index={idx + 1} />
          ))}
        </div>

        {/* ── Fuentes Consultadas ── */}
        {metadata.sources && metadata.sources.length > 0 && (
          <>
            <h3 className="text-sm font-bold mb-3 pb-2 border-b">
              Fuentes Consultadas ({metadata.sources.length})
            </h3>
            <table className="w-full text-xs mb-6">
              <thead>
                <tr className="border-b text-left">
                  <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400 w-24">Tipo</th>
                  <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400">Título / ID</th>
                  <th className="pb-1.5 font-semibold text-gray-500 dark:text-gray-400 w-20 text-right">URL</th>
                </tr>
              </thead>
              <tbody>
                {metadata.sources.map((source, idx) => (
                  <PredictiveSourceRow key={source.id || idx} source={source} />
                ))}
              </tbody>
            </table>
          </>
        )}

        {/* ── CENDOJ Notice ── */}
        {hasJurisprudence && (
          <div className="flex items-start gap-2 p-3 bg-purple-50/50 dark:bg-purple-500/5 rounded-md border border-purple-200 dark:border-purple-500/20 mb-4">
            <IconGavel className="h-4 w-4 text-purple-500 shrink-0 mt-0.5" />
            <div className="text-[11px] text-gray-500 dark:text-gray-400">
              <p className="font-semibold text-gray-600 dark:text-gray-300 mb-0.5">Jurisprudencia CENDOJ</p>
              <p>
                Las referencias jurisprudenciales se obtienen del Centro de Documentación Judicial (CENDOJ)
                exclusivamente para consulta de uso personal, conforme a las condiciones de acceso del servicio.
                No se almacena ni reproduce el contenido de las resoluciones. Los textos se procesan de forma
                efímera como contexto del análisis y se descartan al finalizar.
              </p>
            </div>
          </div>
        )}

        {/* ── Disclaimer ── */}
        {disclaimer && (
          <div className="flex items-start gap-2 p-3 bg-amber-50/50 dark:bg-amber-500/5 rounded-md border border-amber-200 dark:border-amber-500/20 mb-6">
            <IconAlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <p className="text-[11px] text-gray-500 dark:text-gray-400">{disclaimer}</p>
          </div>
        )}

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

/** Factor detail card with expandable evidence items */
function FactorDetail({ factor, index }: { factor: PredictiveFactorInfo; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const isWeighted = factor.status === 'weighted'
  const isRejected = factor.status === 'rejected'
  const matches = factor.supporting_matches || []

  const borderColor = isWeighted
    ? 'border-l-blue-500'
    : isRejected
      ? 'border-l-destructive'
      : 'border-l-gray-300'

  const bgColor = isWeighted
    ? 'bg-blue-50/50 dark:bg-blue-500/5'
    : isRejected
      ? 'bg-red-50/50 dark:bg-destructive/5'
      : 'bg-gray-50/50 dark:bg-muted/20'

  const statusLabel = isWeighted ? 'PONDERADO' : isRejected ? 'RECHAZADO' : 'ANALIZANDO'
  const statusColor = isWeighted
    ? 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400'
    : isRejected
      ? 'bg-red-100 text-red-700 dark:bg-destructive/20 dark:text-destructive'
      : 'bg-gray-100 text-gray-600 dark:bg-muted dark:text-muted-foreground'

  const statusIcon = isWeighted
    ? <IconCircleCheck className="h-3 w-3" />
    : isRejected
      ? <IconCircleX className="h-3 w-3" />
      : <IconScale className="h-3 w-3" />

  return (
    <div className={cn('border-l-[3px] rounded-r-md p-3', borderColor, bgColor)}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className={cn(
            'text-xs leading-relaxed',
            isRejected && 'line-through text-gray-400'
          )}>
            <span className="font-bold text-gray-500 dark:text-gray-400">#{index}</span>{' '}
            {factor.description}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {factor.factor_type && (
            <Badge variant="outline" className="text-[9px] font-mono">
              {factor.factor_type}
            </Badge>
          )}
          {factor.weight !== undefined && (
            <span className="text-[10px] font-mono text-gray-500">{Math.round(factor.weight * 100)}%</span>
          )}
          <Badge className={cn('text-[9px] px-1.5 py-0 font-mono uppercase gap-1', statusColor)}>
            {statusIcon}
            {statusLabel}
          </Badge>
        </div>
      </div>

      {/* Weight bar */}
      {factor.weight !== undefined && (
        <div className="flex items-center gap-3 mt-2">
          <div className="flex-1 h-1.5 bg-gray-100 dark:bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all"
              style={{ width: `${Math.round(factor.weight * 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* Outcome details */}
      {factor.outcome && (
        <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-1.5">
          Resultado: {factor.outcome}
          {factor.confidence ? ` · Confianza: ${Math.round(factor.confidence * 100)}%` : ''}
          {factor.evidence_count ? ` · ${factor.evidence_count} evidencias` : ''}
        </p>
      )}

      {/* Expandable evidence */}
      {matches.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[10px] text-blue-600 dark:text-blue-400 hover:underline"
          >
            {expanded
              ? <IconChevronDown className="h-3 w-3" />
              : <IconChevronRight className="h-3 w-3" />
            }
            Ver {matches.length} evidencia{matches.length !== 1 ? 's' : ''}
          </button>
          {expanded && (
            <div className="mt-2 space-y-2 pl-2 border-l border-gray-200 dark:border-gray-700">
              {matches.map((match, mIdx) => (
                <EvidenceItem key={mIdx} match={match} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Single evidence item within a factor */
function EvidenceItem({ match }: { match: PredictiveMatchInfo }) {
  const sourceIcon = match.source === 'jurisprudence'
    ? <IconGavel className="h-3 w-3 text-purple-500" />
    : match.source === 'web'
      ? <IconWorld className="h-3 w-3 text-blue-500" />
      : match.source === 'uploaded'
        ? <IconPaperclip className="h-3 w-3 text-amber-500" />
        : <IconFile className="h-3 w-3 text-gray-400" />

  const sourceLabel = match.source === 'jurisprudence' ? 'Jurisprudencia'
    : match.source === 'web' ? 'Web'
      : match.source === 'uploaded' ? 'Cargado'
        : 'Interno'

  return (
    <div className="bg-white/60 dark:bg-muted/40 rounded p-2 text-[10px]">
      <div className="flex items-center gap-1.5 mb-1">
        {sourceIcon}
        <span className="font-medium text-gray-700 dark:text-gray-300 truncate">
          {match.document_title || match.document_id}
        </span>
        {match.roj && (
          <Badge variant="outline" className="text-[8px] px-1 py-0 font-mono">
            {match.roj}
          </Badge>
        )}
        {match.ecli && (
          <span className="text-gray-400 font-mono truncate">{match.ecli}</span>
        )}
        <span className="ml-auto text-gray-400 shrink-0">
          {sourceLabel} · {Math.round(match.similarity_score * 100)}%
        </span>
      </div>
      {match.text_excerpt && (
        <p className="text-gray-500 dark:text-gray-400 italic leading-relaxed line-clamp-3">
          &ldquo;{match.text_excerpt}&rdquo;
        </p>
      )}
      <div className="flex items-center gap-2 mt-1">
        <Badge
          variant="outline"
          className={cn(
            'text-[8px] px-1 py-0',
            match.supports_factor
              ? 'text-emerald-600 border-emerald-300'
              : 'text-red-600 border-red-300'
          )}
        >
          {match.supports_factor ? 'A favor' : 'En contra'}
        </Badge>
        {match.date && (
          <span className="text-gray-400">{match.date}</span>
        )}
        {match.url && (
          <a
            href={match.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-500 hover:underline ml-auto"
          >
            Ver fuente ↗
          </a>
        )}
      </div>
    </div>
  )
}

/** Source row for the global "Fuentes Consultadas" table */
function PredictiveSourceRow({ source }: { source: PredictiveSource }) {
  const sourceType = source.source || 'internal'
  const isJurisprudence = sourceType === 'jurisprudence'

  const icon = isJurisprudence
    ? <IconGavel className="h-3 w-3 text-purple-500 inline" />
    : sourceType === 'web'
      ? <IconWorld className="h-3 w-3 text-blue-500 inline" />
      : sourceType === 'uploaded'
        ? <IconPaperclip className="h-3 w-3 text-amber-500 inline" />
        : <IconFile className="h-3 w-3 text-gray-400 inline" />

  const label = isJurisprudence ? 'CENDOJ'
    : sourceType === 'web' ? 'Web'
      : sourceType === 'uploaded' ? 'Cargado'
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
        <div>
          {source.title || source.id}
          {isJurisprudence && (source.roj || source.ecli) && (
            <div className="text-[9px] text-gray-400 font-mono mt-0.5">
              {source.roj && <span>{source.roj}</span>}
              {source.roj && source.ecli && <span> · </span>}
              {source.ecli && <span>{source.ecli}</span>}
              {source.date && <span> · {source.date}</span>}
              {source.ponente && <span> · Ponente: {source.ponente}</span>}
            </div>
          )}
        </div>
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

'use client'

import { useState } from 'react'
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
} from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { VerifiedGenerationMetadata, VerifiedSource } from '@/lib/types/emma'
import { API_CONFIG } from '@/lib/config'

interface VerifiedDocumentResultProps {
  content: string
  verified: VerifiedGenerationMetadata
}

export function VerifiedDocumentResult({ content, verified }: VerifiedDocumentResultProps) {
  const [copied, setCopied] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const { claims, verified_count, rejected_count, total_claims, execution_time_ms, average_confidence } = verified
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
      const url = `${API_CONFIG.STREAMING_BASE_URL}${API_CONFIG.API_V1}${endpoint}`
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
            <h3 className="font-semibold text-sm">Documento Verificado</h3>
            <p className="text-xs text-muted-foreground">
              {total_claims} claims analizados
              {execution_time_ms ? ` · ${execution_time_ms < 1000 ? `${Math.round(execution_time_ms)}ms` : `${(execution_time_ms / 1000).toFixed(1)}s`}` : ''}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
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

      {/* Paper sheet with scroll */}
      <div className="bg-muted/50 dark:bg-muted/20 p-4 sm:p-6">
        <ScrollArea className="h-[600px]">
          <div className="bg-white dark:bg-card text-gray-900 dark:text-card-foreground shadow-md border rounded-md px-8 py-8 mx-auto w-[80%] min-h-[300px]">

            {/* ── Informe de Verificación ── */}
            <h2 className="text-base font-bold mb-3">Informe de Verificación</h2>
            <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5 mb-5">
              <p><span className="font-semibold text-gray-700 dark:text-gray-300">Tema:</span> {verified.topic}</p>
              <p><span className="font-semibold text-gray-700 dark:text-gray-300">Fecha:</span> {dateStr}</p>
              <p><span className="font-semibold text-gray-700 dark:text-gray-300">Sesión:</span> {verified.session_id.slice(0, 16)}…</p>
            </div>

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

            {/* ── Detalle de Claims ── */}
            <h3 className="text-sm font-bold mb-3 pb-2 border-b">
              Detalle de Claims ({claims.length})
            </h3>
            <div className="space-y-3 mb-6">
              {claims.map((claim, idx) => (
                <ClaimDetail key={claim.claim_id} claim={claim} index={idx + 1} />
              ))}
            </div>

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

            {/* ── Footer ── */}
            <div className="pt-3 border-t text-center">
              <p className="text-[10px] text-gray-400 dark:text-gray-500">
                Generado por NouxCubeIA
                {execution_time_ms ? ` — Tiempo de ejecución: ${Math.round(execution_time_ms)}ms` : ''}
              </p>
            </div>

          </div>
        </ScrollArea>
      </div>
    </div>
  )
}

/** Claim detail card matching PDF "Detalle de Claims" — all info always visible */
function ClaimDetail({ claim, index }: { claim: VerifiedGenerationMetadata['claims'][0]; index: number }) {
  const isVerified = claim.status === 'verified'
  const isCorrected = claim.status === 'corrected'
  const isRejected = claim.status === 'rejected'

  const borderColor = isVerified
    ? 'border-l-emerald-500'
    : isCorrected
      ? 'border-l-amber-500'
      : 'border-l-destructive'

  const bgColor = isVerified
    ? 'bg-emerald-50/50 dark:bg-emerald-500/5'
    : isCorrected
      ? 'bg-amber-50/50 dark:bg-amber-500/5'
      : 'bg-red-50/50 dark:bg-destructive/5'

  const statusLabel = isVerified ? 'VERIFICADO' : isCorrected ? 'CORREGIDO' : 'RECHAZADO'
  const statusColor = isVerified
    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400'
    : isCorrected
      ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400'
      : 'bg-red-100 text-red-700 dark:bg-destructive/20 dark:text-destructive'

  const statusIcon = isVerified
    ? <IconCircleCheck className="h-3 w-3" />
    : isCorrected
      ? <IconAlertTriangle className="h-3 w-3" />
      : <IconCircleX className="h-3 w-3" />

  return (
    <div className={cn('border-l-[3px] rounded-r-md p-3', borderColor, bgColor)}>
      <div className="flex items-start justify-between gap-2">
        <p className={cn(
          'text-xs leading-relaxed flex-1',
          isRejected && 'line-through text-gray-400'
        )}>
          <span className="font-bold text-gray-500 dark:text-gray-400">#{index}</span>{' '}
          {claim.claim_text}
        </p>
        <div className="flex items-center gap-1.5 shrink-0">
          {claim.confidence !== undefined && (
            <span className="text-[10px] font-mono text-gray-500">{Math.round(claim.confidence * 100)}%</span>
          )}
          <Badge className={cn('text-[9px] px-1.5 py-0 font-mono uppercase gap-1', statusColor)}>
            {statusIcon}
            {statusLabel}
          </Badge>
        </div>
      </div>

      {/* Original text for corrected claims — always visible */}
      {isCorrected && claim.original_text && (
        <p className="text-[10px] text-amber-600/70 dark:text-amber-400/70 mt-1.5 pl-3 border-l-2 border-amber-300 italic">
          Original: {claim.original_text}
        </p>
      )}
    </div>
  )
}

/** Source row as table row matching PDF "Fuentes Consultadas" */
function SourceRow({ source }: { source: VerifiedSource }) {
  const sourceType = source.source || 'internal'
  const icon = sourceType === 'web'
    ? <IconWorld className="h-3 w-3 text-blue-500 inline" />
    : sourceType === 'uploaded'
      ? <IconPaperclip className="h-3 w-3 text-amber-500 inline" />
      : <IconFile className="h-3 w-3 text-gray-400 inline" />
  const label = sourceType === 'web' ? 'Web' : sourceType === 'uploaded' ? 'Cargado' : 'Interno'

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

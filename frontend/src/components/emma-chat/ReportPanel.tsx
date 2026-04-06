'use client'

import { useState } from 'react'
import { IconChevronDown, IconChevronRight, IconFileText, IconDownload, IconLoader2 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { EmmaMarkdown } from './EmmaMarkdown'
import { generateReportDocument, getReportDownloadUrl } from '@/lib/services/emma.service'
import type { ReportMetadata } from '@/lib/types/emma'

interface ReportPanelProps {
  report: ReportMetadata
  content: string
}

function ConfidenceBadge({ value }: { value: number }) {
  const color = value >= 0.8
    ? 'bg-green-500/20 text-green-400 border-green-500/30'
    : value >= 0.5
      ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
      : 'bg-red-500/20 text-red-400 border-red-500/30'
  return (
    <span className={cn('text-[10px] px-1.5 py-0.5 rounded border font-mono', color)}>
      {Math.round(value * 100)}%
    </span>
  )
}

export function ReportPanel({ report, content }: ReportPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true)
  const [isGenerating, setIsGenerating] = useState(false)
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleGenerateDocument = async () => {
    setIsGenerating(true)
    setError(null)
    try {
      await generateReportDocument(report.report_id, 'new')
      // Download via fetch with auth token, then create blob URL
      const url = getReportDownloadUrl(report.report_id)
      const token = JSON.parse(sessionStorage.getItem('nexus_sso_tokens') || '{}').access_token || ''
      const resp = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` },
      })
      if (!resp.ok) throw new Error(`Download failed: ${resp.status}`)
      const blob = await resp.blob()
      const blobUrl = URL.createObjectURL(blob)
      setDownloadUrl(blobUrl)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al generar el documento')
    } finally {
      setIsGenerating(false)
    }
  }

  const { trust_summary } = report

  return (
    <div className="mt-3 rounded-xl border border-border/50 bg-card/60 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left hover:bg-muted/30 transition-colors"
      >
        {isExpanded ? (
          <IconChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <IconChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <IconFileText className="h-4 w-4 shrink-0 text-primary" />
        <span className="flex-1 text-sm font-medium truncate">
          Informe: {report.entity_label}
        </span>
        <ConfidenceBadge value={trust_summary.avg_confidence} />
      </button>

      {/* Body */}
      {isExpanded && (
        <div className="px-4 pb-4">
          {/* Report content */}
          <div className="prose-sm max-w-none">
            <EmmaMarkdown content={content} />
          </div>

          {/* Trust bar */}
          <div className="flex flex-wrap gap-3 text-xs text-muted-foreground border-t border-border/30 pt-3 mt-3">
            <span className="flex items-center gap-1.5">
              Confianza media
              <ConfidenceBadge value={trust_summary.avg_confidence} />
            </span>
            <span className="flex items-center gap-1.5">
              Mínima
              <ConfidenceBadge value={trust_summary.min_confidence} />
            </span>
            <span>
              <span className="font-medium text-foreground">{trust_summary.total_facts}</span> hechos
            </span>
            <span>
              <span className="font-medium text-foreground">{report.source_count}</span> fuentes
            </span>
          </div>

          {/* Footer */}
          <div className="mt-3 flex items-center gap-3">
            {!downloadUrl ? (
              <button
                onClick={handleGenerateDocument}
                disabled={isGenerating}
                className={cn(
                  'inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
                  'hover:bg-primary/90 transition-colors disabled:opacity-60 disabled:cursor-not-allowed',
                )}
              >
                {isGenerating ? (
                  <>
                    <IconLoader2 className="h-4 w-4 animate-spin" />
                    Generando…
                  </>
                ) : (
                  <>
                    <IconFileText className="h-4 w-4" />
                    Generar documento
                  </>
                )}
              </button>
            ) : (
              <a
                href={downloadUrl}
                download={`informe_${report.entity_label.toLowerCase().replace(/\s+/g, '_')}.docx`}
                className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <IconDownload className="h-4 w-4" />
                Descargar DOCX
              </a>
            )}
            {error && (
              <p className="text-xs text-red-400">{error}</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

'use client'

import { useState } from 'react'
import {
  IconFileText,
  IconCopy,
  IconCheck,
  IconAlertTriangle,
  IconScale,
  IconListDetails,
  IconZoomIn,
  IconZoomOut,
  IconZoomReset,
  IconPrinter,
  IconDownload,
} from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { DocGenMetadata } from '@/lib/types/emma'
import { DocumentViewer, docGenToViewerDocument } from '@/components/document-viewer'

interface DocGenResultProps {
  metadata: DocGenMetadata
}

const ZOOM_STEP = 0.1
const ZOOM_MIN = 0.5
const ZOOM_MAX = 2.0

export function DocGenResult({ metadata }: DocGenResultProps) {
  const [copied, setCopied] = useState(false)
  const [fitZoom, setFitZoom] = useState(0.65)
  const [zoom, setZoom] = useState<number | null>(null)
  const effectiveZoom = zoom ?? fitZoom
  const { document_text, document_type, pending_fields, sources_used, execution_time_ms } = metadata

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(document_text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // fallback
    }
  }

  const handleDownloadDocx = async () => {
    if (!metadata.generated_doc_id) return
    try {
      const { apiClient } = await import('@/lib/api-client')
      const result = await apiClient.downloadBlob(`/emma/generated/${metadata.generated_doc_id}/download`)
      if (result.error || !result.blob) throw new Error(result.error || 'Download failed')
      const blobUrl = URL.createObjectURL(result.blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = `${(document_type || 'documento').toLowerCase().replace(/\s+/g, '_')}.docx`
      a.click()
      URL.revokeObjectURL(blobUrl)
    } catch (err) {
      console.error('DOCX download failed:', err)
    }
  }

  // Count clauses (lines starting with number or "CLÁUSULA" pattern)
  const clauseCount = (document_text.match(/^(?:CLÁUSULA|Cláusula|CLAUSULA|Clausula|\d+[\.\)]\s)/gm) || []).length

  const now = new Date()
  const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`

  return (
    <div className={cn('bg-card border rounded-xl overflow-hidden')}>
      {/* Header bar */}
      <div className="flex items-center justify-between p-4 border-b bg-violet-500/5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-violet-500/10 flex items-center justify-center">
            <IconFileText className="h-5 w-5 text-violet-600" />
          </div>
          <div>
            <h3 className="font-semibold text-sm">Documento Generado</h3>
            <p className="text-xs text-muted-foreground">
              {document_type || 'Documento legal'}
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

          {/* Download DOCX */}
          {metadata.generated_doc_id && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadDocx}
              className="gap-1.5"
            >
              <IconDownload className="h-3.5 w-3.5" />
              DOCX
            </Button>
          )}

          {/* Copy */}
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopy}
            className="gap-1.5"
          >
            {copied ? <IconCheck className="h-3.5 w-3.5" /> : <IconCopy className="h-3.5 w-3.5" />}
            {copied ? 'Copiado' : 'Copiar'}
          </Button>
        </div>
      </div>

      {/* Stats grid */}
      <div className="p-4">
        <div className="flex justify-center gap-3">
          {clauseCount > 0 && (
            <Badge variant="outline" className="text-xs bg-violet-500/10 text-violet-600 border-violet-500/20">
              <IconListDetails className="h-3 w-3 mr-1" />
              {clauseCount} cláusulas
            </Badge>
          )}
          {pending_fields.length > 0 && (
            <Badge variant="outline" className="text-xs bg-amber-500/10 text-amber-600 border-amber-500/20">
              <IconAlertTriangle className="h-3 w-3 mr-1" />
              {pending_fields.length} campos pendientes
            </Badge>
          )}
          {sources_used.length > 0 && (
            <Badge variant="outline" className="text-xs bg-blue-500/10 text-blue-600 border-blue-500/20">
              <IconScale className="h-3 w-3 mr-1" />
              {sources_used.length} fuentes legales
            </Badge>
          )}
        </div>
      </div>

      {/* Document Viewer */}
      <DocumentViewer documents={[docGenToViewerDocument(metadata)]} zoom={effectiveZoom} onFitZoomCalculated={setFitZoom}>
        {/* Header */}
        <h2 className="text-base font-bold mb-3 capitalize">{document_type || 'Documento Generado'}</h2>
        <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5 mb-5">
          <p><span className="font-semibold text-gray-700 dark:text-gray-300">Tipo:</span> {document_type || 'Documento legal'}</p>
          <p><span className="font-semibold text-gray-700 dark:text-gray-300">Fecha:</span> {dateStr}</p>
        </div>

        {/* Document content */}
        <div className="prose prose-sm dark:prose-invert max-w-none mb-6">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{document_text}</ReactMarkdown>
        </div>

        {/* Pending fields */}
        {pending_fields.length > 0 && (
          <>
            <h3 className="text-sm font-bold mb-3 pb-2 border-b">
              Campos Pendientes ({pending_fields.length})
            </h3>
            <div className="flex flex-wrap gap-2 mb-6">
              {pending_fields.map((field, idx) => (
                <Badge
                  key={idx}
                  variant="outline"
                  className="text-xs bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-300 dark:border-amber-500/30 font-mono"
                >
                  {field}
                </Badge>
              ))}
            </div>
          </>
        )}

        {/* Legal sources */}
        {sources_used.length > 0 && (
          <>
            <h3 className="text-sm font-bold mb-3 pb-2 border-b">
              Fuentes Legales ({sources_used.length})
            </h3>
            <ul className="list-disc list-inside text-xs text-gray-600 dark:text-gray-400 space-y-1 mb-6">
              {sources_used.map((source, idx) => (
                <li key={idx}>{source}</li>
              ))}
            </ul>
          </>
        )}

        {/* Footer */}
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

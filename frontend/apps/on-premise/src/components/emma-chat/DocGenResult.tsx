'use client'

import { useState } from 'react'
import {
  IconFileText,
  IconCopy,
  IconCheck,
  IconAlertTriangle,
  IconScale,
  IconListDetails,
} from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { DocGenMetadata } from '@/lib/types/emma'
import { EmmaMarkdown } from './EmmaMarkdown'

interface DocGenResultProps {
  metadata: DocGenMetadata
}

export function DocGenResult({ metadata }: DocGenResultProps) {
  const [copied, setCopied] = useState(false)
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

      {/* Paper sheet */}
      <div className="bg-muted/50 dark:bg-muted/20 p-4 sm:p-6">
        <ScrollArea className="h-[600px]">
          <div className="bg-white dark:bg-card text-gray-900 dark:text-card-foreground shadow-md border rounded-md px-8 py-8 mx-auto w-[80%] min-h-[300px]">

            {/* Header */}
            <h2 className="text-base font-bold mb-3 capitalize">{document_type || 'Documento Generado'}</h2>
            <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5 mb-5">
              <p><span className="font-semibold text-gray-700 dark:text-gray-300">Tipo:</span> {document_type || 'Documento legal'}</p>
              <p><span className="font-semibold text-gray-700 dark:text-gray-300">Fecha:</span> {dateStr}</p>
            </div>

            {/* Document content */}
            <div className="prose prose-sm dark:prose-invert max-w-none mb-6">
              <EmmaMarkdown content={document_text} />
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

          </div>
        </ScrollArea>
      </div>
    </div>
  )
}

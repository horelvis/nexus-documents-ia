'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  IconFileText,
  IconDownload,
  IconFileTypePdf,
  IconFileTypeDocx,
  IconEdit,
  IconCircleCheck,
  IconChevronDown,
  IconChevronUp,
  IconSearch,
  IconExternalLink,
} from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { ForgeMetadata, ForgeField } from '@/lib/types/emma'
import { cacheForgeSession, downloadDocument } from '@/lib/services/forge.service'
import { formatFileSize } from '@/lib/document-utils'

interface ForgeResultProps {
  metadata: ForgeMetadata
}

const MAX_FIELDS_COLLAPSED = 8

export function ForgeResult({ metadata }: ForgeResultProps) {
  const router = useRouter()
  const [fieldsExpanded, setFieldsExpanded] = useState(false)
  const [downloadingFormat, setDownloadingFormat] = useState<string | null>(null)

  const confidencePct = Math.round((metadata.confidence || 0) * 100)
  const confidenceColor = confidencePct >= 80
    ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
    : confidencePct >= 60
      ? 'bg-amber-500/10 text-amber-600 border-amber-500/20'
      : 'bg-red-500/10 text-red-600 border-red-500/20'

  const handleEditFields = () => {
    cacheForgeSession(metadata.session_id, metadata)
    router.push(`/forge/${metadata.session_id}`)
  }

  const handleDownload = async (format: 'docx' | 'pdf') => {
    setDownloadingFormat(format)
    try {
      await downloadDocument(metadata.session_id, format)
    } finally {
      setDownloadingFormat(null)
    }
  }

  // ── Analyze mode: detected fields list ──
  if (metadata.action === 'analyze') {
    const fields = metadata.fields || []
    const visibleFields = fieldsExpanded ? fields : fields.slice(0, MAX_FIELDS_COLLAPSED)
    const hasMore = fields.length > MAX_FIELDS_COLLAPSED

    return (
      <Card className="bg-card border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b bg-blue-500/5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-blue-500/10 flex items-center justify-center">
              <IconSearch className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <h3 className="font-semibold text-sm">Documento Analizado</h3>
              <p className="text-xs text-muted-foreground">
                {metadata.source_title || metadata.document_type}
                {' · '}{fields.length} campos detectados
              </p>
            </div>
          </div>
          <Badge variant="outline" className={cn('text-xs font-mono', confidenceColor)}>
            {confidencePct}% confianza
          </Badge>
        </div>

        <div className="p-4 space-y-3">
          {/* Document type */}
          <div className="flex items-center gap-2">
            <IconFileText className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">{metadata.document_type}</span>
          </div>

          {/* Fields list */}
          {fields.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Campos detectados
              </p>
              <div className="flex flex-wrap gap-1.5">
                {visibleFields.map((field: ForgeField) => (
                  <Badge
                    key={field.field_name}
                    variant="outline"
                    className={cn(
                      'text-xs font-mono',
                      field.current_value
                        ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
                        : field.required
                          ? 'bg-amber-500/10 text-amber-600 border-amber-500/20'
                          : 'bg-muted/50 text-muted-foreground'
                    )}
                  >
                    {field.label}
                    {field.current_value && (
                      <IconCircleCheck className="h-2.5 w-2.5 ml-1" />
                    )}
                  </Badge>
                ))}
              </div>
              {hasMore && (
                <button
                  onClick={() => setFieldsExpanded(!fieldsExpanded)}
                  className="flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  {fieldsExpanded ? (
                    <>
                      <IconChevronUp className="h-3 w-3" />
                      Mostrar menos
                    </>
                  ) : (
                    <>
                      <IconChevronDown className="h-3 w-3" />
                      +{fields.length - MAX_FIELDS_COLLAPSED} campos más
                    </>
                  )}
                </button>
              )}
            </div>
          )}

          {/* Edit fields button */}
          <Button
            variant="default"
            size="sm"
            onClick={handleEditFields}
            className="gap-1.5 w-full"
          >
            <IconEdit className="h-3.5 w-3.5" />
            Editar campos
          </Button>
        </div>
      </Card>
    )
  }

  // ── Render mode: download buttons ──
  if (metadata.action === 'render') {
    const outputs = metadata.outputs || {}

    return (
      <Card className="bg-card border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b bg-violet-500/5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-violet-500/10 flex items-center justify-center">
              <IconFileText className="h-5 w-5 text-violet-600" />
            </div>
            <div>
              <h3 className="font-semibold text-sm">Documento Generado</h3>
              <p className="text-xs text-muted-foreground">
                {metadata.document_title || metadata.source_title || metadata.document_type}
              </p>
            </div>
          </div>
          <button
            onClick={handleEditFields}
            className="text-xs text-violet-600 hover:text-violet-700 hover:underline flex items-center gap-0.5"
          >
            Ver detalle
            <IconExternalLink className="h-3 w-3" />
          </button>
        </div>

        <div className="p-4">
          <div className="flex flex-wrap gap-2">
            {/* DOCX download */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleDownload('docx')}
              disabled={downloadingFormat === 'docx'}
              className="gap-1.5"
            >
              <IconFileTypeDocx className="h-4 w-4 text-blue-500" />
              {downloadingFormat === 'docx' ? 'Descargando...' : 'DOCX'}
              {outputs.docx && (
                <span className="text-[10px] text-muted-foreground ml-1">
                  ({formatFileSize(outputs.docx.size_bytes)})
                </span>
              )}
            </Button>

            {/* PDF download */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleDownload('pdf')}
              disabled={downloadingFormat === 'pdf'}
              className="gap-1.5"
            >
              <IconFileTypePdf className="h-4 w-4 text-red-500" />
              {downloadingFormat === 'pdf' ? 'Descargando...' : 'PDF'}
              {outputs.pdf && (
                <span className="text-[10px] text-muted-foreground ml-1">
                  ({formatFileSize(outputs.pdf.size_bytes)})
                </span>
              )}
            </Button>
          </div>
        </div>
      </Card>
    )
  }

  // ── Persist mode: success card ──
  if (metadata.action === 'persist') {
    const gcsPaths = metadata.gcs_paths || {}
    const pathCount = Object.keys(gcsPaths).length

    return (
      <Card className="bg-card border rounded-xl overflow-hidden border-emerald-500/30">
        <div className="flex items-center justify-between p-4 border-b bg-emerald-500/5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center">
              <IconCircleCheck className="h-5 w-5 text-emerald-600" />
            </div>
            <div>
              <h3 className="font-semibold text-sm text-emerald-700 dark:text-emerald-400">
                Documento Persistido
              </h3>
              <p className="text-xs text-muted-foreground">
                {metadata.document_title || metadata.source_title || metadata.document_type}
              </p>
            </div>
          </div>
          {metadata.weaviate_indexed && (
            <Badge variant="outline" className="text-xs bg-emerald-500/10 text-emerald-600 border-emerald-500/20">
              Indexado en búsqueda
            </Badge>
          )}
        </div>

        <div className="p-4 space-y-3">
          {/* GCS paths */}
          {pathCount > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Almacenamiento
              </p>
              {Object.entries(gcsPaths).map(([format, path]) => (
                <div key={format} className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0 uppercase">
                    {format}
                  </Badge>
                  <span className="truncate">{path}</span>
                </div>
              ))}
            </div>
          )}

          {/* Document ID */}
          {metadata.document_id && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="font-semibold">ID:</span>
              <span className="font-mono">{metadata.document_id}</span>
            </div>
          )}
        </div>
      </Card>
    )
  }

  // Fallback — unknown action
  return null
}

'use client'

import { useState } from 'react'
import {
  IconFileText,
  IconCircleCheck,
  IconQuestionMark,
  IconChevronDown,
  IconChevronUp,
  IconEdit,
  IconFileTypePdf,
} from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { ForgeMetadata, ForgeField } from '@/lib/types/emma'

const MAX_FIELDS_COLLAPSED = 8

interface ForgeTabProps {
  metadata: ForgeMetadata | null
  onEditFields?: () => void
  onGenerate?: () => void
}

/**
 * Document Forge tab content for the ArtifactsPanel.
 *
 * Renders template analysis results: template name, overall confidence,
 * field detection list with fill status, and action buttons.
 * Extracted from ForgeResult analyze mode (content only, no card wrapper).
 */
export function ForgeTab({ metadata, onEditFields, onGenerate }: ForgeTabProps) {
  const [fieldsExpanded, setFieldsExpanded] = useState(false)

  if (!metadata) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <IconFileText className="h-8 w-8 mb-2 opacity-30" />
        <p className="text-sm">Sin documentos Forge activos</p>
      </div>
    )
  }

  const fields = metadata.fields || []
  const filledCount = fields.filter(f => f.current_value).length
  const totalCount = fields.length
  const progressPercent = totalCount > 0 ? Math.round((filledCount / totalCount) * 100) : 0
  const visibleFields = fieldsExpanded ? fields : fields.slice(0, MAX_FIELDS_COLLAPSED)
  const hasMore = fields.length > MAX_FIELDS_COLLAPSED

  const confidencePct = Math.round((metadata.confidence || 0) * 100)
  const confidenceColor = confidencePct >= 80
    ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
    : confidencePct >= 60
      ? 'bg-amber-500/10 text-amber-600 border-amber-500/20'
      : 'bg-red-500/10 text-red-600 border-red-500/20'

  return (
    <div className="space-y-4">
      {/* Header info */}
      <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 dark:bg-violet-500/5 overflow-hidden">
        <div className="px-3 pt-3 pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <IconFileText className="h-4 w-4 text-violet-600 shrink-0" />
              <p className="text-xs font-medium truncate">
                {metadata.source_title || metadata.document_type}
              </p>
            </div>
            <Badge variant="outline" className={cn('text-[10px] shrink-0 ml-2 font-mono', confidenceColor)}>
              {confidencePct}%
            </Badge>
          </div>

          {/* Progress bar: fields_filled / fields_detected */}
          <div className="mt-2">
            <div className="flex items-center justify-between text-[10px] text-muted-foreground mb-1">
              <span>{filledCount} de {totalCount} campos completados</span>
              <span className="font-mono">{progressPercent}%</span>
            </div>
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-violet-500 rounded-full transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        </div>

        {/* Document type */}
        {metadata.document_type && (
          <div className="px-3 pb-2">
            <Badge variant="outline" className="text-[10px] bg-violet-500/10 text-violet-600 border-violet-500/20">
              {metadata.document_type}
            </Badge>
          </div>
        )}

        {/* Fields list */}
        {fields.length > 0 && (
          <div className="px-3 pb-2 space-y-1.5">
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
              Campos detectados
            </p>
            <div className="space-y-1">
              {visibleFields.map((field: ForgeField) => (
                <FieldItem key={field.field_name} field={field} />
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
                    +{fields.length - MAX_FIELDS_COLLAPSED} campos mas
                  </>
                )}
              </button>
            )}
          </div>
        )}

        {/* Action buttons */}
        <div className="px-3 pb-3 flex gap-2">
          {onEditFields && (
            <Button
              variant="default"
              size="sm"
              onClick={onEditFields}
              className="gap-1.5 flex-1"
            >
              <IconEdit className="h-3.5 w-3.5" />
              Editar campos
            </Button>
          )}
          {onGenerate && (
            <Button
              variant="outline"
              size="sm"
              onClick={onGenerate}
              className="gap-1.5 flex-1"
            >
              <IconFileTypePdf className="h-3.5 w-3.5" />
              Generar PDF
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Field item
// ---------------------------------------------------------------------------

function FieldItem({ field }: { field: ForgeField }) {
  const isFilled = !!field.current_value

  return (
    <div className="flex items-center gap-2 p-2 bg-background/60 dark:bg-background/40 rounded-lg">
      <div className="shrink-0">
        {isFilled ? (
          <IconCircleCheck className="h-3.5 w-3.5 text-emerald-500" />
        ) : (
          <IconQuestionMark className={cn(
            'h-3.5 w-3.5',
            field.required ? 'text-amber-500' : 'text-muted-foreground/50'
          )} />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium truncate">{field.label}</span>
          {field.required && !isFilled && (
            <span className="text-[9px] text-amber-500">*</span>
          )}
        </div>
        {isFilled && (
          <p className="text-[10px] text-muted-foreground truncate mt-0.5">
            {field.current_value}
          </p>
        )}
      </div>

      <Badge
        variant="outline"
        className={cn(
          'text-[9px] shrink-0',
          isFilled
            ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
            : field.required
              ? 'bg-amber-500/10 text-amber-600 border-amber-500/20'
              : 'bg-muted/50 text-muted-foreground'
        )}
      >
        {field.field_type}
      </Badge>
    </div>
  )
}

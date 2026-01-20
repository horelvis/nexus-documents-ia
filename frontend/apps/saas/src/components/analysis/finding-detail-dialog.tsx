'use client'

import React from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  AlertTriangle,
  Lightbulb,
  Quote,
  FileText,
  ExternalLink,
  BookOpen
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { parseLegalReferences, getUniqueLegalReferences } from '@/lib/utils/legal-references'

// Type for risk/recommendation from analysis
export interface AnalysisFinding {
  id: string
  type: 'risk' | 'recommendation'
  severity?: 'high' | 'medium' | 'low' | null
  title: string
  description: string
  quote?: string
  clause?: string
  priority?: 'high' | 'medium' | 'low'
  recommendation?: string
  action_required?: string
  // Page info if annotation exists
  pageNumber?: number
}

interface FindingDetailDialogProps {
  finding: AnalysisFinding | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

function getSeverityConfig(severity?: string | null) {
  switch (severity) {
    case 'high':
      return {
        label: 'Alto',
        bgClass: 'bg-red-100 dark:bg-red-900/30',
        textClass: 'text-red-700 dark:text-red-400',
        borderClass: 'border-red-200 dark:border-red-800'
      }
    case 'medium':
      return {
        label: 'Medio',
        bgClass: 'bg-amber-100 dark:bg-amber-900/30',
        textClass: 'text-amber-700 dark:text-amber-400',
        borderClass: 'border-amber-200 dark:border-amber-800'
      }
    case 'low':
      return {
        label: 'Bajo',
        bgClass: 'bg-yellow-100 dark:bg-yellow-900/30',
        textClass: 'text-yellow-700 dark:text-yellow-400',
        borderClass: 'border-yellow-200 dark:border-yellow-800'
      }
    default:
      return {
        label: 'Medio',
        bgClass: 'bg-amber-100 dark:bg-amber-900/30',
        textClass: 'text-amber-700 dark:text-amber-400',
        borderClass: 'border-amber-200 dark:border-amber-800'
      }
  }
}

function getPriorityConfig(priority?: string | null) {
  switch (priority) {
    case 'high':
      return { label: 'Alta', className: 'border-blue-500 text-blue-600' }
    case 'medium':
      return { label: 'Media', className: 'border-blue-400 text-blue-500' }
    case 'low':
      return { label: 'Baja', className: 'border-blue-300 text-blue-400' }
    default:
      return { label: 'Media', className: 'border-blue-400 text-blue-500' }
  }
}

export function FindingDetailDialog({
  finding,
  open,
  onOpenChange
}: FindingDetailDialogProps) {
  if (!finding) return null

  const isRisk = finding.type === 'risk'
  const severityConfig = isRisk ? getSeverityConfig(finding.severity) : null
  const priorityConfig = !isRisk ? getPriorityConfig(finding.priority) : null

  // Extract legal references from description and quote
  const allText = [finding.description, finding.quote, finding.clause]
    .filter(Boolean)
    .join(' ')
  const legalReferences = getUniqueLegalReferences(allText)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-start gap-3">
            {/* Icon */}
            <div className={cn(
              "w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0",
              isRisk
                ? severityConfig?.bgClass
                : "bg-blue-100 dark:bg-blue-900/30"
            )}>
              {isRisk ? (
                <AlertTriangle className={cn("h-5 w-5", severityConfig?.textClass)} />
              ) : (
                <Lightbulb className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              )}
            </div>

            {/* Title and badge */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                {isRisk ? (
                  <Badge
                    variant="outline"
                    className={cn("text-xs", severityConfig?.borderClass, severityConfig?.textClass)}
                  >
                    <AlertTriangle className="h-3 w-3 mr-1" />
                    Riesgo {severityConfig?.label}
                  </Badge>
                ) : (
                  <Badge
                    variant="outline"
                    className={cn("text-xs", priorityConfig?.className)}
                  >
                    <Lightbulb className="h-3 w-3 mr-1" />
                    Recomendación {priorityConfig?.label && `(Prioridad ${priorityConfig.label})`}
                  </Badge>
                )}
              </div>
              <DialogTitle className="text-lg font-semibold leading-tight">
                {finding.title}
              </DialogTitle>
            </div>
          </div>
        </DialogHeader>

        <ScrollArea className="flex-1 -mx-6 px-6">
          <div className="space-y-4 pb-4">
            {/* Description - Full text with legal references parsed */}
            <div>
              <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                <FileText className="h-4 w-4" />
                Descripción
              </h4>
              <div className="text-sm leading-relaxed text-foreground">
                {parseLegalReferences(finding.description)}
              </div>
            </div>

            {/* Quote from document */}
            {finding.quote && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                  <Quote className="h-4 w-4" />
                  Cita del documento
                </h4>
                <blockquote className={cn(
                  "p-3 rounded-lg border-l-4 text-sm italic",
                  isRisk
                    ? "bg-amber-50 dark:bg-amber-950/20 border-amber-400 text-amber-900 dark:text-amber-100"
                    : "bg-blue-50 dark:bg-blue-950/20 border-blue-400 text-blue-900 dark:text-blue-100"
                )}>
                  "{finding.quote}"
                </blockquote>
              </div>
            )}

            {/* Clause reference */}
            {finding.clause && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">
                  Cláusula referenciada
                </h4>
                <p className="text-sm">
                  {parseLegalReferences(finding.clause)}
                </p>
              </div>
            )}

            {/* Recommendation for risk / Action required */}
            {isRisk && finding.recommendation && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                  <Lightbulb className="h-4 w-4" />
                  Recomendación
                </h4>
                <p className="text-sm">
                  {parseLegalReferences(finding.recommendation)}
                </p>
              </div>
            )}

            {!isRisk && finding.action_required && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">
                  Acción requerida
                </h4>
                <p className="text-sm font-medium text-primary">
                  {finding.action_required}
                </p>
              </div>
            )}

            {/* Legal references list */}
            {legalReferences.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                  <BookOpen className="h-4 w-4" />
                  Referencias legales
                </h4>
                <ul className="space-y-1">
                  {legalReferences.map((ref, idx) => (
                    <li key={idx}>
                      <a
                        href={ref.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                      >
                        {ref.text}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </ScrollArea>

        {/* Footer with close button */}
        <div className="flex justify-end pt-4 border-t">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Cerrar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

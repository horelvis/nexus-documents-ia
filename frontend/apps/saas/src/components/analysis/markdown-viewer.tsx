'use client'

import React, { useMemo, useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  FileText,
  AlertTriangle,
  Lightbulb
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { MarkdownPage, PDFAnnotation } from '@/lib/services/emma.service'

interface MarkdownViewerProps {
  markdown: string
  pages: MarkdownPage[]
  annotations?: PDFAnnotation[]
  currentPage?: number
  onPageChange?: (page: number) => void
  onAnnotationClick?: (annotationId: string) => void
  highlightedAnnotationId?: string | null
  className?: string
}

export function MarkdownViewer({
  markdown,
  pages,
  annotations = [],
  currentPage = 1,
  onPageChange,
  onAnnotationClick,
  highlightedAnnotationId,
  className
}: MarkdownViewerProps) {
  const [fontSize, setFontSize] = useState(16)
  const totalPages = pages.length

  // Get current page content
  const currentPageContent = useMemo(() => {
    const page = pages.find(p => p.page_number === currentPage)
    return page?.content || ''
  }, [pages, currentPage])

  // Get annotations for current page
  const currentPageAnnotations = useMemo(() => {
    return annotations.filter(a => a.page_number === currentPage)
  }, [annotations, currentPage])

  // Navigate pages
  const goToPage = useCallback((page: number) => {
    if (page >= 1 && page <= totalPages) {
      onPageChange?.(page)
    }
  }, [totalPages, onPageChange])

  // Custom components for markdown rendering
  const components = useMemo(() => ({
    // Style marks (annotations) with click handlers
    mark: ({ node, ...props }: any) => {
      const dataType = props['data-type']
      const dataSeverity = props['data-severity']
      const dataId = props['data-id']

      const isRisk = dataType === 'risk'
      const isHighlighted = highlightedAnnotationId === dataId

      return (
        <mark
          {...props}
          onClick={() => dataId && onAnnotationClick?.(dataId)}
          className={cn(
            "px-1 rounded cursor-pointer transition-all",
            isRisk && dataSeverity === 'high' && "bg-red-200 dark:bg-red-900/50 hover:bg-red-300",
            isRisk && dataSeverity === 'medium' && "bg-orange-200 dark:bg-orange-900/50 hover:bg-orange-300",
            isRisk && dataSeverity === 'low' && "bg-yellow-200 dark:bg-yellow-900/50 hover:bg-yellow-300",
            !isRisk && "bg-blue-200 dark:bg-blue-900/50 hover:bg-blue-300",
            isHighlighted && "ring-2 ring-primary animate-pulse"
          )}
        />
      )
    },
    // Style tables
    table: ({ node, ...props }: any) => (
      <div className="overflow-x-auto my-4">
        <table {...props} className="min-w-full border-collapse border border-border" />
      </div>
    ),
    th: ({ node, ...props }: any) => (
      <th {...props} className="border border-border bg-muted px-4 py-2 text-left font-medium" />
    ),
    td: ({ node, ...props }: any) => (
      <td {...props} className="border border-border px-4 py-2" />
    ),
    // Style headings
    h1: ({ node, ...props }: any) => (
      <h1 {...props} className="text-2xl font-bold mt-6 mb-4 text-foreground" />
    ),
    h2: ({ node, ...props }: any) => (
      <h2 {...props} className="text-xl font-semibold mt-5 mb-3 text-foreground" />
    ),
    h3: ({ node, ...props }: any) => (
      <h3 {...props} className="text-lg font-semibold mt-4 mb-2 text-foreground" />
    ),
    // Style paragraphs
    p: ({ node, ...props }: any) => (
      <p {...props} className="my-2 leading-relaxed" />
    ),
    // Style lists
    ul: ({ node, ...props }: any) => (
      <ul {...props} className="list-disc list-inside my-2 ml-4" />
    ),
    ol: ({ node, ...props }: any) => (
      <ol {...props} className="list-decimal list-inside my-2 ml-4" />
    ),
    li: ({ node, ...props }: any) => (
      <li {...props} className="my-1" />
    ),
    // Style blockquotes
    blockquote: ({ node, ...props }: any) => (
      <blockquote {...props} className="border-l-4 border-primary/30 pl-4 my-4 italic text-muted-foreground" />
    ),
    // Style code
    code: ({ node, inline, ...props }: any) => (
      inline ? (
        <code {...props} className="bg-muted px-1 py-0.5 rounded text-sm font-mono" />
      ) : (
        <code {...props} className="block bg-muted p-4 rounded-lg text-sm font-mono overflow-x-auto" />
      )
    ),
  }), [highlightedAnnotationId, onAnnotationClick])

  return (
    <div className={cn("flex flex-col h-full bg-background", className)}>
      {/* Toolbar */}
      <div className="h-12 border-b bg-card flex items-center justify-between px-4 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm">
            Página {currentPage} de {totalPages}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => goToPage(currentPage + 1)}
            disabled={currentPage >= totalPages}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setFontSize(s => Math.max(12, s - 2))}
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <Badge variant="secondary" className="cursor-pointer" onClick={() => setFontSize(16)}>
            {fontSize}px
          </Badge>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setFontSize(s => Math.min(24, s + 2))}
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Content Area */}
      <ScrollArea className="flex-1">
        <div className="max-w-4xl mx-auto p-8">
          {/* Page header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2 text-muted-foreground">
              <FileText className="h-4 w-4" />
              <span className="text-sm">Página {currentPage}</span>
            </div>
            {currentPageAnnotations.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  {currentPageAnnotations.length} anotaciones
                </span>
              </div>
            )}
          </div>

          {/* Annotations summary for current page */}
          {currentPageAnnotations.length > 0 && (
            <Card className="mb-6 p-4 bg-muted/30 border-dashed">
              <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                Hallazgos en esta página
              </h4>
              <div className="flex flex-wrap gap-2">
                {currentPageAnnotations.map((ann) => (
                  <Badge
                    key={ann.id}
                    variant="outline"
                    className={cn(
                      "cursor-pointer transition-all",
                      ann.type === 'risk' && ann.severity === 'high' && "border-red-500 text-red-600 hover:bg-red-50",
                      ann.type === 'risk' && ann.severity === 'medium' && "border-orange-500 text-orange-600 hover:bg-orange-50",
                      ann.type === 'risk' && ann.severity === 'low' && "border-yellow-500 text-yellow-600 hover:bg-yellow-50",
                      ann.type !== 'risk' && "border-blue-500 text-blue-600 hover:bg-blue-50",
                      highlightedAnnotationId === ann.id && "ring-2 ring-primary"
                    )}
                    onClick={() => onAnnotationClick?.(ann.id)}
                  >
                    {ann.type === 'risk' ? (
                      <AlertTriangle className="h-3 w-3 mr-1" />
                    ) : (
                      <Lightbulb className="h-3 w-3 mr-1" />
                    )}
                    {ann.title.slice(0, 30)}{ann.title.length > 30 ? '...' : ''}
                  </Badge>
                ))}
              </div>
            </Card>
          )}

          {/* Markdown content */}
          <article
            className="prose prose-slate dark:prose-invert max-w-none"
            style={{ fontSize: `${fontSize}px` }}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw]}
              components={components}
            >
              {currentPageContent}
            </ReactMarkdown>
          </article>

          {/* Page footer */}
          <div className="mt-8 pt-4 border-t text-center text-sm text-muted-foreground">
            — Página {currentPage} de {totalPages} —
          </div>
        </div>
      </ScrollArea>
    </div>
  )
}

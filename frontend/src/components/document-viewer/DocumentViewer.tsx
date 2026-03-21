'use client'

import { useState, useRef, useEffect, type ReactNode } from 'react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { DocumentPage } from './DocumentPage'
import { DocumentSidebar } from './DocumentSidebar'
import type { ViewerDocument } from './types'

/** A4 page width in px at 96dpi: 21cm × 37.795275591 px/cm */
const A4_WIDTH_PX = 21 * 37.795275591 // ≈ 793.7px

interface DocumentViewerProps {
  documents: ViewerDocument[]
  /** JSX children rendered inside DocumentPage (for verified/predictive results) */
  children?: ReactNode
  /** Zoom level controlled by parent. If undefined, auto-fit to container width is used. */
  zoom?: number
  /** Called once on mount with the calculated fit-to-width zoom value */
  onFitZoomCalculated?: (fitZoom: number) => void
  /** Additional className for the container */
  className?: string
}

/**
 * Unified document viewer with A4 page rendering and optional sidebar.
 * Calculates a fit-to-width zoom on mount so the page fills the container.
 * Zoom and actions are managed by the parent component's header bar.
 */
export function DocumentViewer({ documents, children, zoom, onFitZoomCalculated, className }: DocumentViewerProps) {
  const [activeIndex, setActiveIndex] = useState(0)
  const pageRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [fitZoom, setFitZoom] = useState(0.65) // sensible default until measured
  const fitZoomCallbackRef = useRef(onFitZoomCalculated)
  fitZoomCallbackRef.current = onFitZoomCalculated

  // Calculate fit-to-width zoom on mount
  useEffect(() => {
    if (!containerRef.current) return
    const containerWidth = containerRef.current.clientWidth
    const padding = 48 // p-6 = 24px each side
    const available = containerWidth - padding
    const calculated = Math.round((available / A4_WIDTH_PX) * 100) / 100
    const clamped = Math.min(Math.max(calculated, 0.3), 1)
    setFitZoom(clamped)
    fitZoomCallbackRef.current?.(clamped)
  }, [])

  const effectiveZoom = zoom ?? fitZoom

  const activeDoc = documents[activeIndex]
  const showSidebar = documents.length > 1

  if (!activeDoc) return null

  return (
    <div className={className}>
      {/* Content area */}
      <div className="flex bg-muted/50 dark:bg-muted/20">
        {/* Sidebar (only shown for multiple documents) */}
        {showSidebar && (
          <DocumentSidebar
            documents={documents}
            activeIndex={activeIndex}
            onSelect={setActiveIndex}
          />
        )}

        {/* Page area */}
        <div ref={containerRef} className="flex-1 overflow-hidden">
          <ScrollArea className="h-[600px]">
            <div className="p-6 flex justify-center">
              <DocumentPage
                ref={pageRef}
                content={children ? undefined : activeDoc.content}
                zoom={effectiveZoom}
              >
                {children}
              </DocumentPage>
            </div>
          </ScrollArea>
        </div>
      </div>
    </div>
  )
}

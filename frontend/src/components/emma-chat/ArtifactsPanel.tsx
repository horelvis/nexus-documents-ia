'use client'

import { useState, useRef, useEffect } from 'react'
import { X, GripVertical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface ArtifactTab {
  id: string
  label: string
  icon: React.ReactNode
  badge?: string | number
  content: React.ReactNode
}

interface ArtifactsPanelProps {
  tabs: ArtifactTab[]
  activeTabId: string | null
  onTabChange: (tabId: string) => void
  open: boolean
  onOpenChange: (open: boolean) => void
}

const DEFAULT_WIDTH = 400
const MIN_WIDTH = 300
const MAX_WIDTH_VW = 0.6

/**
 * ArtifactsPanel — side panel container for artifact tabs.
 *
 * Two states:
 *  - open=true:  Full panel docked to the right of the chat area.
 *                Drag the left-edge grip to resize (min 300px, max 60vw).
 *  - open=false: Collapses to a floating pill (bottom-right) showing total
 *                artifact count. Click pill to reopen.
 *
 * When tabs.length === 0 and open=false, nothing is rendered.
 */
export function ArtifactsPanel({
  tabs,
  activeTabId,
  onTabChange,
  open,
  onOpenChange,
}: ArtifactsPanelProps) {
  const [width, setWidth] = useState(DEFAULT_WIDTH)
  const isDragging = useRef(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(DEFAULT_WIDTH)
  const panelRef = useRef<HTMLDivElement>(null)

  // Total badge count for the collapsed pill
  const totalBadgeCount = tabs.reduce((sum, tab) => {
    const n = typeof tab.badge === 'number' ? tab.badge : parseInt(tab.badge ?? '0', 10)
    return sum + (isNaN(n) ? 0 : n)
  }, 0)

  // Active tab object
  const activeTab = tabs.find((t) => t.id === activeTabId) ?? tabs[0] ?? null

  // --- Resize handle ---
  function handleResizeMouseDown(e: React.MouseEvent) {
    e.preventDefault()
    isDragging.current = true
    dragStartX.current = e.clientX
    dragStartWidth.current = width

    function onMouseMove(ev: MouseEvent) {
      if (!isDragging.current) return
      const delta = dragStartX.current - ev.clientX
      const maxWidth = window.innerWidth * MAX_WIDTH_VW
      const newWidth = Math.min(maxWidth, Math.max(MIN_WIDTH, dragStartWidth.current + delta))
      setWidth(newWidth)
    }

    function onMouseUp() {
      isDragging.current = false
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }

  // Clean up drag listeners if component unmounts mid-drag
  useEffect(() => {
    return () => {
      isDragging.current = false
    }
  }, [])

  // --- Collapsed pill ---
  if (!open) {
    if (tabs.length === 0) return null

    const activeBadge = activeTab?.badge
    const pillLabel =
      totalBadgeCount > 0 ? `${totalBadgeCount} artifacts` : `${tabs.length} artifact${tabs.length !== 1 ? 's' : ''}`

    return (
      <button
        onClick={() => onOpenChange(true)}
        className={cn(
          'fixed bottom-6 right-6 z-40',
          'flex items-center gap-2 px-4 py-2 rounded-full',
          'bg-indigo-600 text-white shadow-lg',
          'hover:bg-indigo-500 transition-colors duration-150',
          'text-sm font-medium select-none',
        )}
        aria-label="Open artifacts panel"
      >
        <span>{pillLabel}</span>
        {activeBadge !== undefined && activeBadge !== '' && (
          <span className="bg-white/20 text-white text-xs rounded-full px-1.5 py-0.5 leading-none">
            {activeBadge}
          </span>
        )}
      </button>
    )
  }

  // --- Open panel ---
  return (
    <div
      ref={panelRef}
      style={{ width }}
      className={cn(
        'relative flex flex-col',
        'bg-background border-l border-border',
        'shrink-0 sticky top-0 h-screen max-h-screen overflow-hidden',
      )}
    >
      {/* Resize handle — left edge */}
      <div
        onMouseDown={handleResizeMouseDown}
        className={cn(
          'absolute left-0 top-0 bottom-0 w-1 z-10',
          'cursor-col-resize hover:bg-indigo-400 transition-colors duration-150',
          'group flex items-center justify-center',
        )}
        aria-label="Resize panel"
        role="separator"
        aria-orientation="vertical"
      >
        <GripVertical className="h-4 w-4 text-border group-hover:text-indigo-400 pointer-events-none" />
      </div>

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <span className="text-sm font-semibold text-foreground">Artifacts</span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-foreground"
          onClick={() => onOpenChange(false)}
          aria-label="Close artifacts panel"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Tab bar */}
      {tabs.length > 0 && (
        <div className="flex items-center gap-0.5 px-2 py-1.5 border-b border-border shrink-0 overflow-x-auto scrollbar-thin">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap',
                'transition-colors duration-150 shrink-0',
                activeTabId === tab.id
                  ? 'bg-indigo-600 text-white'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )}
              aria-selected={activeTabId === tab.id}
              role="tab"
            >
              <span className="flex items-center">{tab.icon}</span>
              <span>{tab.label}</span>
              {tab.badge !== undefined && tab.badge !== '' && (
                <span
                  className={cn(
                    'rounded-full px-1.5 py-0.5 text-[10px] leading-none font-semibold',
                    activeTabId === tab.id
                      ? 'bg-white/20 text-white'
                      : 'bg-muted-foreground/20 text-muted-foreground',
                  )}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Content area */}
      <div className="flex-1 overflow-y-auto">
        {activeTab ? (
          activeTab.content
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            No artifacts yet
          </div>
        )}
      </div>
    </div>
  )
}

export default ArtifactsPanel

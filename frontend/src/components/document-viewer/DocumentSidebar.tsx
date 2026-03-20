'use client'

import { FileText } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import type { ViewerDocument } from './types'

interface DocumentSidebarProps {
  documents: ViewerDocument[]
  activeIndex: number
  onSelect: (index: number) => void
}

export function DocumentSidebar({ documents, activeIndex, onSelect }: DocumentSidebarProps) {
  return (
    <div className="w-56 border-r bg-muted/20 flex flex-col">
      <div className="px-3 py-2 border-b">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Documentos ({documents.length})
        </h4>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {documents.map((doc, idx) => (
            <button
              key={doc.id}
              onClick={() => onSelect(idx)}
              className={cn(
                'w-full text-left px-3 py-2 rounded-md text-xs transition-colors',
                'hover:bg-muted/50',
                idx === activeIndex
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'text-muted-foreground'
              )}
            >
              <div className="flex items-center gap-2">
                <FileText className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{doc.title}</span>
              </div>
              {doc.subtitle && (
                <p className="mt-0.5 pl-5.5 text-[10px] text-muted-foreground/70 truncate">
                  {doc.subtitle}
                </p>
              )}
            </button>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

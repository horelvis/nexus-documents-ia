'use client'

import { IconAlertTriangle } from '@tabler/icons-react'
import { Card } from '@/components/ui/card'

export function ErrorBubble({ error }: { error: string }) {
  return (
    <div className="w-full emma-message-enter">
      <Card className="relative overflow-hidden p-4 border border-destructive/20 bg-destructive/[0.03] rounded-xl">
        {/* Red accent line */}
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-destructive/50 to-transparent" />

        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <div className="flex items-center justify-center h-6 w-6 rounded-lg bg-destructive/10">
              <IconAlertTriangle className="h-3.5 w-3.5 text-destructive" />
            </div>
            <span className="text-[11px] font-semibold tracking-widest text-destructive/70 uppercase">
              Error
            </span>
          </div>
          <p className="text-sm text-destructive/80 leading-relaxed pl-8">{error}</p>
        </div>
      </Card>
    </div>
  )
}

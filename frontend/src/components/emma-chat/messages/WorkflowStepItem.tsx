'use client'

import { IconCircleCheck, IconAlertCircle } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import type { WorkflowStep } from '@/lib/types/emma'

export function WorkflowStepItem({ step, index = 0 }: { step: WorkflowStep; index?: number }) {
  const getStatusIndicator = () => {
    switch (step.status) {
      case 'completed':
        return <IconCircleCheck className="h-3.5 w-3.5 text-emerald-500" />
      case 'in_progress':
        return (
          <span className="relative flex h-3.5 w-3.5 items-center justify-center">
            <span className="absolute h-2.5 w-2.5 rounded-full bg-primary/30 animate-ping" />
            <span className="relative h-1.5 w-1.5 rounded-full bg-primary" />
          </span>
        )
      case 'error':
        return <IconAlertCircle className="h-3.5 w-3.5 text-destructive" />
      default:
        return <span className="h-1.5 w-1.5 rounded-full border border-muted-foreground/30 ml-1 mr-1" />
    }
  }

  const agentName = step.agent || 'Task'

  return (
    <div
      className={cn(
        'emma-step-enter flex items-center gap-2 text-xs font-mono',
        step.status === 'pending' && 'text-muted-foreground/40',
        step.status === 'in_progress' && 'text-primary',
        step.status === 'completed' && 'text-muted-foreground/70',
        step.status === 'error' && 'text-destructive'
      )}
      style={{ animationDelay: `${index * 80}ms` }}
    >
      {getStatusIndicator()}
      <span className="text-muted-foreground/50">[{agentName}]</span>
      <span>{step.description}</span>
      {step.execution_time_ms && step.status === 'completed' && (
        <span className="text-[10px] text-emerald-500/50 ml-auto tabular-nums">
          {step.execution_time_ms < 1000
            ? `${Math.round(step.execution_time_ms)}ms`
            : `${(step.execution_time_ms / 1000).toFixed(1)}s`}
        </span>
      )}
    </div>
  )
}

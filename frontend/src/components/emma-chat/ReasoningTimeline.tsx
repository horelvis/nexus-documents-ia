'use client'

import { IconBrain, IconSearch, IconEye, IconTool, IconCheck, IconAlertTriangle } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { ReasoningTimelineStep } from '@/lib/services/explainability.service'

// Badge config per step type
type BadgeConfig = {
  label: string
  color: string
  bgColor: string
  borderColor: string
  Icon: React.ElementType
}

const BADGE_CONFIG: Record<ReasoningTimelineStep['type'], BadgeConfig> = {
  thinking: {
    label: 'RAZONAMIENTO',
    color: 'text-purple-300',
    bgColor: 'bg-purple-950/60',
    borderColor: 'border-purple-700/50',
    Icon: IconBrain,
  },
  search: {
    label: 'BÚSQUEDA',
    color: 'text-blue-300',
    bgColor: 'bg-blue-950/60',
    borderColor: 'border-blue-700/50',
    Icon: IconSearch,
  },
  observation: {
    label: 'OBSERVACIÓN',
    color: 'text-amber-300',
    bgColor: 'bg-amber-950/60',
    borderColor: 'border-amber-700/50',
    Icon: IconEye,
  },
  tool_call: {
    label: 'ACCIÓN',
    color: 'text-cyan-300',
    bgColor: 'bg-cyan-950/60',
    borderColor: 'border-cyan-700/50',
    Icon: IconTool,
  },
  tool_result: {
    label: 'ACCIÓN',
    color: 'text-cyan-300',
    bgColor: 'bg-cyan-950/60',
    borderColor: 'border-cyan-700/50',
    Icon: IconTool,
  },
  reflection: {
    label: 'RAZONAMIENTO',
    color: 'text-purple-300',
    bgColor: 'bg-purple-950/60',
    borderColor: 'border-purple-700/50',
    Icon: IconBrain,
  },
  answer: {
    label: 'RESPUESTA',
    color: 'text-green-300',
    bgColor: 'bg-green-950/60',
    borderColor: 'border-green-700/50',
    Icon: IconCheck,
  },
  error: {
    label: 'ERROR',
    color: 'text-red-300',
    bgColor: 'bg-red-950/60',
    borderColor: 'border-red-700/50',
    Icon: IconAlertTriangle,
  },
}

const DOT_COLORS: Record<ReasoningTimelineStep['type'], string> = {
  thinking: 'bg-purple-500',
  search: 'bg-blue-500',
  observation: 'bg-amber-500',
  tool_call: 'bg-cyan-500',
  tool_result: 'bg-cyan-500',
  reflection: 'bg-purple-500',
  answer: 'bg-green-500',
  error: 'bg-red-500',
}

interface ReasoningTimelineProps {
  steps: ReasoningTimelineStep[]
  onStepHover?: (step: ReasoningTimelineStep | null) => void
  className?: string
}

export default function ReasoningTimeline({ steps, onStepHover, className }: ReasoningTimelineProps) {
  if (!steps.length) {
    return (
      <div className={cn('flex items-center justify-center h-full text-muted-foreground text-sm', className)}>
        No hay pasos de razonamiento disponibles.
      </div>
    )
  }

  return (
    <div className={cn('relative flex flex-col gap-0 overflow-y-auto pr-2', className)}>
      {steps.map((step, i) => {
        const config = BADGE_CONFIG[step.type] ?? BADGE_CONFIG.thinking
        const dotColor = DOT_COLORS[step.type] ?? 'bg-slate-500'
        const isLast = i === steps.length - 1
        const relSec = (step.timestamp_ms / 1000).toFixed(1)

        return (
          <div
            key={step.index}
            className="relative flex gap-3 group cursor-default"
            onMouseEnter={() => onStepHover?.(step)}
            onMouseLeave={() => onStepHover?.(null)}
          >
            {/* Timeline line + dot */}
            <div className="relative flex flex-col items-center">
              <div
                className={cn(
                  'w-3 h-3 rounded-full mt-1 shrink-0 ring-2 ring-offset-1 ring-offset-background transition-transform group-hover:scale-125',
                  dotColor,
                  'ring-slate-700'
                )}
              />
              {!isLast && <div className="w-px flex-1 bg-slate-700/60 mt-1" />}
            </div>

            {/* Content card */}
            <div
              className={cn(
                'flex-1 rounded-lg border p-3 mb-3 transition-colors',
                config.bgColor,
                config.borderColor,
                'group-hover:border-opacity-80'
              )}
            >
              {/* Header row */}
              <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                <Badge
                  className={cn(
                    'text-[10px] font-bold tracking-wider border px-1.5 py-0',
                    config.color,
                    config.bgColor,
                    config.borderColor
                  )}
                >
                  <config.Icon size={10} className="mr-1" />
                  {config.label}
                </Badge>
                {step.source && (
                  <span className="text-[10px] text-muted-foreground truncate max-w-[140px]">{step.source}</span>
                )}
                <span className="ml-auto text-[10px] text-slate-500 shrink-0">+{relSec}s</span>
              </div>

              {/* Content */}
              <p className="text-xs text-slate-200 leading-relaxed line-clamp-4">{step.content}</p>

              {/* Detail */}
              {step.detail && (
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed line-clamp-2">{step.detail}</p>
              )}

              {/* Confidence bar */}
              {step.confidence != null && (
                <div className="mt-2 flex items-center gap-2">
                  <span className="text-[10px] text-slate-500">Confianza</span>
                  <div className="flex-1 h-1 rounded-full bg-slate-700 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-green-500 transition-all"
                      style={{ width: `${Math.round(step.confidence * 100)}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-slate-400">{Math.round(step.confidence * 100)}%</span>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

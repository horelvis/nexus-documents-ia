'use client'

import { cn } from '@/lib/utils'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { IconBrain, IconBolt } from '@tabler/icons-react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { History } from 'lucide-react'

interface ChatToolbarProps {
  deepReasoning: boolean
  onDeepReasoningChange: (value: boolean) => void
  showThreadHistory: boolean
  onToggleThreadHistory: () => void
  isLoading: boolean
}

export function ChatToolbar({
  deepReasoning,
  onDeepReasoningChange,
  showThreadHistory,
  onToggleThreadHistory,
  isLoading,
}: ChatToolbarProps) {
  return (
    <TooltipProvider>
      <div className="flex items-center justify-end gap-2 mb-3">
        <button
          onClick={onToggleThreadHistory}
          className={cn(
            'mr-auto flex items-center gap-1.5 px-2 py-1 text-xs rounded transition-colors',
            showThreadHistory
              ? 'bg-primary/10 text-primary'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <History className="h-3.5 w-3.5" />
          Historial
        </button>

        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex items-center gap-2">
              <IconBolt
                className={cn(
                  'h-4 w-4 transition-colors',
                  !deepReasoning ? 'text-yellow-500' : 'text-muted-foreground',
                )}
              />
              <Label
                htmlFor="deep-reasoning"
                className={cn(
                  'text-xs cursor-pointer select-none transition-colors',
                  !deepReasoning ? 'text-foreground' : 'text-muted-foreground',
                )}
              >
                Rápido
              </Label>
              <Switch
                id="deep-reasoning"
                checked={deepReasoning}
                onCheckedChange={onDeepReasoningChange}
                disabled={isLoading}
                className="data-[state=checked]:bg-purple-600"
              />
              <Label
                htmlFor="deep-reasoning"
                className={cn(
                  'text-xs cursor-pointer select-none transition-colors',
                  deepReasoning ? 'text-foreground' : 'text-muted-foreground',
                )}
              >
                Profundo
              </Label>
              <IconBrain
                className={cn(
                  'h-4 w-4 transition-colors',
                  deepReasoning ? 'text-purple-500' : 'text-muted-foreground',
                )}
              />
            </div>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs">
            <p className="font-semibold mb-1">
              {deepReasoning ? 'Modo Profundo' : 'Modo Rápido'}
            </p>
            <p className="text-xs text-muted-foreground">
              {deepReasoning
                ? 'Análisis exhaustivo con razonamiento detallado. Ideal para contratos, cumplimiento y análisis legal.'
                : 'Respuestas rápidas y directas. Ideal para búsquedas simples y consultas generales.'}
            </p>
          </TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  )
}

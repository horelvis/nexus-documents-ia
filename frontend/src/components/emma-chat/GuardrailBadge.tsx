'use client'

import { ShieldCheck, ShieldAlert } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const GUARDRAIL_LABELS: Record<string, string> = {
  global_pii_email: 'Email redactado',
  global_pii_phone: 'Teléfono redactado',
  global_pii_national_id: 'DNI/NIE/NIF redactado',
  global_pii_financial: 'Datos financieros redactados',
  global_min_response: 'Respuesta incompleta',
}

function humanize(name: string): string {
  return GUARDRAIL_LABELS[name] ?? name.replace(/_/g, ' ')
}

interface GuardrailBadgeProps {
  warnings: string[]
  blocked?: boolean
}

export function GuardrailBadge({ warnings, blocked }: GuardrailBadgeProps) {
  if (!warnings || warnings.length === 0) return null

  const Icon = blocked ? ShieldAlert : ShieldCheck
  const tone = blocked
    ? 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-300 dark:border-red-900'
    : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900'

  const summary = blocked
    ? 'Respuesta bloqueada'
    : warnings.length === 1
      ? humanize(warnings[0])
      : `${warnings.length} protecciones aplicadas`

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={`mt-2 inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${tone}`}
          role="status"
          aria-label={`Guardrails aplicados: ${warnings.map(humanize).join(', ')}`}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{summary}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <div className="space-y-1">
          <p className="font-semibold text-xs">
            {blocked
              ? 'La respuesta fue bloqueada por:'
              : 'Se ocultó información sensible:'}
          </p>
          <ul className="list-disc pl-4 text-xs">
            {warnings.map((w) => (
              <li key={w}>{humanize(w)}</li>
            ))}
          </ul>
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

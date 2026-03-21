'use client'

import { IconCircleCheck, IconCircleX, IconLoader2, IconAlertTriangle, IconBrain } from '@tabler/icons-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { VerifiedClaimInfo, VerifiedGenerationMetadata } from '@/lib/types/emma'

interface VerifiedGenerationProgressProps {
  verified: VerifiedGenerationMetadata
}

export function VerifiedGenerationProgress({ verified }: VerifiedGenerationProgressProps) {
  const { claims, current_phase, verified_count, rejected_count, total_claims, topic } = verified
  const processedCount = claims.filter(c => c.status !== 'generating').length
  const progressPercent = total_claims > 0 ? Math.round((processedCount / total_claims) * 100) : 0

  return (
    <div className="w-full">
      <Card className="space-y-3 p-3 bg-emerald-500/5 rounded-lg border border-emerald-500/20">
        {/* Header */}
        <div className="flex items-center gap-2">
          <img src="/emma-avatar.png" alt="Emma" className="h-5 w-5 rounded-full object-cover object-top" />
          <span className="text-xs font-mono text-emerald-600 uppercase tracking-wide">
            GENERACIÓN VERIFICADA:
          </span>
          {current_phase !== 'complete' && (
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse ml-auto" />
          )}
        </div>

        {/* Topic */}
        <p className="text-sm text-muted-foreground font-mono truncate">
          {topic}
        </p>

        {/* Progress bar */}
        <div className="space-y-1">
          <div className="flex justify-between text-[10px] font-mono text-muted-foreground">
            <span>{processedCount}/{total_claims || '?'} claims</span>
            <span>{progressPercent}%</span>
          </div>
          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 rounded-full transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Claims list */}
        {claims.length > 0 && (
          <div className="space-y-1.5 max-h-[300px] overflow-y-auto">
            {claims.map((claim) => (
              <ClaimItem key={claim.claim_id} claim={claim} />
            ))}
          </div>
        )}

        {/* Summary badges */}
        <div className="flex gap-2 pt-1 border-t border-emerald-500/10">
          <Badge variant="outline" className="text-[10px] font-mono bg-emerald-500/10 text-emerald-600 border-emerald-500/20">
            {verified_count} verificados
          </Badge>
          {rejected_count > 0 && (
            <Badge variant="outline" className="text-[10px] font-mono bg-destructive/10 text-destructive border-destructive/20">
              {rejected_count} rechazados
            </Badge>
          )}
          <Badge variant="outline" className="text-[10px] font-mono">
            {current_phase === 'generating' ? 'Generando...' : current_phase === 'verifying' ? 'Verificando...' : 'Completo'}
          </Badge>
        </div>
      </Card>
    </div>
  )
}

function ClaimItem({ claim }: { claim: VerifiedClaimInfo }) {
  const getStatusIcon = () => {
    switch (claim.status) {
      case 'verified':
        return <IconCircleCheck className="h-3.5 w-3.5 text-emerald-500" />
      case 'corrected':
        return <IconAlertTriangle className="h-3.5 w-3.5 text-amber-500" />
      case 'rejected':
        return <IconCircleX className="h-3.5 w-3.5 text-destructive" />
      case 'verifying':
        return <IconLoader2 className="h-3.5 w-3.5 text-primary animate-spin" />
      case 'generating':
      default:
        return <span className="h-2 w-2 rounded-full bg-muted-foreground/30" />
    }
  }

  return (
    <div className={cn(
      'flex items-start gap-2 text-xs font-mono',
      claim.status === 'rejected' && 'text-muted-foreground/50 line-through',
      claim.status === 'verifying' && 'text-primary',
      claim.status === 'verified' && 'text-foreground',
      claim.status === 'corrected' && 'text-amber-700',
    )}>
      <div className="mt-0.5 shrink-0">{getStatusIcon()}</div>
      <span className="flex-1 min-w-0 break-words">{claim.claim_text}</span>
      {claim.confidence !== undefined && claim.status !== 'generating' && (
        <span className="shrink-0 text-[10px] text-muted-foreground">
          {Math.round(claim.confidence * 100)}%
        </span>
      )}
    </div>
  )
}

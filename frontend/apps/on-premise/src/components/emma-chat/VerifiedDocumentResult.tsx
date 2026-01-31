'use client'

import { useState } from 'react'
import { IconCircleCheck, IconCircleX, IconEdit, IconCopy, IconCheck, IconBrain, IconFileTypePdf, IconLoader2 } from '@tabler/icons-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { VerifiedGenerationMetadata } from '@/lib/types/emma'
import { EmmaMarkdown } from './EmmaMarkdown'
import { API_CONFIG } from '@/lib/config'

interface VerifiedDocumentResultProps {
  content: string
  verified: VerifiedGenerationMetadata
}

export function VerifiedDocumentResult({ content, verified }: VerifiedDocumentResultProps) {
  const [copied, setCopied] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const { claims, verified_count, rejected_count, total_claims, execution_time_ms, average_confidence } = verified
  const documentText = verified.document_text || content

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(documentText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // fallback
    }
  }

  const handleDownloadPDF = async () => {
    if (!verified.session_id) return
    setIsDownloading(true)
    try {
      const stored = typeof window !== 'undefined' ? sessionStorage.getItem('nexus_sso_tokens') : null
      const token = stored ? JSON.parse(stored).access_token : null
      const url = `${API_CONFIG.STREAMING_BASE_URL}${API_CONFIG.API_V1}${API_CONFIG.ENDPOINTS.EMMA_VERIFIED_SESSION_PDF(verified.session_id)}`
      const response = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token || ''}` },
      })
      if (!response.ok) throw new Error("PDF generation failed")
      const blob = await response.blob()
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = blobUrl
      a.download = `informe_verificado_${verified.session_id.slice(0, 8)}.pdf`
      a.click()
      URL.revokeObjectURL(blobUrl)
    } catch {
      // silent fail
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <div className="w-full">
      <Card className="space-y-3 p-3 bg-emerald-500/5 rounded-lg border border-emerald-500/20">
        {/* Header */}
        <div className="flex items-center gap-2">
          <img src="/emma-avatar.png" alt="Emma" className="h-5 w-5 rounded-full object-cover object-top" />
          <span className="text-xs font-mono text-emerald-600 uppercase tracking-wide">
            DOCUMENTO VERIFICADO:
          </span>
        </div>

        {/* Stats bar */}
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="text-[10px] font-mono bg-emerald-500/10 text-emerald-600 border-emerald-500/20">
            <IconCircleCheck className="h-3 w-3 mr-1" />
            {verified_count} verificados
          </Badge>
          {rejected_count > 0 && (
            <Badge variant="outline" className="text-[10px] font-mono bg-destructive/10 text-destructive border-destructive/20">
              <IconCircleX className="h-3 w-3 mr-1" />
              {rejected_count} rechazados
            </Badge>
          )}
          {average_confidence !== undefined && (
            <Badge variant="outline" className="text-[10px] font-mono">
              Confianza: {Math.round(average_confidence * 100)}%
            </Badge>
          )}
          {execution_time_ms !== undefined && (
            <Badge variant="outline" className="text-[10px] font-mono text-muted-foreground">
              {execution_time_ms < 1000
                ? `${Math.round(execution_time_ms)}ms`
                : `${(execution_time_ms / 1000).toFixed(1)}s`}
            </Badge>
          )}
        </div>

        {/* Document content */}
        <div className="pt-2 border-t border-emerald-500/10">
          <EmmaMarkdown content={documentText} />
        </div>

        {/* Claims summary (collapsible) */}
        <ClaimsSummary claims={claims} />

        {/* Actions */}
        <div className="flex gap-2 pt-2 border-t border-emerald-500/10">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopy}
            className="text-xs h-7 font-mono"
          >
            {copied ? (
              <>
                <IconCheck className="h-3 w-3 mr-1" />
                Copiado
              </>
            ) : (
              <>
                <IconCopy className="h-3 w-3 mr-1" />
                Copiar documento
              </>
            )}
          </Button>
          {verified.session_id && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadPDF}
              disabled={isDownloading}
              className="text-xs h-7 font-mono"
            >
              {isDownloading ? (
                <>
                  <IconLoader2 className="h-3 w-3 mr-1 animate-spin" />
                  Generando PDF...
                </>
              ) : (
                <>
                  <IconFileTypePdf className="h-3 w-3 mr-1" />
                  Descargar PDF
                </>
              )}
            </Button>
          )}
        </div>
      </Card>
    </div>
  )
}

function ClaimsSummary({ claims }: { claims: VerifiedGenerationMetadata['claims'] }) {
  const [expanded, setExpanded] = useState(false)

  if (claims.length === 0) return null

  return (
    <div className="space-y-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
      >
        {expanded ? '▼' : '▶'} {claims.length} claims detallados
      </button>
      {expanded && (
        <div className="space-y-1 ml-3 max-h-[200px] overflow-y-auto">
          {claims.map((claim) => (
            <div key={claim.claim_id} className={cn(
              'flex items-start gap-1.5 text-[10px] font-mono',
              claim.status === 'rejected' && 'text-muted-foreground/50',
            )}>
              {claim.status === 'verified' && <IconCircleCheck className="h-3 w-3 text-emerald-500 shrink-0 mt-0.5" />}
              {claim.status === 'corrected' && <IconEdit className="h-3 w-3 text-amber-500 shrink-0 mt-0.5" />}
              {claim.status === 'rejected' && <IconCircleX className="h-3 w-3 text-destructive shrink-0 mt-0.5" />}
              <span className="flex-1 min-w-0">{claim.claim_text}</span>
              {claim.confidence !== undefined && (
                <span className="shrink-0 text-muted-foreground">{Math.round(claim.confidence * 100)}%</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

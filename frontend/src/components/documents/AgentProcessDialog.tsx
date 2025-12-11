'use client'

import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Loader2 } from 'lucide-react'
import { useTranslation } from '@/lib/i18n/hooks'

interface AgentOption {
  id: string
  name: string
  description: string
}

const AGENTS: AgentOption[] = [
  { id: 'auto', name: 'Auto', description: 'Emma elige el mejor agente' },
  { id: 'search', name: 'Búsqueda', description: 'Encuentra documentos relevantes' },
  { id: 'analyst', name: 'Análisis', description: 'Analiza en profundidad' },
  { id: 'contract', name: 'Contratos', description: 'Revisa cláusulas y riesgos' },
  { id: 'compliance', name: 'Cumplimiento', description: 'Verifica GDPR/LOPD' },
  { id: 'summarizer', name: 'Resúmenes', description: 'Genera resumen ejecutivo' },
]

interface AgentProcessDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  documentIds: string[]
  documentNames?: string[]
  onProcess: (agentId: string, documentIds: string[]) => Promise<void>
  isProcessing?: boolean
}

export function AgentProcessDialog({
  open,
  onOpenChange,
  documentIds,
  documentNames,
  onProcess,
  isProcessing = false,
}: AgentProcessDialogProps) {
  const { t } = useTranslation()
  const [selectedAgent, setSelectedAgent] = useState('auto')

  const handleProcess = async () => {
    await onProcess(selectedAgent, documentIds)
  }

  const docCount = documentIds.length
  const docLabel = docCount === 1 ? 'documento' : 'documentos'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('documents.agentAnalysisDialog')}</DialogTitle>
        </DialogHeader>

        {documentNames && documentNames.length > 0 && documentNames.length <= 3 && (
          <div className="text-sm text-muted-foreground mb-2">
            {documentNames.map((name, i) => (
              <div key={i} className="truncate">{name}</div>
            ))}
          </div>
        )}

        <RadioGroup
          value={selectedAgent}
          onValueChange={setSelectedAgent}
          disabled={isProcessing}
        >
          {AGENTS.map((agent, index) => (
            <div key={agent.id}>
              {index === 1 && <Separator className="my-2" />}
              <div className="flex items-center space-x-3 py-2">
                <RadioGroupItem value={agent.id} id={agent.id} />
                <Label
                  htmlFor={agent.id}
                  className="flex-1 cursor-pointer flex items-baseline gap-2"
                >
                  <span className="font-medium">{agent.name}</span>
                  <span className="text-muted-foreground text-sm">
                    {agent.description}
                  </span>
                </Label>
              </div>
            </div>
          ))}
        </RadioGroup>

        <DialogFooter>
          <Button
            onClick={handleProcess}
            className="w-full"
            disabled={isProcessing || docCount === 0}
          >
            {isProcessing ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Procesando...
              </>
            ) : (
              `Procesar ${docCount} ${docLabel}`
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

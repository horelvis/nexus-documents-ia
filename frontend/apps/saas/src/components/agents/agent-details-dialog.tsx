'use client'

import React from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  IconInfoCircle,
  IconSparkles,
  IconTool,
  IconBrain,
  IconChevronRight
} from '@tabler/icons-react'
import { Agent } from '@/lib/services/agents.service'
import { getAgentUseCase } from '@/lib/agent-use-cases'

interface AgentDetailsDialogProps {
  agent: Agent | null
  isOpen: boolean
  onClose: () => void
  onSelectExample?: (agentId: string, example: string) => void
}

export function AgentDetailsDialog({ agent, isOpen, onClose, onSelectExample }: AgentDetailsDialogProps) {
  if (!agent) return null

  const useCase = getAgentUseCase(agent.id)

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <IconInfoCircle className="h-5 w-5 text-blue-600" />
            {useCase?.title || agent.name}
          </DialogTitle>
          <DialogDescription>
            {useCase?.description || agent.description}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 mt-4">
          {/* Agent Type and Status */}
          <div className="flex items-center gap-2">
            <Badge variant={agent.is_active ? "default" : "secondary"}>
              {agent.is_active ? 'Active' : 'Inactive'}
            </Badge>
            <Badge variant="outline">
              {agent.type || 'General'}
            </Badge>
            {agent.source === 'dynamic' && (
              <Badge variant="secondary">Custom Agent</Badge>
            )}
          </div>

          {/* Benefits Section */}
          {useCase?.benefits && (
            <div>
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                <IconSparkles className="h-4 w-4 text-yellow-600" />
                ¿Qué puede hacer este agente?
              </h3>
              <div className="space-y-2">
                {useCase.benefits.map((benefit, idx) => (
                  <div key={idx} className="flex items-start gap-2">
                    <IconChevronRight className="h-4 w-4 mt-0.5 text-green-600 flex-shrink-0" />
                    <span className="text-sm text-muted-foreground">{benefit}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <Separator />

          {/* Example Queries */}
          {useCase?.examples && (
            <div>
              <h3 className="text-sm font-semibold mb-3">Ejemplos de uso:</h3>
              <div className="grid gap-2">
                {useCase.examples.map((example, idx) => (
                  <Button
                    key={idx}
                    variant="outline"
                    className="justify-start text-left"
                    onClick={() => {
                      onSelectExample?.(agent.id, example)
                      onClose()
                    }}
                  >
                    <span className="text-sm">{example}</span>
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Tools and Capabilities */}
          {(agent.tools || agent.capabilities) && (
            <>
              <Separator />
              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <IconTool className="h-4 w-4" />
                  Herramientas y capacidades
                </h3>
                <div className="flex flex-wrap gap-2">
                  {agent.tools?.map((tool, idx) => (
                    <Badge key={idx} variant="secondary">
                      {tool}
                    </Badge>
                  ))}
                  {agent.capabilities?.map((cap, idx) => (
                    <Badge key={idx} variant="outline">
                      {cap.replace(/_/g, ' ')}
                    </Badge>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* Configuration Info */}
          {agent.configuration && Object.keys(agent.configuration).length > 0 && (
            <>
              <Separator />
              <div>
                <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                  <IconBrain className="h-4 w-4" />
                  Configuración
                </h3>
                <div className="bg-muted/50 rounded-lg p-3">
                  <pre className="text-xs overflow-x-auto">
                    {JSON.stringify(agent.configuration, null, 2)}
                  </pre>
                </div>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
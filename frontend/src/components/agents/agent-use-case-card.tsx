'use client'

import React from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  IconSparkles,
  IconChevronRight,
  IconCurrencyDollar,
  IconScale,
  IconFileText,
  IconRobot,
  IconSignature,
  IconBrain
} from '@tabler/icons-react'
import { AgentUseCase } from '@/lib/agent-use-cases'

interface AgentUseCaseCardProps {
  useCase: AgentUseCase
  onSelectExample?: (example: string) => void
  isSelected?: boolean
}

export function AgentUseCaseCard({ useCase, onSelectExample, isSelected }: AgentUseCaseCardProps) {
  const getIcon = () => {
    switch (useCase.agentId) {
      case 'financial_analysis_agent':
        return <IconCurrencyDollar className="h-6 w-6" />
      case 'legal_compliance_agent':
        return <IconScale className="h-6 w-6" />
      case 'document_analyzer_agent':
        return <IconFileText className="h-6 w-6" />
      case 'rag_assistant_agent':
        return <IconRobot className="h-6 w-6" />
      case 'digital_signature_agent':
        return <IconSignature className="h-6 w-6" />
      default:
        return <IconBrain className="h-6 w-6" />
    }
  }

  return (
    <Card className={`transition-all ${isSelected ? 'border-primary shadow-lg' : 'hover:border-primary/50'}`}>
      <CardHeader>
        <CardTitle className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            {getIcon()}
          </div>
          <div>
            <h3 className="text-lg font-semibold">{useCase.title}</h3>
            <p className="text-sm text-muted-foreground font-normal mt-1">
              {useCase.description}
            </p>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Benefits */}
        <div>
          <h4 className="text-sm font-medium mb-2 flex items-center gap-1">
            <IconSparkles className="h-4 w-4 text-yellow-600" />
            Beneficios
          </h4>
          <div className="space-y-1.5">
            {useCase.benefits.map((benefit, idx) => (
              <div key={idx} className="flex items-start gap-2 text-sm">
                <IconChevronRight className="h-4 w-4 mt-0.5 text-green-600 flex-shrink-0" />
                <span className="text-muted-foreground">{benefit}</span>
              </div>
            ))}
          </div>
        </div>

        <Separator />

        {/* Example Queries */}
        <div>
          <h4 className="text-sm font-medium mb-2">Prueba estos ejemplos:</h4>
          <div className="space-y-2">
            {useCase.examples.map((example, idx) => (
              <Button
                key={idx}
                variant="outline"
                size="sm"
                className="w-full justify-start text-left text-sm"
                onClick={() => onSelectExample?.(example)}
              >
                <span className="truncate">{example}</span>
              </Button>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
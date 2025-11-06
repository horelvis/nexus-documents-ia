'use client'

import React, { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChevronDown, ChevronRight, Brain, Cpu, Clock, Target, ArrowRight } from 'lucide-react'

interface DecisionStep {
  step: number
  node_id: string
  reasoning: string
  tools_considered: string[]
  tools_selected: string[]
  confidence: number
  execution_time_ms: number
}

interface ChainOfThoughtData {
  decision_trace: DecisionStep[]
  reasoning_steps: string[]
  tools_selected: string[]
  enhanced_query?: string
  documents_context: number
}

interface ChainOfThoughtDisplayProps {
  data: ChainOfThoughtData
  executionTimeMs: number
  className?: string
}

export function ChainOfThoughtDisplay({ data, executionTimeMs, className }: ChainOfThoughtDisplayProps) {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set([0]))
  const [showEnhancedQuery, setShowEnhancedQuery] = useState(false)

  const toggleStep = (stepIndex: number) => {
    const newExpanded = new Set(expandedSteps)
    if (newExpanded.has(stepIndex)) {
      newExpanded.delete(stepIndex)
    } else {
      newExpanded.add(stepIndex)
    }
    setExpandedSteps(newExpanded)
  }

  const formatExecutionTime = (timeMs: number) => {
    if (timeMs < 1000) return `${timeMs}ms`
    return `${(timeMs / 1000).toFixed(1)}s`
  }

  return (
    <Card className={`border-2 border-blue-200 bg-blue-50/50 ${className}`}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-blue-700">
          <Brain className="h-5 w-5" />
          Chain of Thought Analysis
          <Badge variant="secondary" className="ml-auto">
            Admin Only
          </Badge>
        </CardTitle>
        
        {/* Summary Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
          <div className="flex items-center gap-2 text-sm">
            <Target className="h-4 w-4 text-green-600" />
            <span>Steps: {data.decision_trace.length}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Cpu className="h-4 w-4 text-blue-600" />
            <span>Tools: {data.tools_selected.length}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Clock className="h-4 w-4 text-purple-600" />
            <span>Time: {formatExecutionTime(executionTimeMs)}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-600">Context: {data.documents_context} docs</span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Enhanced Query Section */}
        {data.enhanced_query && (
          <Collapsible open={showEnhancedQuery} onOpenChange={setShowEnhancedQuery}>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm" className="w-full justify-start">
                {showEnhancedQuery ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                Enhanced Query with Context
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <Card className="mt-2 bg-gray-50">
                <CardContent className="pt-4">
                  <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono">
                    {data.enhanced_query}
                  </pre>
                </CardContent>
              </Card>
            </CollapsibleContent>
          </Collapsible>
        )}

        {/* Decision Trace */}
        <div className="space-y-3">
          <h4 className="font-semibold text-sm text-gray-700 flex items-center gap-2">
            <Brain className="h-4 w-4" />
            Decision Trace
          </h4>

          {data.decision_trace.length > 0 ? (
            data.decision_trace.map((step, index) => (
              <div key={step.step} className="relative">
                {/* Connection Line */}
                {index < data.decision_trace.length - 1 && (
                  <div className="absolute left-6 top-12 w-px h-6 bg-gray-300" />
                )}
                
                <Collapsible 
                  open={expandedSteps.has(index)} 
                  onOpenChange={() => toggleStep(index)}
                >
                  <CollapsibleTrigger asChild>
                    <Card className="cursor-pointer hover:shadow-sm transition-shadow">
                      <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                          <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center text-xs font-semibold text-blue-700">
                            {step.step}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between">
                              <div className="font-medium text-sm text-gray-900">
                                Node: {step.node_id}
                              </div>
                              <div className="flex items-center gap-2">
                                <Badge variant="outline" className="text-xs">
                                  {formatExecutionTime(step.execution_time_ms)}
                                </Badge>
                                <Badge 
                                  variant={step.confidence > 0.8 ? "default" : step.confidence > 0.6 ? "secondary" : "destructive"}
                                  className="text-xs"
                                >
                                  {Math.round(step.confidence * 100)}%
                                </Badge>
                                {expandedSteps.has(index) ? 
                                  <ChevronDown className="h-4 w-4 text-gray-400" /> : 
                                  <ChevronRight className="h-4 w-4 text-gray-400" />
                                }
                              </div>
                            </div>
                            <div className="text-xs text-gray-600 mt-1 truncate">
                              {step.reasoning.substring(0, 100)}...
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </CollapsibleTrigger>

                  <CollapsibleContent>
                    <Card className="mt-2 ml-9 bg-gray-50">
                      <CardContent className="p-4 space-y-3">
                        {/* Reasoning */}
                        <div>
                          <h5 className="font-medium text-xs text-gray-700 mb-2">Reasoning:</h5>
                          <p className="text-sm text-gray-600 whitespace-pre-wrap">
                            {step.reasoning}
                          </p>
                        </div>

                        {/* Tools */}
                        {step.tools_considered.length > 0 && (
                          <div>
                            <h5 className="font-medium text-xs text-gray-700 mb-2">Tools Considered:</h5>
                            <div className="flex flex-wrap gap-1">
                              {step.tools_considered.map((tool, i) => (
                                <Badge 
                                  key={i}
                                  variant={step.tools_selected.includes(tool) ? "default" : "outline"}
                                  className="text-xs"
                                >
                                  {tool}
                                  {step.tools_selected.includes(tool) && (
                                    <ArrowRight className="h-3 w-3 ml-1" />
                                  )}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  </CollapsibleContent>
                </Collapsible>
              </div>
            ))
          ) : (
            <div className="text-center py-8 text-gray-500">
              <Brain className="h-8 w-8 mx-auto mb-2 text-gray-300" />
              <p className="text-sm">No detailed decision trace available</p>
              <p className="text-xs">Enable debug mode for detailed chain-of-thought analysis</p>
            </div>
          )}
        </div>

        {/* Final Tools Summary */}
        {data.tools_selected.length > 0 && (
          <div className="pt-3 border-t">
            <h4 className="font-semibold text-sm text-gray-700 mb-2">Final Tools Used:</h4>
            <div className="flex flex-wrap gap-1">
              {data.tools_selected.map((tool, index) => (
                <Badge key={index} variant="default" className="text-xs">
                  {tool}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Reasoning Steps Summary */}
        {data.reasoning_steps.length > 0 && (
          <div className="pt-3 border-t">
            <h4 className="font-semibold text-sm text-gray-700 mb-2">Key Reasoning Steps:</h4>
            <ul className="space-y-1">
              {data.reasoning_steps.slice(0, 3).map((step, index) => (
                <li key={index} className="text-xs text-gray-600 flex items-start gap-2">
                  <div className="w-1 h-1 rounded-full bg-gray-400 mt-2 flex-shrink-0" />
                  {step}
                </li>
              ))}
              {data.reasoning_steps.length > 3 && (
                <li className="text-xs text-gray-500 italic">
                  ... and {data.reasoning_steps.length - 3} more steps
                </li>
              )}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
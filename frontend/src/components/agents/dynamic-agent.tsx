"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import * as Icons from "@tabler/icons-react"
import { SearchResult } from "@/lib/services/search.service"

interface DynamicAgentProps {
  agentDefinition: AgentDefinition
  searchResults: SearchResult[]
  searchQuery: string
  onActionClick: (action: string) => void | Promise<void>
}

interface AgentDefinition {
  name: string
  display_name: string
  description: string
  icon?: string
  color?: string
  capabilities: string[]
  ui_config: {
    icon?: string
    color?: string
    quick_actions?: string[]
    show_filters?: boolean
    custom_components?: any[]
  }
}

export default function DynamicAgent({ 
  agentDefinition,
  searchResults, 
  searchQuery,
  onActionClick 
}: DynamicAgentProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)

  // Get the icon component dynamically
  const iconName = agentDefinition.ui_config?.icon || agentDefinition.icon || "IconRobot"
  const IconComponent = Icons[iconName as keyof typeof Icons] || Icons.IconRobot
  const color = agentDefinition.ui_config?.color || agentDefinition.color || "blue"

  // Check if agent should be shown based on search context
  const shouldShow = () => {
    // Agent can define its own visibility rules
    if (agentDefinition.capabilities.includes("always_show")) return true
    
    // Check if search query or results match agent's domain
    const keywords = agentDefinition.capabilities.flatMap(cap => {
      // Map capabilities to keywords
      const keywordMap: Record<string, string[]> = {
        "financial_analysis": ["factura", "invoice", "presupuesto", "budget", "pago", "payment"],
        "legal_compliance": ["contrato", "contract", "legal", "compliance", "terms"],
        "document_analysis": ["analyze", "analysis", "review", "summary"],
        // Add more mappings as needed
      }
      return keywordMap[cap] || []
    })

    return keywords.some(keyword => 
      searchQuery.toLowerCase().includes(keyword) ||
      searchResults.some(result => {
        const doc = result.document || result.metadata || {}
        const text = `${doc.title || ''} ${doc.description || ''} ${result.content || ''}`.toLowerCase()
        return text.includes(keyword)
      })
    )
  }

  const handleAction = async (action: string) => {
    setIsProcessing(true)
    setIsExpanded(true)
    
    try {
      await onActionClick(action)
    } finally {
      setIsProcessing(false)
    }
  }

  if (!shouldShow()) {
    return null
  }

  const colorClasses = {
    blue: "border-blue-200 bg-blue-50/50 dark:bg-blue-950/20 dark:border-blue-800",
    emerald: "border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/20 dark:border-emerald-800",
    purple: "border-purple-200 bg-purple-50/50 dark:bg-purple-950/20 dark:border-purple-800",
    amber: "border-amber-200 bg-amber-50/50 dark:bg-amber-950/20 dark:border-amber-800",
    red: "border-red-200 bg-red-50/50 dark:bg-red-950/20 dark:border-red-800",
  }

  const textColorClasses = {
    blue: "text-blue-700 dark:text-blue-300",
    emerald: "text-emerald-700 dark:text-emerald-300",
    purple: "text-purple-700 dark:text-purple-300",
    amber: "text-amber-700 dark:text-amber-300",
    red: "text-red-700 dark:text-red-300",
  }

  return (
    <Card className={colorClasses[color as keyof typeof colorClasses] || colorClasses.blue}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className={`flex items-center gap-2 ${textColorClasses[color as keyof typeof textColorClasses] || textColorClasses.blue}`}>
            <IconComponent className="h-5 w-5" />
            {agentDefinition.display_name}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              {agentDefinition.capabilities.length} capabilities
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
              className={textColorClasses[color as keyof typeof textColorClasses]}
            >
              {isExpanded ? (
                <Icons.IconChevronUp className="h-4 w-4" />
              ) : (
                <Icons.IconChevronDown className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
        
        {!isExpanded && (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              {agentDefinition.description}
            </p>
            
            {agentDefinition.ui_config?.quick_actions && (
              <div className="flex flex-wrap gap-2">
                {agentDefinition.ui_config.quick_actions.slice(0, 2).map((action, index) => (
                  <Button
                    key={index}
                    size="sm"
                    variant="outline"
                    onClick={() => handleAction(action)}
                    disabled={isProcessing}
                    className="h-6 text-xs"
                  >
                    {isProcessing ? (
                      <Icons.IconRefresh className="h-3 w-3 animate-spin mr-1" />
                    ) : (
                      <Icons.IconSparkles className="h-3 w-3 mr-1" />
                    )}
                    {action}
                  </Button>
                ))}
              </div>
            )}
          </div>
        )}
      </CardHeader>

      {isExpanded && (
        <CardContent className="space-y-4">
          {/* Capabilities */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Icons.IconBrain className="h-4 w-4" />
              Capabilities:
            </div>
            <div className="flex flex-wrap gap-2">
              {agentDefinition.capabilities.map((capability, index) => (
                <Badge key={index} variant="secondary" className="text-xs">
                  {capability.replace(/_/g, ' ')}
                </Badge>
              ))}
            </div>
          </div>

          <Separator />

          {/* Quick Actions */}
          {agentDefinition.ui_config?.quick_actions && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Icons.IconSparkles className="h-4 w-4" />
                Quick Actions:
              </div>
              <div className="grid grid-cols-1 gap-2">
                {agentDefinition.ui_config.quick_actions.map((action, index) => (
                  <Button
                    key={index}
                    size="sm"
                    variant="outline"
                    onClick={() => handleAction(action)}
                    disabled={isProcessing}
                    className="justify-start h-8 text-xs"
                  >
                    {isProcessing ? (
                      <Icons.IconRefresh className="h-3 w-3 animate-spin mr-2" />
                    ) : (
                      <Icons.IconArrowRight className="h-3 w-3 mr-2" />
                    )}
                    {action}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* Custom Components Placeholder */}
          {agentDefinition.ui_config?.custom_components && (
            <div className="space-y-2">
              <div className="text-sm text-muted-foreground">
                {/* Here we would render custom components based on configuration */}
                Custom analysis components would appear here
              </div>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  )
}
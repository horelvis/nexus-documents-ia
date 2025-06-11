import { useState, useEffect, useCallback } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { Agent } from '@/lib/services/agents.service'

interface UseAgentSelectionReturn {
  selectedAgent: Agent | null
  selectAgent: (agent: Agent) => void
  clearSelection: () => void
  selectedAgentId: string | null
}

export function useAgentSelection(agents: Agent[] = []): UseAgentSelectionReturn {
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const searchParams = useSearchParams()
  const router = useRouter()

  // Auto-select agent from URL parameter
  useEffect(() => {
    const agentId = searchParams.get('agentId')
    if (agentId && agents.length > 0) {
      const agent = agents.find(a => a.id === agentId)
      if (agent && agent.id !== selectedAgent?.id) {
        setSelectedAgent(agent)
      }
    } else if (!agentId && selectedAgent) {
      setSelectedAgent(null)
    }
  }, [searchParams, agents, selectedAgent?.id])

  const selectAgent = useCallback((agent: Agent) => {
    setSelectedAgent(agent)
    
    // Update URL to reflect selection
    const currentPath = window.location.pathname
    const newUrl = `${currentPath}?agentId=${agent.id}`
    router.push(newUrl, { scroll: false })
  }, [router])

  const clearSelection = useCallback(() => {
    setSelectedAgent(null)
    
    // Remove agentId from URL
    const currentPath = window.location.pathname
    router.push(currentPath, { scroll: false })
  }, [router])

  return {
    selectedAgent,
    selectAgent,
    clearSelection,
    selectedAgentId: selectedAgent?.id || searchParams.get('agentId')
  }
}
'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { AdminGuard } from '@/components/auth/admin-guard'
import { AgentBuilderForm } from '@/components/agents/agent-builder-form'
import { agentsService } from '@/lib/services/agents.service'
import type { Agent } from '@/lib/types/agent'

export default function EditAgentPage() {
  return (
    <AdminGuard>
      <EditAgentContent />
    </AdminGuard>
  )
}

function EditAgentContent() {
  const params = useParams()
  const id = typeof params?.id === 'string' ? params.id : Array.isArray(params?.id) ? params.id[0] : ''
  const [agent, setAgent] = useState<Agent | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    setIsLoading(true)
    setError(null)
    void (async () => {
      const r = await agentsService.get(id)
      if (r.error || !r.data) setError(r.error || 'No data')
      else setAgent(r.data)
      setIsLoading(false)
    })()
  }, [id])

  return (
    <div className="container mx-auto p-6">
      <Link href="/admin/agents" className="text-sm text-blue-600 hover:underline">
        ← Volver al catálogo
      </Link>
      <h1 className="text-2xl font-semibold my-4">Editar agente</h1>
      {error && <p className="text-red-700 mb-4">{error}</p>}
      {isLoading ? (
        <p>Cargando…</p>
      ) : agent ? (
        <AgentBuilderForm mode="edit" initial={agent} />
      ) : (
        <p>Agente no encontrado.</p>
      )}
    </div>
  )
}

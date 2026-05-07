'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconRobot } from '@tabler/icons-react'
import { agentsService } from '@/lib/services/agents.service'
import type { Agent } from '@/lib/types/agent'

export default function AgentsGalleryPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [orderBy, setOrderBy] = useState<'name' | 'usage_count'>('name')
  const router = useRouter()

  useEffect(() => {
    setIsLoading(true)
    setError(null)
    void (async () => {
      const r = await agentsService.list({ active: true, order_by: orderBy })
      if (r.error || !r.data) setError(r.error || 'No data')
      else setAgents(r.data)
      setIsLoading(false)
    })()
  }, [orderBy])

  return (
    <div className="container mx-auto p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Asistentes disponibles</h1>
        <select
          value={orderBy}
          onChange={(e) => setOrderBy(e.target.value as 'name' | 'usage_count')}
          className="border rounded px-2 py-1 text-sm"
        >
          <option value="name">Ordenar por nombre</option>
          <option value="usage_count">Más usados</option>
        </select>
      </div>

      {error && (
        <p className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 px-3 py-2 rounded">
          {error}
        </p>
      )}

      {isLoading ? (
        <p>Cargando…</p>
      ) : agents.length === 0 ? (
        <p>No hay agentes activos en este momento.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <article key={agent.id} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
              <div className="flex items-center gap-2 mb-2">
                <IconRobot size={20} />
                <h2 className="font-semibold">{agent.name}</h2>
                {agent.is_seed && (
                  <span className="ml-auto text-xs px-2 py-0.5 rounded bg-purple-100 text-purple-800">SEED</span>
                )}
              </div>
              <p className="text-sm text-gray-600 mb-3 min-h-[3em]">
                {agent.description ?? '—'}
              </p>
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>{agent.usage_count} usos</span>
                <button
                  type="button"
                  onClick={() => router.push(`/?prefill=${encodeURIComponent('@' + agent.slug + ' ')}`)}
                  className="px-3 py-1 bg-blue-600 text-white rounded text-xs"
                >
                  Probar
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

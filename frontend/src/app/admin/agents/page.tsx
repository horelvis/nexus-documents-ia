'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { AdminGuard } from '@/components/auth/admin-guard'
import { agentsService } from '@/lib/services/agents.service'
import type { Agent } from '@/lib/types/agent'

export default function AgentsAdminPage() {
  return (
    <AdminGuard>
      <AgentsAdminContent />
    </AdminGuard>
  )
}

function AgentsAdminContent() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function loadAgents() {
    setIsLoading(true)
    setError(null)
    const r = await agentsService.list()
    if (r.error || !r.data) setError(r.error || 'No data')
    else setAgents(r.data)
    setIsLoading(false)
  }

  useEffect(() => {
    void loadAgents()
  }, [])

  async function handleToggleActive(agent: Agent) {
    const r = await agentsService.update(agent.id, { is_active: !agent.is_active })
    if (r.error) {
      alert(`No se pudo cambiar estado: ${r.error}`)
      return
    }
    void loadAgents()
  }

  return (
    <div className="container mx-auto p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Catálogo de agentes</h1>
        <Link
          href="/admin/agents/new"
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          + Nuevo agente
        </Link>
      </div>

      {error && (
        <p className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 px-3 py-2 rounded">
          {error}
        </p>
      )}

      {isLoading ? (
        <p>Cargando…</p>
      ) : agents.length === 0 ? (
        <p>No hay agentes. Crea el primero.</p>
      ) : (
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b text-left text-sm">
              <th className="py-2 pr-3">Nombre</th>
              <th className="py-2 pr-3">Slug</th>
              <th className="py-2 pr-3">Estado</th>
              <th className="py-2 pr-3">Uso</th>
              <th className="py-2 pr-3">Tipo</th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.id} className="border-b hover:bg-gray-50">
                <td className="py-2 pr-3">{a.name}</td>
                <td className="py-2 pr-3 font-mono text-sm">@{a.slug}</td>
                <td className="py-2 pr-3">
                  <button
                    onClick={() => handleToggleActive(a)}
                    disabled={a.is_seed && a.is_active}
                    title={a.is_seed && a.is_active ? 'Un seed activo no se puede desactivar' : ''}
                    className={`px-2 py-0.5 rounded text-xs ${a.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-700'}`}
                  >
                    {a.is_active ? 'Activo' : 'Inactivo'}
                  </button>
                </td>
                <td className="py-2 pr-3 text-sm">{a.usage_count}</td>
                <td className="py-2 pr-3 text-xs">
                  {a.is_seed ? <span className="text-purple-700 font-semibold">SEED</span> : 'normal'}
                </td>
                <td className="py-2 text-right">
                  <Link
                    href={`/admin/agents/${a.id}/edit`}
                    className="text-blue-600 text-sm hover:underline"
                  >
                    Editar
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

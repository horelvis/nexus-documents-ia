'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { SidebarProvider, SidebarInset } from '@/components/ui'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import { AgentBuilderForm } from '@/components/agents/agent-builder-form'
import { agentsService } from '@/lib/services/agents.service'
import type { Agent } from '@/lib/types/agent'

export default function EditAgentPage() {
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
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <nav className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/" className="hover:text-foreground transition-colors">Inicio</Link>
            <span>/</span>
            <Link href="/admin/dashboard" className="hover:text-foreground transition-colors">Administración</Link>
            <span>/</span>
            <Link href="/admin/agents" className="hover:text-foreground transition-colors">Agentes</Link>
            <span>/</span>
            <span className="text-foreground font-medium">Editar</span>
          </nav>
        </PageHeader>

        <main className="flex-1 overflow-auto p-4 md:p-6">
          <div className="max-w-3xl mx-auto space-y-6">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Editar agente</h1>
              {agent && (
                <p className="text-sm text-muted-foreground font-mono">@{agent.slug}</p>
              )}
            </div>
            {error && <p className="text-red-700">{error}</p>}
            {isLoading ? (
              <p className="text-muted-foreground">Cargando…</p>
            ) : agent ? (
              <AgentBuilderForm mode="edit" initial={agent} />
            ) : (
              <p>Agente no encontrado.</p>
            )}
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

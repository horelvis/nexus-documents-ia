'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { SidebarProvider, SidebarInset, Badge, Button } from '@/components/ui'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import { AgentBuilderForm } from '@/components/agents/agent-builder-form'
import { AgentsMock, type UserAgentMock } from '@/lib/mocks/agents-mock'

export default function EditAgentPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const [agent, setAgent] = useState<UserAgentMock | null | undefined>(undefined)

  useEffect(() => {
    if (!params?.id) return
    const found = AgentsMock.get(params.id)
    setAgent(found ?? null)
  }, [params?.id])

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <h1 className="font-semibold">
            {agent ? `Editar: ${agent.name}` : 'Editar agente'}
          </h1>
          <Badge variant="secondary" className="text-[10px]">MOCK</Badge>
        </PageHeader>

        {agent === undefined && (
          <div className="p-8 text-sm text-muted-foreground">Cargando…</div>
        )}
        {agent === null && (
          <div className="p-8 space-y-3">
            <p className="text-sm text-muted-foreground">Agente no encontrado.</p>
            <Button onClick={() => router.push('/agents')}>Volver a la galería</Button>
          </div>
        )}
        {agent && <AgentBuilderForm mode="edit" initial={agent} />}
      </SidebarInset>
    </SidebarProvider>
  )
}

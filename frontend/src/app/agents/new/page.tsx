'use client'

import { SidebarProvider, SidebarInset, Badge } from '@/components/ui'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import { AgentBuilderForm } from '@/components/agents/agent-builder-form'

export default function NewAgentPage() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <h1 className="font-semibold">Crear agente</h1>
          <Badge variant="secondary" className="text-[10px]">MOCK</Badge>
        </PageHeader>
        <AgentBuilderForm mode="create" />
      </SidebarInset>
    </SidebarProvider>
  )
}

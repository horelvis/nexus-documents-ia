'use client'

import Link from 'next/link'
import { IconRobot } from '@tabler/icons-react'
import { SidebarProvider, SidebarInset } from '@/components/ui'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import { AgentDashboard } from '@/components/agents/agent-dashboard'

export default function AgentsPage() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <nav className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/" className="hover:text-foreground transition-colors">Inicio</Link>
            <span>/</span>
            <span className="text-foreground font-medium">Agentes</span>
          </nav>
        </PageHeader>

        <main className="flex-1 overflow-auto p-4 md:p-6">
          <div className="space-y-6">
            <div>
              <h1 className="text-2xl font-semibold flex items-center gap-2">
                <IconRobot className="h-6 w-6" />
                Agentes
              </h1>
              <p className="text-sm text-muted-foreground mt-1">
                Panel de monitoreo de los agentes conversacionales.
              </p>
            </div>

            <AgentDashboard />
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

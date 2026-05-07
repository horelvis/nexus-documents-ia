'use client'

/**
 * Agents Gallery — read-only catalog of admin-curated specialist agents.
 *
 * Open to every authenticated user. Each card has a "Probar" button that
 * pre-fills the chat with @<slug>.
 */

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { IconRobot, IconRefresh } from '@tabler/icons-react'
import {
  SidebarProvider,
  SidebarInset,
  Button,
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import { agentsService } from '@/lib/services/agents.service'
import type { Agent } from '@/lib/types/agent'

export default function AgentsGalleryPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [orderBy, setOrderBy] = useState<'name' | 'usage_count'>('name')
  const router = useRouter()

  async function loadAgents() {
    setIsLoading(true)
    setError(null)
    const r = await agentsService.list({ active: true, order_by: orderBy })
    if (r.error || !r.data) setError(r.error || 'No data')
    else setAgents(r.data)
    setIsLoading(false)
  }

  useEffect(() => {
    void loadAgents()
  }, [orderBy])

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <nav className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/" className="hover:text-foreground transition-colors">Inicio</Link>
            <span>/</span>
            <span className="text-foreground font-medium">Asistentes</span>
          </nav>
        </PageHeader>

        <main className="flex-1 overflow-auto p-4 md:p-6">
          <div className="space-y-6 max-w-6xl mx-auto">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">Asistentes disponibles</h1>
                <p className="text-sm text-muted-foreground">
                  Especialistas curados por el administrador. Invócalos en el chat con <code className="px-1 py-0.5 bg-muted rounded text-xs">@&lt;slug&gt;</code>.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Select value={orderBy} onValueChange={(v) => setOrderBy(v as 'name' | 'usage_count')}>
                  <SelectTrigger className="w-44">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="name">Ordenar por nombre</SelectItem>
                    <SelectItem value="usage_count">Más usados</SelectItem>
                  </SelectContent>
                </Select>
                <Button variant="outline" size="icon" onClick={() => loadAgents()} title="Recargar">
                  <IconRefresh className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {error && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 px-3 py-2 rounded">
                {error}
              </div>
            )}

            {isLoading ? (
              <p className="text-muted-foreground">Cargando…</p>
            ) : agents.length === 0 ? (
              <Card>
                <CardContent className="p-8 text-center text-muted-foreground">
                  No hay agentes activos en este momento.
                </CardContent>
              </Card>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {agents.map((agent) => (
                  <Card key={agent.id} className="hover:shadow-md transition-shadow">
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <div className={`p-2 rounded-md bg-${agent.color}-100 text-${agent.color}-700`}>
                            <IconRobot className="h-5 w-5" />
                          </div>
                          <CardTitle className="text-base">{agent.name}</CardTitle>
                        </div>
                        {agent.is_seed && (
                          <Badge variant="secondary" className="text-xs">SEED</Badge>
                        )}
                      </div>
                      <CardDescription className="font-mono text-xs">@{agent.slug}</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <p className="text-sm text-muted-foreground line-clamp-3 min-h-[3.6em]">
                        {agent.description ?? '—'}
                      </p>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">{agent.usage_count} usos</span>
                        <Button
                          size="sm"
                          onClick={() =>
                            router.push(`/?prefill=${encodeURIComponent('@' + agent.slug + ' ')}`)
                          }
                        >
                          Probar
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

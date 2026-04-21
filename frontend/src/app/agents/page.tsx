'use client'

/**
 * /agents — Galería de agentes (mock, localStorage-backed)
 */

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { SidebarProvider, SidebarInset } from '@/components/ui'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import {
  Button, Input, Card, CardContent, Badge,
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
} from '@/components/ui'
import {
  IconPlus, IconSearch, IconBolt, IconUsers, IconLock, IconDotsVertical,
  IconPencil, IconCopy, IconTrash, IconMessage,
} from '@tabler/icons-react'
import { AgentsMock, type UserAgentMock } from '@/lib/mocks/agents-mock'

type FilterMode = 'all' | 'mine' | 'shared'

export default function AgentsGalleryPage() {
  const router = useRouter()
  const search = useSearchParams()
  const [agents, setAgents] = useState<UserAgentMock[]>([])
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FilterMode>('all')
  const [recentlyCreated, setRecentlyCreated] = useState<string | null>(null)

  const load = () => setAgents(AgentsMock.list())

  useEffect(() => {
    load()
    const created = search.get('created')
    if (created) {
      setRecentlyCreated(created)
      const t = setTimeout(() => setRecentlyCreated(null), 3500)
      return () => clearTimeout(t)
    }
  }, [search])

  const handleDelete = (agent: UserAgentMock) => {
    if (!window.confirm(`¿Eliminar "${agent.name}"?`)) return
    AgentsMock.remove(agent.id)
    load()
  }

  const handleDuplicate = (agent: UserAgentMock) => {
    AgentsMock.duplicate(agent.id)
    load()
  }

  const q = query.trim().toLowerCase()
  const filtered = agents.filter((a) => {
    if (filter === 'mine' && a.visibility !== 'private') return false
    if (filter === 'shared' && a.visibility !== 'shared') return false
    if (!q) return true
    return (
      a.name.toLowerCase().includes(q) ||
      a.description.toLowerCase().includes(q) ||
      a.allowed_tools.some((t) => t.includes(q))
    )
  })

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader>
          <h1 className="font-semibold">Mis Agentes</h1>
          <Badge variant="secondary" className="text-[10px]">MOCK</Badge>
        </PageHeader>

        <div className="p-6 space-y-4 overflow-y-auto">
          {recentlyCreated && (
            <div className="border border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 rounded px-3 py-2 text-sm">
              ✅ Agente creado correctamente.
            </div>
          )}

          <div className="flex flex-col sm:flex-row gap-3 justify-between items-start sm:items-center">
            <div className="flex flex-wrap gap-2 items-center">
              <div className="relative">
                <IconSearch className="h-4 w-4 absolute left-2.5 top-2.5 text-muted-foreground" />
                <Input
                  placeholder="Buscar agentes…"
                  className="pl-8 w-64"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              <div className="flex gap-1 border rounded-md p-0.5">
                {(['all', 'mine', 'shared'] as FilterMode[]).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`text-xs px-3 py-1.5 rounded transition ${
                      filter === f ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
                    }`}
                  >
                    {f === 'all' ? 'Todos' : f === 'mine' ? 'Privados' : 'Compartidos'}
                  </button>
                ))}
              </div>
            </div>
            <Button onClick={() => router.push('/agents/new')}>
              <IconPlus className="h-4 w-4 mr-1" /> Crear agente
            </Button>
          </div>

          {filtered.length === 0 ? (
            <EmptyState onCreate={() => router.push('/agents/new')} />
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {filtered.map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  isNew={agent.id === recentlyCreated}
                  onDelete={() => handleDelete(agent)}
                  onDuplicate={() => handleDuplicate(agent)}
                />
              ))}
              <button
                onClick={() => router.push('/agents/new')}
                className="border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center gap-2 text-muted-foreground hover:bg-accent hover:text-foreground transition min-h-[200px]"
              >
                <IconPlus className="h-8 w-8" />
                <span className="font-medium">Crear agente</span>
                <span className="text-xs">desde cero</span>
              </button>
            </div>
          )}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}

function AgentCard({
  agent, isNew, onDelete, onDuplicate,
}: {
  agent: UserAgentMock
  isNew: boolean
  onDelete: () => void
  onDuplicate: () => void
}) {
  return (
    <Card className={`relative transition ${isNew ? 'ring-2 ring-emerald-500' : ''}`}>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between">
          <div
            className="h-12 w-12 rounded-lg flex items-center justify-center text-2xl shrink-0"
            style={{ backgroundColor: agent.color + '22' }}
          >
            {agent.icon}
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-7 w-7">
                <IconDotsVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem asChild>
                <Link href={`/agents/${agent.id}/edit`}>
                  <IconPencil className="h-4 w-4 mr-2" /> Editar
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={onDuplicate}>
                <IconCopy className="h-4 w-4 mr-2" /> Duplicar
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={onDelete} className="text-destructive">
                <IconTrash className="h-4 w-4 mr-2" /> Eliminar
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div>
          <h3 className="font-semibold leading-tight">{agent.name}</h3>
          <p className="text-sm text-muted-foreground line-clamp-2 mt-1">{agent.description}</p>
        </div>

        <div className="flex flex-wrap gap-1">
          {agent.allowed_tools.slice(0, 3).map((t) => (
            <Badge key={t} variant="outline" className="text-[10px] font-mono">{t}</Badge>
          ))}
          {agent.allowed_tools.length > 3 && (
            <Badge variant="outline" className="text-[10px]">+{agent.allowed_tools.length - 3}</Badge>
          )}
        </div>

        <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t">
          <span className="flex items-center gap-1">
            {agent.visibility === 'private' ? (
              <><IconLock className="h-3 w-3" /> Privado</>
            ) : (
              <><IconUsers className="h-3 w-3" /> Compartido</>
            )}
          </span>
          <span className="flex items-center gap-1">
            <IconBolt className="h-3 w-3" /> {agent.usage_count} usos
          </span>
        </div>

        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm" className="flex-1">
            <Link href={`/agents/${agent.id}/edit`}>Editar</Link>
          </Button>
          <Button asChild size="sm" className="flex-1">
            <Link href={`/?agent=${agent.id}`}>
              <IconMessage className="h-3.5 w-3.5 mr-1" /> Abrir
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="border-2 border-dashed rounded-lg p-12 text-center space-y-3">
      <div className="text-5xl">🤖</div>
      <h3 className="font-semibold">Aún no hay agentes que coincidan</h3>
      <p className="text-sm text-muted-foreground">Crea tu primer agente personalizado.</p>
      <Button onClick={onCreate}>
        <IconPlus className="h-4 w-4 mr-1" /> Crear agente
      </Button>
    </div>
  )
}

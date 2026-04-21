'use client'

/**
 * AgentBuilderForm — 2-column layout (form + playground) shared by
 * /agents/new and /agents/[id]/edit.
 *
 * Frontend-only mock: persists via AgentsMock (localStorage).
 */

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  Button, Input, Label, Textarea, Checkbox, Card, CardContent, CardHeader, CardTitle,
  Badge, RadioGroup, RadioGroupItem, Separator,
} from '@/components/ui'
import { IconTrash, IconCopy, IconDeviceFloppy, IconArrowLeft, IconWand } from '@tabler/icons-react'
import { AgentPlaygroundMock } from '@/components/agents/agent-playground-mock'
import {
  AgentsMock, TOOL_CATALOG, FOLDER_SUGGESTIONS, ROLE_SUGGESTIONS,
  type UserAgentMock, type ModelRole, type Visibility,
} from '@/lib/mocks/agents-mock'

interface AgentBuilderFormProps {
  initial?: UserAgentMock
  mode: 'create' | 'edit'
}

const ICON_CHOICES = ['🤖', '⚖️', '💰', '🏥', '📊', '📝', '🔍', '🎓', '🧪', '🛡️', '💼', '🧭']
const COLOR_CHOICES = ['#6366f1', '#10b981', '#ef4444', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899']

export function AgentBuilderForm({ initial, mode }: AgentBuilderFormProps) {
  const router = useRouter()

  const [name, setName]                 = useState(initial?.name ?? '')
  const [description, setDescription]   = useState(initial?.description ?? '')
  const [icon, setIcon]                 = useState(initial?.icon ?? '🤖')
  const [color, setColor]               = useState(initial?.color ?? '#6366f1')
  const [systemPrompt, setSystemPrompt] = useState(initial?.system_prompt ?? '')
  const [tools, setTools]               = useState<Set<string>>(new Set(initial?.allowed_tools ?? ['smart_search']))
  const [modelRole, setModelRole]       = useState<ModelRole>(initial?.model_role ?? 'CHAT')
  const [temperature, setTemperature]   = useState<number>(initial?.temperature ?? 0.5)
  const [folders, setFolders]           = useState<string[]>(initial?.scope.folders ?? [])
  const [roles, setRoles]               = useState<string[]>(initial?.scope.roles ?? [])
  const [visibility, setVisibility]     = useState<Visibility>(initial?.visibility ?? 'private')

  const [isSaving, setIsSaving]         = useState(false)
  const [error, setError]               = useState<string | null>(null)

  const toggleTool = (id: string) =>
    setTools((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const toggleFolder = (f: string) =>
    setFolders((prev) => (prev.includes(f) ? prev.filter((x) => x !== f) : [...prev, f]))

  const toggleRole = (r: string) =>
    setRoles((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]))

  const canSave = useMemo(
    () => name.trim() && description.trim() && systemPrompt.trim() && tools.size > 0,
    [name, description, systemPrompt, tools],
  )

  const handleSave = async () => {
    if (!canSave) return
    setIsSaving(true)
    setError(null)
    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        icon,
        color,
        system_prompt: systemPrompt.trim(),
        allowed_tools: Array.from(tools),
        model_role: modelRole,
        temperature,
        scope: { folders, roles },
        visibility,
      }
      if (mode === 'edit' && initial) {
        AgentsMock.update(initial.id, payload)
        router.push(`/agents`)
      } else {
        const created = AgentsMock.create(payload)
        router.push(`/agents?created=${created.id}`)
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = () => {
    if (!initial) return
    if (!window.confirm(`¿Eliminar el agente "${initial.name}"? Esta acción no se puede deshacer.`)) return
    AgentsMock.remove(initial.id)
    router.push('/agents')
  }

  const handleDuplicate = () => {
    if (!initial) return
    const dup = AgentsMock.duplicate(initial.id)
    if (dup) router.push(`/agents/${dup.id}/edit`)
  }

  const draftConfig = useMemo(
    () => ({
      system_prompt: systemPrompt || 'Eres un agente útil.',
      allowed_tools: Array.from(tools),
      model_role: modelRole,
      temperature,
    }),
    [systemPrompt, tools, modelRole, temperature],
  )

  const toolsByCategory = useMemo(() => {
    const groups: Record<string, typeof TOOL_CATALOG> = {}
    for (const t of TOOL_CATALOG) {
      groups[t.category] = groups[t.category] ?? []
      groups[t.category].push(t)
    }
    return groups
  }, [])

  const categoryLabels: Record<string, string> = {
    core: 'Núcleo', knowledge: 'Conocimiento', external: 'Externos', output: 'Salidas', advanced: 'Avanzado',
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-4 p-4 h-[calc(100vh-3.5rem)] min-h-0">
      {/* IZQ — Formulario */}
      <div className="overflow-y-auto space-y-4 pr-2 min-h-0">
        <div className="flex items-center justify-between sticky top-0 bg-background z-10 py-2 -my-2">
          <Button variant="ghost" size="sm" onClick={() => router.back()}>
            <IconArrowLeft className="h-4 w-4 mr-1" /> Volver
          </Button>
          <div className="flex gap-2">
            {mode === 'edit' && (
              <>
                <Button variant="outline" size="sm" onClick={handleDuplicate}>
                  <IconCopy className="h-4 w-4 mr-1" /> Duplicar
                </Button>
                <Button variant="destructive" size="sm" onClick={handleDelete}>
                  <IconTrash className="h-4 w-4 mr-1" /> Eliminar
                </Button>
              </>
            )}
          </div>
        </div>

        <Card>
          <CardHeader><CardTitle className="text-base">Identidad</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <div className="flex flex-wrap gap-1 flex-1">
                {ICON_CHOICES.map((i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setIcon(i)}
                    className={`h-9 w-9 rounded border text-lg transition ${icon === i ? 'ring-2 ring-primary' : 'hover:bg-accent'}`}
                  >
                    {i}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-1">
              {COLOR_CHOICES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={`h-7 w-7 rounded-full border-2 transition ${color === c ? 'ring-2 ring-offset-2 ring-primary' : ''}`}
                  style={{ backgroundColor: c }}
                  aria-label={`Color ${c}`}
                />
              ))}
            </div>
            <div>
              <Label htmlFor="name">Nombre</Label>
              <Input id="name" placeholder="Ej: Jurídico Laboral" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="description">Descripción</Label>
              <Textarea
                id="description"
                rows={2}
                placeholder="En una frase, qué hace este agente"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center justify-between">
              <span>Comportamiento</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSystemPrompt(
                  'Eres un agente especializado. Responde con precisión y cita tus fuentes. Si falta información, pídela explícitamente.',
                )}
                className="text-xs"
              >
                <IconWand className="h-3 w-3 mr-1" /> Sugerir
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Label htmlFor="prompt">System prompt</Label>
            <Textarea
              id="prompt"
              rows={7}
              placeholder="Eres un agente especializado en…"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              className="font-mono text-xs"
            />
            <p className="text-[11px] text-muted-foreground mt-1">
              En producción se versionará en Langfuse (label: <code>production</code>).
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center justify-between">
              <span>Herramientas</span>
              <Badge variant="secondary">{tools.size} seleccionada{tools.size === 1 ? '' : 's'}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {Object.entries(toolsByCategory).map(([cat, items]) => (
              <div key={cat}>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                  {categoryLabels[cat] ?? cat}
                </p>
                <div className="grid grid-cols-1 gap-1">
                  {items.map((t) => (
                    <label
                      key={t.id}
                      className="flex items-start gap-2 p-2 rounded border hover:bg-accent cursor-pointer"
                    >
                      <Checkbox
                        checked={tools.has(t.id)}
                        onCheckedChange={() => toggleTool(t.id)}
                        className="mt-0.5"
                      />
                      <span className="text-base leading-none">{t.icon}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">{t.label}</span>
                          {t.featureGated && (
                            <Badge variant="outline" className="text-[9px] py-0 h-4">feature-gated</Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground truncate">{t.description}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Modelo</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label>Rol del modelo</Label>
              <RadioGroup value={modelRole} onValueChange={(v) => setModelRole(v as ModelRole)} className="flex gap-4 mt-2">
                <label className="flex items-center gap-2 border rounded px-3 py-2 flex-1 cursor-pointer hover:bg-accent">
                  <RadioGroupItem value="PLANNER" id="r-p" />
                  <div>
                    <div className="text-sm font-medium">Rápido</div>
                    <div className="text-[11px] text-muted-foreground">PLANNER · temp ~0.3</div>
                  </div>
                </label>
                <label className="flex items-center gap-2 border rounded px-3 py-2 flex-1 cursor-pointer hover:bg-accent">
                  <RadioGroupItem value="CHAT" id="r-c" />
                  <div>
                    <div className="text-sm font-medium">Calidad</div>
                    <div className="text-[11px] text-muted-foreground">CHAT · 9B</div>
                  </div>
                </label>
              </RadioGroup>
            </div>
            <div>
              <Label className="flex items-center justify-between">
                <span>Temperatura</span>
                <span className="font-mono text-xs">{temperature.toFixed(2)}</span>
              </Label>
              <input
                type="range"
                min={0} max={1} step={0.05}
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full mt-2 accent-primary"
              />
              <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
                <span>preciso</span><span>equilibrado</span><span>creativo</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Alcance (scope)</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label>Carpetas</Label>
              <div className="flex flex-wrap gap-1 mt-1">
                {FOLDER_SUGGESTIONS.map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => toggleFolder(f)}
                    className={`text-xs px-2 py-1 rounded-full border transition ${
                      folders.includes(f) ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
            <Separator />
            <div>
              <Label>Roles con acceso</Label>
              <div className="flex flex-wrap gap-1 mt-1">
                {ROLE_SUGGESTIONS.map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => toggleRole(r)}
                    className={`text-xs px-2 py-1 rounded-full border transition ${
                      roles.includes(r) ? 'bg-primary text-primary-foreground border-primary' : 'hover:bg-accent'
                    }`}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Visibilidad</CardTitle></CardHeader>
          <CardContent>
            <RadioGroup value={visibility} onValueChange={(v) => setVisibility(v as Visibility)} className="flex gap-4">
              <label className="flex items-center gap-2 border rounded px-3 py-2 flex-1 cursor-pointer hover:bg-accent">
                <RadioGroupItem value="private" id="v-pri" />
                <div>
                  <div className="text-sm font-medium">Privado</div>
                  <div className="text-[11px] text-muted-foreground">Solo tú</div>
                </div>
              </label>
              <label className="flex items-center gap-2 border rounded px-3 py-2 flex-1 cursor-pointer hover:bg-accent">
                <RadioGroupItem value="shared" id="v-sh" />
                <div>
                  <div className="text-sm font-medium">Compartido</div>
                  <div className="text-[11px] text-muted-foreground">Roles seleccionados</div>
                </div>
              </label>
            </RadioGroup>
          </CardContent>
        </Card>

        {error && (
          <div className="text-sm text-destructive border border-destructive/30 bg-destructive/10 rounded px-3 py-2">
            {error}
          </div>
        )}

        <div className="flex gap-2 justify-end sticky bottom-0 bg-background py-3 border-t">
          <Button variant="outline" onClick={() => router.push('/agents')}>Cancelar</Button>
          <Button disabled={!canSave || isSaving} onClick={handleSave}>
            <IconDeviceFloppy className="h-4 w-4 mr-1" />
            {isSaving ? 'Guardando…' : mode === 'edit' ? 'Guardar cambios' : 'Publicar agente'}
          </Button>
        </div>
      </div>

      {/* DCHA — Playground */}
      <div className="min-h-0 min-w-0">
        <AgentPlaygroundMock
          draftConfig={draftConfig}
          disabled={!canSave}
          agentIcon={icon}
          agentName={name || 'Agente (borrador)'}
        />
      </div>
    </div>
  )
}

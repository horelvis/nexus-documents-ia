'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  IconCopy,
  IconTrash,
  IconDeviceFloppy,
  IconX,
  IconWand,
  IconLoader2,
} from '@tabler/icons-react'
import { apiClient } from '@/lib/api-client'
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  Input,
  Label,
  Textarea,
  Switch,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
} from '@/components/ui'
import { agentsService } from '@/lib/services/agents.service'
import type {
  Agent,
  AgentCreatePayload,
  AgentUpdatePayload,
  AgentModelRole,
} from '@/lib/types/agent'

interface AgentBuilderFormProps {
  initial?: Agent
  mode: 'create' | 'edit'
}

const COLOR_OPTIONS = [
  { value: 'blue', label: 'Azul' },
  { value: 'green', label: 'Verde' },
  { value: 'orange', label: 'Naranja' },
  { value: 'purple', label: 'Morado' },
  { value: 'red', label: 'Rojo' },
  { value: 'pink', label: 'Rosa' },
  { value: 'indigo', label: 'Índigo' },
] as const

function autoSlug(name: string): string {
  return name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 50)
}

export function AgentBuilderForm({ initial, mode }: AgentBuilderFormProps) {
  const router = useRouter()

  const [name, setName] = useState(initial?.name ?? '')
  const [slug, setSlug] = useState(initial?.slug ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [icon, setIcon] = useState(initial?.icon ?? 'IconRobot')
  const [color, setColor] = useState(initial?.color ?? 'blue')
  const [instructions, setInstructions] = useState(initial?.persona?.instructions ?? '')
  const [style, setStyle] = useState<Agent['persona']['style']>(initial?.persona?.style ?? 'concise')
  const [language, setLanguage] = useState<Agent['persona']['language']>(
    initial?.persona?.language ?? 'es',
  )
  const [modelRole, setModelRole] = useState<AgentModelRole>(initial?.model_role ?? 'CHAT')
  const [temperature, setTemperature] = useState<number>(initial?.temperature ?? 0.5)
  const [isActive, setIsActive] = useState(initial?.is_active ?? false)

  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleGeneratePrompt() {
    if (!name.trim()) {
      setError('Define primero el nombre del agente para generar el prompt.')
      return
    }
    setError(null)
    setIsGenerating(true)
    try {
      const r = await apiClient.post<{ instructions: string }>(
        '/api/v1/agents/_helpers/generate-prompt',
        {
          name,
          description: description ?? '',
          // Scope is preserved on the row but no longer edited from the UI;
          // pass through whatever the agent already had so the meta-prompt
          // can still benefit from it when present.
          semantic_types: initial?.scope?.semantic_types ?? [],
          current_instructions: instructions,
        },
      )
      if (r.error || !r.data) throw new Error(r.error || 'No data')
      setInstructions(r.data.instructions)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsGenerating(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSaving(true)
    try {
      if (mode === 'create') {
        // Scope intentionally omitted — backend defaults to {} (no filters,
        // agent sees whole corpus). Power users can populate it via API
        // directly; UI surface is kept minimal per admin request.
        const payload: AgentCreatePayload = {
          name,
          slug,
          description: description || null,
          icon,
          color,
          persona: { style, language, instructions },
          is_active: isActive,
          model_role: modelRole,
          temperature,
        }
        const r = await agentsService.create(payload)
        if (r.error || !r.data) throw new Error(r.error || 'create failed')
        router.push('/admin/agents')
      } else if (initial) {
        // On update we deliberately do NOT send scope so we don't clobber
        // a value the admin might have set via API.
        const payload: AgentUpdatePayload = {
          name,
          description: description || null,
          icon,
          color,
          persona: { style, language, instructions },
          is_active: isActive,
          model_role: modelRole,
          temperature,
        }
        const r = await agentsService.update(initial.id, payload)
        if (r.error || !r.data) throw new Error(r.error || 'update failed')
        router.push('/admin/agents')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsSaving(false)
    }
  }

  async function handleDelete() {
    if (!initial || !confirm(`¿Eliminar agente ${initial.slug}?`)) return
    setError(null)
    setIsDeleting(true)
    try {
      const r = await agentsService.delete(initial.id)
      if (r.error) throw new Error(r.error)
      router.push('/admin/agents')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsDeleting(false)
    }
  }

  async function handleDuplicate() {
    if (!initial) return
    setError(null)
    setIsSaving(true)
    try {
      const r = await agentsService.duplicate(initial.id)
      if (r.error || !r.data) throw new Error(r.error || 'duplicate failed')
      router.push(`/admin/agents/${r.data.id}/edit`)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <div className="text-sm text-red-700 bg-red-50 border border-red-200 px-3 py-2 rounded">
          {error}
        </div>
      )}

      {/* Identidad */}
      <Card>
        <CardHeader>
          <CardTitle>Identidad</CardTitle>
          <CardDescription>Nombre visible, slug para mención y aspecto.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="agent-name">Nombre</Label>
            <Input
              id="agent-name"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (mode === 'create' && !slug) setSlug(autoSlug(e.target.value))
              }}
              required
              maxLength={100}
              placeholder="Contabilidad"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="agent-slug">
              Slug
              <span className="text-xs text-muted-foreground font-normal ml-2">
                lowercase, sin espacios — usado como <code className="px-1 rounded bg-muted">@&lt;slug&gt;</code> en el chat
              </span>
            </Label>
            <Input
              id="agent-slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              required
              pattern="^[a-z][a-z0-9_]{1,49}$"
              disabled={mode === 'edit'}
              className="font-mono"
              placeholder="contabilidad"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="agent-description">Descripción</Label>
            <Textarea
              id="agent-description"
              value={description ?? ''}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Análisis de facturas, pagos y conciliaciones."
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="agent-color">Color</Label>
              <Select value={color} onValueChange={setColor}>
                <SelectTrigger id="agent-color">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {COLOR_OPTIONS.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="agent-icon">
                Icon
                <span className="text-xs text-muted-foreground font-normal ml-2">
                  (Tabler component name)
                </span>
              </Label>
              <Input
                id="agent-icon"
                value={icon}
                onChange={(e) => setIcon(e.target.value)}
                className="font-mono"
                placeholder="IconRobot"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Persona */}
      <Card>
        <CardHeader>
          <CardTitle>Persona</CardTitle>
          <CardDescription>
            Las instrucciones se publican en Langfuse como <code className="px-1 rounded bg-muted text-xs">agent_&lt;slug&gt;_persona</code> al guardar.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="agent-instructions">Instructions (system prompt)</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleGeneratePrompt}
                disabled={isGenerating || !name.trim()}
                title={
                  !name.trim()
                    ? 'Define primero el nombre del agente'
                    : instructions.trim()
                      ? 'Mejorar el prompt actual con IA'
                      : 'Generar prompt desde cero con IA'
                }
              >
                {isGenerating ? (
                  <IconLoader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <IconWand className="h-4 w-4 mr-1" />
                )}
                {isGenerating
                  ? 'Generando…'
                  : instructions.trim()
                    ? 'Mejorar con IA'
                    : 'Generar con IA'}
              </Button>
            </div>
            <Textarea
              id="agent-instructions"
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={6}
              className="font-mono text-sm"
              placeholder="Eres el asistente de Contabilidad. Cita siempre la factura origen."
              disabled={isGenerating}
            />
            <p className="text-xs text-muted-foreground">
              El botón usa el modelo CHAT con un meta-prompt. Si hay texto, lo mejora; si está vacío, lo genera desde cero a partir de nombre, descripción y semantic_types.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="agent-style">Estilo</Label>
              <Select value={style} onValueChange={(v) => setStyle(v as typeof style)}>
                <SelectTrigger id="agent-style">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="concise">Conciso</SelectItem>
                  <SelectItem value="detailed">Detallado</SelectItem>
                  <SelectItem value="conversational">Conversacional</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="agent-language">Idioma</Label>
              <Select value={language} onValueChange={(v) => setLanguage(v as typeof language)}>
                <SelectTrigger id="agent-language">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="es">Español</SelectItem>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="auto">Auto</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Runtime */}
      <Card>
        <CardHeader>
          <CardTitle>Runtime</CardTitle>
          <CardDescription>Modelo y comportamiento.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="agent-model-role">Modelo</Label>
              <Select
                value={modelRole}
                onValueChange={(v) => setModelRole(v as AgentModelRole)}
              >
                <SelectTrigger id="agent-model-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="CHAT">CHAT — alta calidad</SelectItem>
                  <SelectItem value="PLANNER">PLANNER — rápido</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="agent-temperature">
                Temperature
                <span className="ml-2 font-mono text-xs text-muted-foreground">
                  {temperature.toFixed(2)}
                </span>
              </Label>
              <Input
                id="agent-temperature"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={temperature}
                onChange={(e) => setTemperature(Number(e.target.value))}
                className="cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-muted-foreground -mt-1 px-0.5">
                <span>0 — determinista</span>
                <span>1 — creativo</span>
              </div>
            </div>
          </div>

          <Separator />

          <div className="flex items-center justify-between">
            <div>
              <Label htmlFor="agent-is-active" className="cursor-pointer">
                Activo
              </Label>
              <p className="text-xs text-muted-foreground">
                Cuando se activa, todos los usuarios autenticados ven y pueden invocar este agente.
              </p>
            </div>
            <Switch
              id="agent-is-active"
              checked={isActive}
              onCheckedChange={setIsActive}
              disabled={initial?.is_seed && initial.is_active}
            />
          </div>
          {initial?.is_seed && (
            <p className="text-xs text-muted-foreground">
              Este agente es <strong>seed</strong>: no se puede desactivar ni eliminar.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex items-center gap-2 sticky bottom-0 bg-background py-3 border-t">
        <Button type="submit" disabled={isSaving}>
          <IconDeviceFloppy className="h-4 w-4 mr-1" />
          {isSaving ? 'Guardando…' : mode === 'create' ? 'Crear agente' : 'Guardar cambios'}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => router.push('/admin/agents')}
        >
          <IconX className="h-4 w-4 mr-1" />
          Cancelar
        </Button>
        {mode === 'edit' && initial && (
          <>
            <div className="ml-auto flex items-center gap-2">
              <Button type="button" variant="outline" onClick={handleDuplicate} disabled={isSaving}>
                <IconCopy className="h-4 w-4 mr-1" />
                Duplicar
              </Button>
              <Button
                type="button"
                variant="destructive"
                onClick={handleDelete}
                disabled={isDeleting || initial.is_seed}
                title={initial.is_seed ? 'Los agentes seed no se pueden eliminar' : ''}
              >
                <IconTrash className="h-4 w-4 mr-1" />
                {isDeleting ? 'Eliminando…' : 'Eliminar'}
              </Button>
            </div>
          </>
        )}
      </div>
    </form>
  )
}

'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { agentsService } from '@/lib/services/agents.service'
import type { Agent, AgentCreatePayload, AgentUpdatePayload, AgentModelRole } from '@/lib/types/agent'

interface AgentBuilderFormProps {
  initial?: Agent
  mode: 'create' | 'edit'
}

const COLOR_OPTIONS = ['blue', 'green', 'orange', 'purple', 'red', 'pink', 'indigo']

function autoSlug(name: string): string {
  return name.toLowerCase()
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
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
  const [language, setLanguage] = useState<Agent['persona']['language']>(initial?.persona?.language ?? 'es')
  const [semanticTypes, setSemanticTypes] = useState((initial?.scope?.semantic_types ?? []).join(', '))
  const [modelRole, setModelRole] = useState<AgentModelRole>(initial?.model_role ?? 'CHAT')
  const [temperature, setTemperature] = useState<number>(initial?.temperature ?? 0.5)
  const [isActive, setIsActive] = useState(initial?.is_active ?? false)

  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSaving(true)
    try {
      const scope = {
        semantic_types: semanticTypes.split(',').map((s) => s.trim()).filter(Boolean),
      }
      if (mode === 'create') {
        const payload: AgentCreatePayload = {
          name, slug, description: description || null, icon, color,
          persona: { style, language, instructions },
          scope,
          is_active: isActive,
          model_role: modelRole,
          temperature,
        }
        const r = await agentsService.create(payload)
        if (r.error || !r.data) throw new Error(r.error || 'create failed')
        router.push('/admin/agents')
      } else if (initial) {
        const payload: AgentUpdatePayload = {
          name, description: description || null, icon, color,
          persona: { style, language, instructions },
          scope,
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
    <form onSubmit={handleSubmit} className="space-y-6 max-w-3xl">
      {error && <div className="text-sm text-red-700 bg-red-50 border border-red-200 px-3 py-2 rounded">{error}</div>}

      <fieldset className="border border-gray-200 rounded p-4 space-y-3">
        <legend className="px-2 text-sm font-semibold">Identidad</legend>
        <div>
          <label className="block text-sm mb-1">Nombre</label>
          <input
            value={name}
            onChange={(e) => {
              setName(e.target.value)
              if (mode === 'create' && !slug) setSlug(autoSlug(e.target.value))
            }}
            required maxLength={100}
            className="w-full border rounded px-3 py-1.5"
          />
        </div>
        <div>
          <label className="block text-sm mb-1">Slug (lowercase, sin espacios)</label>
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required pattern="^[a-z][a-z0-9_]{1,49}$"
            disabled={mode === 'edit'}
            className="w-full border rounded px-3 py-1.5 font-mono disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm mb-1">Descripción</label>
          <textarea
            value={description ?? ''} onChange={(e) => setDescription(e.target.value)}
            rows={2} className="w-full border rounded px-3 py-1.5"
          />
        </div>
        <div className="flex gap-3">
          <div>
            <label className="block text-sm mb-1">Color</label>
            <select value={color} onChange={(e) => setColor(e.target.value)} className="border rounded px-2 py-1.5">
              {COLOR_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm mb-1">Icon (Tabler name)</label>
            <input value={icon} onChange={(e) => setIcon(e.target.value)} className="border rounded px-3 py-1.5 font-mono" />
          </div>
        </div>
      </fieldset>

      <fieldset className="border border-gray-200 rounded p-4 space-y-3">
        <legend className="px-2 text-sm font-semibold">Persona</legend>
        <div>
          <label className="block text-sm mb-1">Instructions (system prompt)</label>
          <textarea
            value={instructions} onChange={(e) => setInstructions(e.target.value)}
            rows={6} className="w-full border rounded px-3 py-1.5 font-mono text-sm"
            placeholder="Eres el asistente de Contabilidad. Cita siempre la factura origen."
          />
        </div>
        <div className="flex gap-3">
          <div>
            <label className="block text-sm mb-1">Estilo</label>
            <select value={style} onChange={(e) => setStyle(e.target.value as Agent['persona']['style'])} className="border rounded px-2 py-1.5">
              <option value="concise">Conciso</option>
              <option value="detailed">Detallado</option>
              <option value="conversational">Conversacional</option>
            </select>
          </div>
          <div>
            <label className="block text-sm mb-1">Idioma</label>
            <select value={language} onChange={(e) => setLanguage(e.target.value as Agent['persona']['language'])} className="border rounded px-2 py-1.5">
              <option value="es">Español</option>
              <option value="en">English</option>
              <option value="auto">Auto</option>
            </select>
          </div>
        </div>
      </fieldset>

      <fieldset className="border border-gray-200 rounded p-4 space-y-3">
        <legend className="px-2 text-sm font-semibold">Scope</legend>
        <div>
          <label className="block text-sm mb-1">Semantic types (separados por coma)</label>
          <input
            value={semanticTypes} onChange={(e) => setSemanticTypes(e.target.value)}
            placeholder="factura, contrato, sentencia"
            className="w-full border rounded px-3 py-1.5 font-mono text-sm"
          />
          <p className="text-xs text-gray-500 mt-1">v1: solo se expone semantic_types desde la UI. Otros filtros del scope (folders, dates, quality_min) se pueden añadir editando la fila por API.</p>
        </div>
      </fieldset>

      <fieldset className="border border-gray-200 rounded p-4 space-y-3">
        <legend className="px-2 text-sm font-semibold">Runtime</legend>
        <div className="flex gap-3 items-end">
          <div>
            <label className="block text-sm mb-1">Modelo</label>
            <select value={modelRole} onChange={(e) => setModelRole(e.target.value as AgentModelRole)} className="border rounded px-2 py-1.5">
              <option value="CHAT">CHAT (calidad)</option>
              <option value="PLANNER">PLANNER (rápido)</option>
            </select>
          </div>
          <div>
            <label className="block text-sm mb-1">Temperature: {temperature.toFixed(2)}</label>
            <input
              type="range" min={0} max={2} step={0.05}
              value={temperature} onChange={(e) => setTemperature(Number(e.target.value))}
              className="w-48"
            />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
          Activo (visible para todos los usuarios)
        </label>
      </fieldset>

      <div className="flex items-center gap-3">
        <button type="submit" disabled={isSaving} className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50">
          {isSaving ? 'Guardando…' : (mode === 'create' ? 'Crear' : 'Guardar')}
        </button>
        <button type="button" onClick={() => router.push('/admin/agents')} className="px-4 py-2 border rounded">
          Cancelar
        </button>
        {mode === 'edit' && initial && (
          <>
            <button type="button" onClick={handleDuplicate} className="ml-auto px-3 py-2 border rounded text-sm">
              Duplicar
            </button>
            <button
              type="button" onClick={handleDelete} disabled={isDeleting || initial.is_seed}
              title={initial.is_seed ? 'No se puede eliminar un agente seed' : ''}
              className="px-3 py-2 border border-red-300 text-red-700 rounded text-sm disabled:opacity-50"
            >
              {isDeleting ? 'Eliminando…' : 'Eliminar'}
            </button>
          </>
        )}
      </div>
    </form>
  )
}

'use client'

import { ENTITY_TYPE_COLORS, EDGE_NAMESPACE_STYLES } from './explainability-theme'

const ENTITY_TYPES: Array<{ key: string; label: string }> = [
  { key: 'document', label: 'Documento' },
  { key: 'person', label: 'Persona' },
  { key: 'law', label: 'Ley' },
  { key: 'organization', label: 'Organización' },
  { key: 'contract', label: 'Contrato' },
  { key: 'amount', label: 'Importe' },
  { key: 'date', label: 'Fecha' },
  { key: 'place', label: 'Lugar' },
  { key: 'topic', label: 'Tema' },
  { key: 'other', label: 'Otro' },
]

const EDGE_TYPES: Array<{ key: string; label: string }> = [
  { key: 'core', label: 'General' },
  { key: 'legal', label: 'Legal' },
]

export function ExplainabilityLegend() {
  return (
    <div className="absolute bottom-4 left-4 z-10 rounded-lg border border-white/[0.06] bg-[#07090f]/90 backdrop-blur-sm px-3 py-2.5 shadow-lg">
      {/* Entity types */}
      <p className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-2">
        Entidades
      </p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {ENTITY_TYPES.map(({ key, label }) => (
          <div key={key} className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full shrink-0"
              style={{
                backgroundColor: ENTITY_TYPE_COLORS[key],
                boxShadow: `0 0 6px ${ENTITY_TYPE_COLORS[key]}60`,
              }}
            />
            <span className="text-[10px] text-slate-400">{label}</span>
          </div>
        ))}
      </div>

      {/* Edge namespaces */}
      <div className="mt-2.5 pt-2 border-t border-white/[0.06]">
        <p className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1.5">
          Relaciones
        </p>
        <div className="space-y-1">
          {EDGE_TYPES.map(({ key, label }) => {
            const style = EDGE_NAMESPACE_STYLES[key]
            return (
              <div key={key} className="flex items-center gap-1.5">
                <span
                  className="h-px w-4 shrink-0"
                  style={{
                    backgroundColor: style.color,
                    height: style.width,
                    opacity: style.opacity,
                  }}
                />
                <span className="text-[10px] text-slate-400">{label}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Size hint */}
      <div className="mt-2 pt-1.5 border-t border-white/[0.06]">
        <p className="text-[9px] text-slate-600 italic">
          Tamaño = n° conexiones
        </p>
      </div>
    </div>
  )
}

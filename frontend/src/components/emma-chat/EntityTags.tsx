'use client'

import { useRouter } from 'next/navigation'
import { ENTITY_TYPE_COLORS } from '@/app/knowledge-graph/components/explainability-theme'

export interface EntityTag {
  uri: string
  label: string
  type: string
}

interface EntityTagsProps {
  entities: EntityTag[]
}

export function EntityTags({ entities }: EntityTagsProps) {
  const router = useRouter()

  if (!entities.length) return null

  function navigateToGraph(uri: string) {
    const encoded = encodeURIComponent(uri)
    router.push(`/knowledge-graph?entity=${encoded}`)
  }

  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {entities.map((entity) => (
        <button
          key={entity.uri}
          onClick={() => navigateToGraph(entity.uri)}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs
                     bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20
                     border border-cyan-500/20 transition-colors"
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: ENTITY_TYPE_COLORS[entity.type] ?? '#6b7280' }}
          />
          {entity.label}
        </button>
      ))}
    </div>
  )
}

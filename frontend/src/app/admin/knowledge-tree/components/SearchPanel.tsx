"use client"

import { useState, useRef } from "react"
import { IconSearch, IconX, IconLoader2, IconUser, IconFileText, IconScale, IconCategory } from "@tabler/icons-react"
import type { EntitySearchResult } from "@/lib/services/knowledge-tree.service"
import { getNodeKind, type NodeKind } from "@/lib/services/knowledge-tree.service"

const KIND_ICONS: Record<NodeKind, typeof IconFileText> = {
  document: IconFileText,
  person: IconUser,
  law: IconScale,
  entity_type: IconCategory,
  memory: IconCategory,
  unknown: IconCategory,
}

interface SearchPanelProps {
  onSelectEntity: (entity: EntitySearchResult) => void
  onSearch: (query: string) => Promise<EntitySearchResult[]>
  isSearching?: boolean
}

export function SearchPanel({ onSelectEntity, onSearch, isSearching = false }: SearchPanelProps) {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<EntitySearchResult[]>([])
  const [hasSearched, setHasSearched] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleSearch = async () => {
    const q = query.trim()
    if (!q) return
    setHasSearched(true)
    const data = await onSearch(q)
    setResults(data)
  }

  const handleClear = () => {
    setQuery("")
    setResults([])
    setHasSearched(false)
    inputRef.current?.focus()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch()
    if (e.key === "Escape") handleClear()
  }

  return (
    <div className="kt-search-panel">
      {/* Search input */}
      <div className="relative">
        <IconSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500 pointer-events-none" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Buscar entidad..."
          className="w-full h-8 rounded-lg bg-white/[0.04] border border-white/[0.06] pl-8 pr-8 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500/30 focus:bg-white/[0.06] transition-colors"
        />
        {query && (
          <button onClick={handleClear} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-300 transition-colors">
            <IconX className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Loading */}
      {isSearching && (
        <div className="flex items-center justify-center py-4">
          <IconLoader2 className="h-4 w-4 animate-spin text-cyan-500/60" />
        </div>
      )}

      {/* Results */}
      {!isSearching && results.length > 0 && (
        <div className="mt-2 space-y-0.5 max-h-[300px] overflow-y-auto scrollbar-thin">
          <div className="text-[10px] text-slate-600 uppercase tracking-widest px-1 mb-1">
            {results.length} resultado{results.length !== 1 ? "s" : ""}
          </div>
          {results.map((r) => {
            const kind = getNodeKind(r as any)
            const Icon = KIND_ICONS[kind]
            return (
              <button
                key={r.id}
                onClick={() => onSelectEntity(r)}
                className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left hover:bg-white/[0.04] transition-colors group"
              >
                <Icon className="h-3.5 w-3.5 text-slate-500 group-hover:text-cyan-400 transition-colors shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-slate-300 truncate group-hover:text-white transition-colors">
                    {r.name}
                  </div>
                  <div className="text-[10px] text-slate-600 truncate">
                    {r.label}
                    {r.properties.domain ? ` · ${r.properties.domain}` : ""}
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      )}

      {/* No results */}
      {!isSearching && hasSearched && results.length === 0 && (
        <div className="text-center py-4 text-xs text-slate-600">
          Sin resultados para "{query}"
        </div>
      )}
    </div>
  )
}

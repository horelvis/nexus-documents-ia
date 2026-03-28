'use client'

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  ENTITY_TYPE_COLORS,
} from './explainability-theme'
import type {
  TrustGraphNode,
  TrustGraphEdge,
  EntityProperty,
  Contradiction,
} from '@/lib/services/knowledge-tree.service'

interface NodeDetailsDrawerProps {
  node: TrustGraphNode | null
  edges: TrustGraphEdge[]
  allNodes: TrustGraphNode[]
  properties: EntityProperty[]
  contradictions: Contradiction[]
  onClose: () => void
  onNavigate?: (nodeUri: string) => void
}

export function NodeDetailsDrawer({
  node,
  edges,
  allNodes,
  properties,
  contradictions,
  onClose,
  onNavigate,
}: NodeDetailsDrawerProps) {
  if (!node) return null

  const nodeColor = ENTITY_TYPE_COLORS[node.type] ?? '#6b7280'
  const nodeMap = new Map(allNodes.map((n) => [n.id, n]))

  // Edges connected to this node
  const relatedEdges = edges.filter(
    (e) => {
      const sourceId = typeof e.source === 'string' ? e.source : (e.source as any)?.id
      const targetId = typeof e.target === 'string' ? e.target : (e.target as any)?.id
      return sourceId === node.id || targetId === node.id
    },
  )

  // Node contradictions
  const nodeContradictions = contradictions.filter((c) => c.subject === node.id)

  return (
    <Sheet open={!!node} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-[400px] sm:w-[480px] overflow-y-auto">
        <SheetHeader className="pb-4">
          <div className="flex items-center gap-2">
            <span
              className="h-3 w-3 rounded-full"
              style={{ backgroundColor: nodeColor }}
            />
            <SheetTitle className="text-lg">{node.label}</SheetTitle>
            <Badge variant="outline" className="text-xs">
              {node.type}
            </Badge>
          </div>
          {node.definition && (
            <p className="text-sm text-muted-foreground mt-1">{node.definition}</p>
          )}
        </SheetHeader>

        <Tabs defaultValue="relationships" className="mt-2">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="relationships">
              Relaciones ({relatedEdges.length})
            </TabsTrigger>
            <TabsTrigger value="properties">
              Propiedades ({properties.length})
            </TabsTrigger>
            <TabsTrigger value="contradictions">
              Conflictos ({nodeContradictions.length})
            </TabsTrigger>
          </TabsList>

          {/* Relationships Tab */}
          <TabsContent value="relationships" className="mt-3 space-y-1">
            {relatedEdges.length === 0 && (
              <p className="text-sm text-muted-foreground">Sin relaciones</p>
            )}
            {relatedEdges.map((edge) => {
              const sourceId = typeof edge.source === 'string' ? edge.source : (edge.source as any)?.id
              const targetId = typeof edge.target === 'string' ? edge.target : (edge.target as any)?.id
              const isOutgoing = sourceId === node.id
              const otherUri = isOutgoing ? targetId : sourceId
              const otherNode = nodeMap.get(otherUri)
              const otherLabel = otherNode?.label ?? otherUri?.split('/').pop()?.replace(/-/g, ' ') ?? '?'

              return (
                <div
                  key={edge.id}
                  className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-white/5 cursor-pointer"
                  onClick={() => onNavigate?.(otherUri)}
                >
                  <span className="text-xs text-muted-foreground w-4">
                    {isOutgoing ? '→' : '←'}
                  </span>
                  <Badge variant="outline" className="text-[10px] font-mono">
                    {edge.predicate}
                  </Badge>
                  <span className="flex-1 text-sm truncate">{otherLabel}</span>
                  {otherNode && (
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: ENTITY_TYPE_COLORS[otherNode.type] ?? '#6b7280' }}
                    />
                  )}
                </div>
              )
            })}
          </TabsContent>

          {/* Properties Tab */}
          <TabsContent value="properties" className="mt-3 space-y-1">
            {properties.length === 0 && (
              <p className="text-sm text-muted-foreground">Sin propiedades</p>
            )}
            {properties.map((prop, i) => (
              <div key={`${prop.predicate}-${i}`} className="flex items-start gap-2 py-1.5 px-2">
                <Badge variant="outline" className="text-[10px] font-mono flex-shrink-0 mt-0.5">
                  {prop.namespace}/{prop.predicate}
                </Badge>
                <span className="text-sm flex-1 break-words">{prop.value}</span>
              </div>
            ))}
          </TabsContent>

          {/* Contradictions Tab */}
          <TabsContent value="contradictions" className="mt-3 space-y-2">
            {nodeContradictions.length === 0 && (
              <p className="text-sm text-muted-foreground">Sin conflictos detectados</p>
            )}
            {nodeContradictions.map((c, i) => (
              <div key={`contradiction-${i}`} className="border border-rose-500/30 rounded-md p-3 bg-rose-500/5">
                <div className="text-xs font-mono text-rose-400 mb-2">{c.predicate}</div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <div className="text-muted-foreground text-xs mb-1">Valor A</div>
                    <div>{c.valueA}</div>
                    {c.sourceA && <div className="text-xs text-muted-foreground mt-1">{c.sourceA}</div>}
                  </div>
                  <div>
                    <div className="text-muted-foreground text-xs mb-1">Valor B</div>
                    <div>{c.valueB}</div>
                    {c.sourceB && <div className="text-xs text-muted-foreground mt-1">{c.sourceB}</div>}
                  </div>
                </div>
              </div>
            ))}
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  )
}

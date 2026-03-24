'use client'

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { NODE_COLORS, type ExplainNode, type ExplainLink } from './explainability-theme'

interface NodeDetailsDrawerProps {
  node: ExplainNode | null
  edges: ExplainLink[]
  allNodes: ExplainNode[]
  onClose: () => void
  onNavigate?: (nodeId: string) => void
}

const NODE_TYPE_LABELS: Record<string, string> = {
  entity: 'Entity',
  document: 'Document',
  claim: 'Claim',
  law: 'Law',
  contradiction: 'Contradiction',
}

function resolveNodeId(ref: string | ExplainNode): string {
  return typeof ref === 'string' ? ref : ref.id
}

export function NodeDetailsDrawer({
  node,
  edges,
  allNodes,
  onClose,
  onNavigate,
}: NodeDetailsDrawerProps) {
  if (!node) return null

  const nodeColor = NODE_COLORS[node.type] ?? '#94a3b8'

  const relatedEdges = edges.filter(
    (e) => resolveNodeId(e.source) === node.id || resolveNodeId(e.target) === node.id,
  )

  const nodeMap = new Map(allNodes.map((n) => [n.id, n]))

  const confidence =
    node.type === 'claim' && typeof node.properties.confidence === 'number'
      ? (node.properties.confidence as number)
      : null

  const excerpt =
    node.type === 'claim' && typeof node.properties.excerpt === 'string'
      ? (node.properties.excerpt as string)
      : null

  const properties = Object.entries(node.properties).filter(
    ([k]) => k !== 'confidence' && k !== 'excerpt',
  )

  return (
    <Sheet open={!!node} onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent side="right" className="w-80 sm:max-w-sm overflow-y-auto">
        <SheetHeader className="pb-2">
          <div className="flex items-center gap-2">
            <Badge
              className="border-0 text-white text-xs"
              style={{ backgroundColor: nodeColor }}
            >
              {NODE_TYPE_LABELS[node.type] ?? node.type}
            </Badge>
          </div>
          <SheetTitle className="text-base leading-snug break-words mt-1">
            {node.label}
          </SheetTitle>
        </SheetHeader>

        <div className="px-4 pb-4 space-y-5">
          {/* Claim-specific: excerpt + confidence */}
          {node.type === 'claim' && (excerpt || confidence !== null) && (
            <div className="space-y-2">
              {excerpt && (
                <blockquote className="border-l-2 pl-3 text-sm text-muted-foreground italic leading-relaxed" style={{ borderColor: nodeColor }}>
                  {excerpt}
                </blockquote>
              )}
              {confidence !== null && (
                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Confidence</span>
                    <span>{Math.round(confidence * 100)}%</span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${confidence * 100}%`, backgroundColor: nodeColor }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Properties table */}
          {properties.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                Properties
              </p>
              <div className="rounded-md border overflow-hidden">
                <table className="w-full text-xs">
                  <tbody>
                    {properties.map(([key, value], i) => (
                      <tr key={key} className={i % 2 === 0 ? 'bg-muted/40' : ''}>
                        <td className="px-2 py-1.5 font-medium text-muted-foreground capitalize w-1/3 break-words">
                          {key.replace(/_/g, ' ')}
                        </td>
                        <td className="px-2 py-1.5 text-foreground break-words">
                          {value === null || value === undefined
                            ? '—'
                            : typeof value === 'object'
                            ? JSON.stringify(value)
                            : String(value)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Relationships */}
          {relatedEdges.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                Relationships ({relatedEdges.length})
              </p>
              <div className="space-y-1">
                {relatedEdges.map((edge) => {
                  const isSource = resolveNodeId(edge.source) === node.id
                  const otherId = isSource
                    ? resolveNodeId(edge.target)
                    : resolveNodeId(edge.source)
                  const otherNode = nodeMap.get(otherId)
                  const otherColor = otherNode ? NODE_COLORS[otherNode.type] ?? '#94a3b8' : '#94a3b8'

                  return (
                    <button
                      key={edge.id}
                      onClick={() => onNavigate?.(otherId)}
                      className="w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-accent transition-colors group"
                    >
                      <span className="shrink-0 text-muted-foreground">
                        {isSource ? '→' : '←'}
                      </span>
                      <Badge
                        variant="outline"
                        className="shrink-0 text-[10px] px-1 py-0 h-4"
                      >
                        {edge.type}
                      </Badge>
                      <span className="truncate flex-1 text-foreground group-hover:text-accent-foreground">
                        {otherNode?.label ?? otherId}
                      </span>
                      {otherNode && (
                        <span
                          className="ml-auto shrink-0 h-2 w-2 rounded-full"
                          style={{ backgroundColor: otherColor }}
                        />
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Node ID */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
              ID
            </p>
            <p className="text-xs font-mono text-muted-foreground break-all">{node.id}</p>
          </div>

          <Button variant="outline" size="sm" className="w-full" onClick={onClose}>
            Close
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}

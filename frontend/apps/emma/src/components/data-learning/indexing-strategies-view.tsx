'use client'

/**
 * Indexing Strategies View Component
 *
 * Displays and manages connector indexing strategies:
 * - Chunking configuration per document type
 * - Embedding field selection
 * - Entity extraction settings
 */

import { useState, useEffect } from 'react'
import {
  IconLoader2,
  IconStack2,
  IconToggleLeft,
  IconToggleRight,
  IconChevronDown,
  IconChevronRight,
} from '@tabler/icons-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Badge,
  Button,
  Switch,
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@nexus/shared/ui'
import {
  dataLearningService,
  ConnectorIndexingStrategy,
  chunkingTypeLabels,
} from '@/lib/services/data-learning.service'

interface IndexingStrategiesViewProps {
  connectorId: string
  onUpdate?: () => void
}

export function IndexingStrategiesView({ connectorId, onUpdate }: IndexingStrategiesViewProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [strategies, setStrategies] = useState<ConnectorIndexingStrategy[]>([])
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = await dataLearningService.getIndexingStrategies(connectorId)
      if (result.data) {
        setStrategies(result.data)
      } else if (result.error) {
        setError(result.error)
      }
    } catch (err: any) {
      setError(err.message || 'Error al cargar estrategias')
    } finally {
      setIsLoading(false)
    }
  }

  const handleToggleActive = async (strategyId: string, isActive: boolean) => {
    setActionLoading(strategyId)
    try {
      const result = await dataLearningService.toggleStrategy(connectorId, strategyId, isActive)
      if (result.data) {
        setStrategies(prev => prev.map(s => s.id === strategyId ? result.data! : s))
        onUpdate?.()
      } else if (result.error) {
        setError(result.error)
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setActionLoading(null)
    }
  }

  useEffect(() => {
    loadData()
  }, [connectorId])

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex items-center justify-center">
            <IconLoader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-12">
          <p className="text-center text-destructive">{error}</p>
        </CardContent>
      </Card>
    )
  }

  if (strategies.length === 0) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="text-center">
            <IconStack2 className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground mb-2">
              No hay estrategias de indexación
            </p>
            <p className="text-sm text-muted-foreground">
              Ejecuta una optimización de estrategias para generarlas
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <IconStack2 className="h-5 w-5" />
          Estrategias de Indexación ({strategies.length})
        </CardTitle>
        <CardDescription>
          Configuraciones de chunking y embedding por tipo de documento
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Accordion type="multiple" className="w-full">
          {strategies.map((strategy) => (
            <AccordionItem key={strategy.id} value={strategy.id}>
              <AccordionTrigger className="hover:no-underline">
                <div className="flex items-center gap-3 flex-1">
                  <Switch
                    checked={strategy.is_active}
                    onCheckedChange={(checked) => {
                      // Prevent accordion toggle
                      handleToggleActive(strategy.id, checked)
                    }}
                    onClick={(e) => e.stopPropagation()}
                    disabled={actionLoading === strategy.id}
                  />
                  <div className="flex items-center gap-2">
                    {strategy.document_type ? (
                      <code className="text-sm bg-muted px-2 py-0.5 rounded">
                        {strategy.document_type}
                      </code>
                    ) : strategy.mime_type_pattern ? (
                      <code className="text-sm bg-muted px-2 py-0.5 rounded">
                        {strategy.mime_type_pattern}
                      </code>
                    ) : (
                      <span className="text-sm text-muted-foreground">Por defecto</span>
                    )}
                    <Badge variant={strategy.is_active ? 'default' : 'secondary'}>
                      {chunkingTypeLabels[strategy.chunking_type]}
                    </Badge>
                    <Badge variant="outline">
                      Prioridad: {strategy.priority}
                    </Badge>
                  </div>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="grid gap-4 pl-12 pt-2">
                  {/* Chunking Configuration */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h4 className="text-sm font-medium mb-2">Configuración de Chunking</h4>
                      <div className="space-y-1 text-sm">
                        <div>
                          <span className="text-muted-foreground">Tipo:</span>{' '}
                          {chunkingTypeLabels[strategy.chunking_type]}
                        </div>
                        {strategy.chunking_config.target_chunk_size && (
                          <div>
                            <span className="text-muted-foreground">Tamaño objetivo:</span>{' '}
                            {strategy.chunking_config.target_chunk_size} tokens
                          </div>
                        )}
                        {strategy.chunking_config.overlap && (
                          <div>
                            <span className="text-muted-foreground">Overlap:</span>{' '}
                            {strategy.chunking_config.overlap} tokens
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Embedding Fields */}
                    <div>
                      <h4 className="text-sm font-medium mb-2">Campos de Embedding</h4>
                      <div className="flex flex-wrap gap-1">
                        {strategy.embedding_fields.map((field) => (
                          <Badge key={field} variant="secondary" className="text-xs">
                            {field}
                            {strategy.embedding_weights?.[field] && (
                              <span className="ml-1 opacity-60">
                                ({strategy.embedding_weights[field].toFixed(1)})
                              </span>
                            )}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Entity Extraction */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h4 className="text-sm font-medium mb-2">Extracción de Entidades</h4>
                      <div className="space-y-1 text-sm">
                        <div>
                          <span className="text-muted-foreground">Habilitado:</span>{' '}
                          {strategy.extract_entities ? 'Sí' : 'No'}
                        </div>
                        {strategy.entity_types && strategy.entity_types.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {strategy.entity_types.map((type) => (
                              <Badge key={type} variant="outline" className="text-xs">
                                {type}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    <div>
                      <h4 className="text-sm font-medium mb-2">Knowledge Graph</h4>
                      <div className="text-sm">
                        <span className="text-muted-foreground">Extraer a KG:</span>{' '}
                        {strategy.extract_to_knowledge_graph ? 'Sí' : 'No'}
                      </div>
                    </div>
                  </div>

                  {/* Timestamps */}
                  <div className="text-xs text-muted-foreground pt-2 border-t">
                    Creado: {new Date(strategy.created_at).toLocaleDateString()}
                    {strategy.updated_at && (
                      <> • Actualizado: {new Date(strategy.updated_at).toLocaleDateString()}</>
                    )}
                  </div>
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </CardContent>
    </Card>
  )
}

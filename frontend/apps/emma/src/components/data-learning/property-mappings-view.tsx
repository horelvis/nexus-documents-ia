'use client'

/**
 * Property Mappings View Component
 *
 * Displays and manages learned property mappings:
 * - Source to target field mappings
 * - Search weights and embedding settings
 * - Usage statistics
 */

import { useState, useEffect } from 'react'
import {
  IconLoader2,
  IconAdjustmentsHorizontal,
  IconTrash,
  IconSearch,
  IconSparkles,
  IconFilter,
} from '@tabler/icons-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Badge,
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Input,
  Switch,
} from '@nexus/shared/ui'
import {
  dataLearningService,
  LearnedPropertyMapping,
} from '@/lib/services/data-learning.service'

interface PropertyMappingsViewProps {
  connectorId: string
  onUpdate?: () => void
}

export function PropertyMappingsView({ connectorId, onUpdate }: PropertyMappingsViewProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mappings, setMappings] = useState<LearnedPropertyMapping[]>([])
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = await dataLearningService.getPropertyMappings(connectorId)
      if (result.data) {
        setMappings(result.data)
      } else if (result.error) {
        setError(result.error)
      }
    } catch (err: any) {
      setError(err.message || 'Error al cargar mapeos')
    } finally {
      setIsLoading(false)
    }
  }

  const handleWeightChange = async (mappingId: string, weight: number) => {
    setActionLoading(mappingId)
    try {
      const result = await dataLearningService.updatePropertyMapping(
        connectorId,
        mappingId,
        { search_weight: weight }
      )
      if (result.data) {
        setMappings(prev => prev.map(m => m.id === mappingId ? result.data! : m))
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

  const handleToggleEmbedding = async (mappingId: string, include: boolean) => {
    setActionLoading(mappingId)
    try {
      const result = await dataLearningService.updatePropertyMapping(
        connectorId,
        mappingId,
        { include_in_embedding: include }
      )
      if (result.data) {
        setMappings(prev => prev.map(m => m.id === mappingId ? result.data! : m))
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

  const handleDelete = async (mappingId: string) => {
    if (!confirm('¿Eliminar este mapeo de propiedad?')) return

    setActionLoading(mappingId)
    try {
      const result = await dataLearningService.deletePropertyMapping(connectorId, mappingId)
      if (result.error) {
        setError(result.error)
      } else {
        await loadData()
        onUpdate?.()
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

  if (mappings.length === 0) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="text-center">
            <IconAdjustmentsHorizontal className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground mb-2">
              No hay mapeos de propiedades
            </p>
            <p className="text-sm text-muted-foreground">
              Ejecuta un aprendizaje de propiedades para generar mapeos
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
          <IconAdjustmentsHorizontal className="h-5 w-5" />
          Mapeos de Propiedades ({mappings.length})
        </CardTitle>
        <CardDescription>
          Mapeos de propiedades del conector a campos normalizados para búsqueda
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Propiedad Origen</TableHead>
                <TableHead>Campo Destino</TableHead>
                <TableHead className="w-[120px]">
                  <div className="flex items-center gap-1">
                    <IconSearch className="h-3 w-3" />
                    Peso
                  </div>
                </TableHead>
                <TableHead className="w-[80px]">
                  <div className="flex items-center gap-1">
                    <IconSparkles className="h-3 w-3" />
                    Embed
                  </div>
                </TableHead>
                <TableHead className="w-[60px]">
                  <div className="flex items-center gap-1">
                    <IconFilter className="h-3 w-3" />
                    Filtro
                  </div>
                </TableHead>
                <TableHead className="w-[80px]">Uso</TableHead>
                <TableHead className="w-[60px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mappings.map((mapping) => (
                <TableRow key={mapping.id}>
                  <TableCell>
                    <div>
                      <code className="text-xs bg-muted px-1 rounded">
                        {mapping.source_property}
                      </code>
                      {mapping.source_type && (
                        <div className="text-xs text-muted-foreground mt-1">
                          Tipo: {mapping.source_type}
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <code className="text-xs bg-primary/10 text-primary px-1 rounded">
                      {mapping.target_field}
                    </code>
                  </TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      min={0}
                      max={5}
                      step={0.1}
                      value={mapping.search_weight}
                      onChange={(e) => {
                        const value = parseFloat(e.target.value)
                        if (!isNaN(value) && value >= 0 && value <= 5) {
                          handleWeightChange(mapping.id, value)
                        }
                      }}
                      disabled={actionLoading === mapping.id}
                      className="w-20 h-8 text-xs"
                    />
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={mapping.include_in_embedding}
                      onCheckedChange={(checked) => handleToggleEmbedding(mapping.id, checked)}
                      disabled={actionLoading === mapping.id}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      {mapping.is_filterable && (
                        <Badge variant="secondary" className="text-xs">F</Badge>
                      )}
                      {mapping.is_facetable && (
                        <Badge variant="secondary" className="text-xs">C</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="text-xs text-muted-foreground">
                      {mapping.usage_count}
                      {mapping.learned_from_usage && (
                        <Badge variant="outline" className="ml-1 text-xs">auto</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(mapping.id)}
                      disabled={actionLoading === mapping.id}
                      className="text-destructive hover:text-destructive"
                    >
                      {actionLoading === mapping.id ? (
                        <IconLoader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <IconTrash className="h-4 w-4" />
                      )}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="mt-4 text-xs text-muted-foreground">
          <strong>Leyenda:</strong> F = Filtrable, C = Facetable, auto = Aprendido de uso
        </div>
      </CardContent>
    </Card>
  )
}

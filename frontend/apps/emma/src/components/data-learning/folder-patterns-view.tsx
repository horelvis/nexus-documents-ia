'use client'

/**
 * Folder Patterns View Component
 *
 * Displays and manages learned folder patterns:
 * - Pattern paths with semantic information
 * - Verification status
 * - Example paths
 */

import { useState, useEffect } from 'react'
import {
  IconLoader2,
  IconFolders,
  IconCircleCheck,
  IconAlertCircle,
  IconTrash,
  IconCheck,
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
} from '@nexus/shared/ui'
import {
  dataLearningService,
  LearnedFolderPattern,
} from '@/lib/services/data-learning.service'

interface FolderPatternsViewProps {
  connectorId: string
  onUpdate?: () => void
}

const semanticTypeLabels: Record<string, string> = {
  fixed: 'Fijo',
  site_identifier: 'Sitio',
  classification: 'Clasificación',
  temporal: 'Temporal',
  user: 'Usuario',
  document_type: 'Tipo Doc',
}

export function FolderPatternsView({ connectorId, onUpdate }: FolderPatternsViewProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [patterns, setPatterns] = useState<LearnedFolderPattern[]>([])
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = await dataLearningService.getFolderPatterns(connectorId)
      if (result.data) {
        setPatterns(result.data)
      } else if (result.error) {
        setError(result.error)
      }
    } catch (err: any) {
      setError(err.message || 'Error al cargar patrones')
    } finally {
      setIsLoading(false)
    }
  }

  const handleVerify = async (patternId: string) => {
    setActionLoading(patternId)
    try {
      const result = await dataLearningService.verifyFolderPattern(connectorId, patternId)
      if (result.data) {
        await loadData()
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

  const handleDelete = async (patternId: string) => {
    if (!confirm('¿Eliminar este patrón de carpeta?')) return

    setActionLoading(patternId)
    try {
      const result = await dataLearningService.deleteFolderPattern(connectorId, patternId)
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

  if (patterns.length === 0) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="text-center">
            <IconFolders className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground mb-2">
              No hay patrones de carpeta aprendidos
            </p>
            <p className="text-sm text-muted-foreground">
              Ejecuta un análisis de carpetas para aprender los patrones
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
          <IconFolders className="h-5 w-5" />
          Patrones de Carpeta ({patterns.length})
        </CardTitle>
        <CardDescription>
          Patrones de estructura de carpetas aprendidos para contexto semántico
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {patterns.map((pattern) => (
            <div
              key={pattern.id}
              className="p-4 rounded-lg border bg-card"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <code className="text-sm bg-muted px-2 py-1 rounded">
                      {pattern.path_pattern}
                    </code>
                    {pattern.is_verified ? (
                      <Badge variant="default" className="flex items-center gap-1">
                        <IconCircleCheck className="h-3 w-3" />
                        Verificado
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="flex items-center gap-1">
                        <IconAlertCircle className="h-3 w-3" />
                        Sin verificar
                      </Badge>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-2 mb-3">
                    {Object.entries(pattern.level_semantics).map(([level, semantic]) => (
                      <div key={level} className="text-xs bg-muted/50 px-2 py-1 rounded">
                        <span className="text-muted-foreground">Nivel {level}:</span>{' '}
                        <span className="font-medium">{semantic.name}</span>
                        {' '}
                        <Badge variant="secondary" className="text-xs ml-1">
                          {semanticTypeLabels[semantic.type] || semantic.type}
                        </Badge>
                      </div>
                    ))}
                  </div>

                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span>Coincidencias: {pattern.match_count}</span>
                    <span>Confianza: {(pattern.confidence * 100).toFixed(0)}%</span>
                    {pattern.learned_from_sample_size && (
                      <span>Muestra: {pattern.learned_from_sample_size} docs</span>
                    )}
                  </div>

                  {pattern.example_paths && pattern.example_paths.length > 0 && (
                    <div className="mt-3">
                      <span className="text-xs text-muted-foreground">Ejemplos:</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {pattern.example_paths.slice(0, 3).map((path, idx) => (
                          <code key={idx} className="text-xs bg-muted px-1 rounded truncate max-w-xs">
                            {path}
                          </code>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex gap-1">
                  {!pattern.is_verified && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleVerify(pattern.id)}
                      disabled={actionLoading === pattern.id}
                    >
                      {actionLoading === pattern.id ? (
                        <IconLoader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <IconCheck className="h-4 w-4" />
                      )}
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(pattern.id)}
                    disabled={actionLoading === pattern.id}
                    className="text-destructive hover:text-destructive"
                  >
                    {actionLoading === pattern.id ? (
                      <IconLoader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <IconTrash className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

'use client'

/**
 * Content Model View Component
 *
 * Displays the discovered content model for a connector:
 * - Content types with their properties
 * - Aspects with their properties
 * - Semantic enrichment information
 */

import { useState, useEffect } from 'react'
import {
  IconLoader2,
  IconFileTypography,
  IconStack2,
  IconChevronDown,
  IconChevronRight,
  IconTag,
  IconInfoCircle,
} from '@tabler/icons-react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Badge,
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui'
import {
  dataLearningService,
  ConnectorContentModel,
} from '@/lib/services/data-learning.service'

interface ContentModelViewProps {
  connectorId: string
}

export function ContentModelView({ connectorId }: ContentModelViewProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [contentModel, setContentModel] = useState<ConnectorContentModel | null>(null)

  const loadData = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const result = await dataLearningService.getContentModel(connectorId)
      if (result.data) {
        setContentModel(result.data)
      } else if (result.error) {
        // If no model exists, that's okay - show empty state
        if (result.error.includes('404') || result.error.includes('not found')) {
          setContentModel(null)
        } else {
          setError(result.error)
        }
      }
    } catch (err: any) {
      setError(err.message || 'Error al cargar modelo de contenido')
    } finally {
      setIsLoading(false)
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

  if (!contentModel) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="text-center">
            <IconFileTypography className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground mb-2">
              No hay modelo de contenido descubierto
            </p>
            <p className="text-sm text-muted-foreground">
              Ejecuta un aprendizaje completo para descubrir el modelo
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const contentTypes = Object.entries(contentModel.content_types || {})
  const aspects = Object.entries(contentModel.aspects || {})

  return (
    <div className="space-y-4">
      {/* Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Modelo de Contenido Descubierto</CardTitle>
          <CardDescription>
            Método: {contentModel.discovery_method} •{' '}
            Descubierto: {contentModel.discovered_at ? new Date(contentModel.discovered_at).toLocaleDateString() : 'N/A'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-4 rounded-lg bg-muted/50">
              <div className="text-2xl font-bold">{contentTypes.length}</div>
              <div className="text-sm text-muted-foreground">Tipos</div>
            </div>
            <div className="text-center p-4 rounded-lg bg-muted/50">
              <div className="text-2xl font-bold">{aspects.length}</div>
              <div className="text-sm text-muted-foreground">Aspectos</div>
            </div>
            <div className="text-center p-4 rounded-lg bg-muted/50">
              <div className="text-2xl font-bold">
                {Object.keys(contentModel.property_definitions || {}).length}
              </div>
              <div className="text-sm text-muted-foreground">Propiedades</div>
            </div>
            <div className="text-center p-4 rounded-lg bg-muted/50">
              <div className="text-2xl font-bold">
                {Object.keys(contentModel.association_types || {}).length}
              </div>
              <div className="text-sm text-muted-foreground">Asociaciones</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Content Types */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <IconFileTypography className="h-5 w-5" />
            Tipos de Contenido ({contentTypes.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {contentTypes.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">
              No se encontraron tipos de contenido
            </p>
          ) : (
            <Accordion type="multiple" className="w-full">
              {contentTypes.map(([typeName, typeData]) => {
                const semantic = contentModel.type_semantics?.[typeName]
                return (
                  <AccordionItem key={typeName} value={typeName}>
                    <AccordionTrigger className="hover:no-underline">
                      <div className="flex items-center gap-2">
                        <code className="text-sm bg-muted px-2 py-0.5 rounded">{typeName}</code>
                        {semantic && (
                          <Badge variant="outline" className="ml-2">
                            {semantic.domain}
                          </Badge>
                        )}
                      </div>
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="space-y-4 pl-4">
                        {typeData.title && (
                          <div>
                            <span className="text-sm text-muted-foreground">Título:</span>{' '}
                            <span className="font-medium">{typeData.title}</span>
                          </div>
                        )}
                        {typeData.parent && (
                          <div>
                            <span className="text-sm text-muted-foreground">Padre:</span>{' '}
                            <code className="text-sm bg-muted px-1 rounded">{typeData.parent}</code>
                          </div>
                        )}
                        {typeData.properties && typeData.properties.length > 0 && (
                          <div>
                            <span className="text-sm text-muted-foreground">Propiedades:</span>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {typeData.properties.map((prop: string) => (
                                <Badge key={prop} variant="secondary" className="text-xs">
                                  {prop}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        )}
                        {semantic && (
                          <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800">
                            <div className="flex items-center gap-2 mb-2">
                              <IconInfoCircle className="h-4 w-4 text-blue-500" />
                              <span className="text-sm font-medium text-blue-700 dark:text-blue-300">
                                Semántica Enriquecida
                              </span>
                            </div>
                            <div className="grid grid-cols-2 gap-2 text-sm">
                              <div>
                                <span className="text-muted-foreground">Tipo:</span>{' '}
                                {semantic.semantic_type}
                              </div>
                              <div>
                                <span className="text-muted-foreground">Dominio:</span>{' '}
                                {semantic.domain}
                              </div>
                              {semantic.chunking_strategy && (
                                <div>
                                  <span className="text-muted-foreground">Chunking:</span>{' '}
                                  {semantic.chunking_strategy}
                                </div>
                              )}
                              <div>
                                <span className="text-muted-foreground">Importancia:</span>{' '}
                                {semantic.importance}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                )
              })}
            </Accordion>
          )}
        </CardContent>
      </Card>

      {/* Aspects */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <IconStack2 className="h-5 w-5" />
            Aspectos ({aspects.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {aspects.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">
              No se encontraron aspectos
            </p>
          ) : (
            <Accordion type="multiple" className="w-full">
              {aspects.map(([aspectName, aspectData]) => (
                <AccordionItem key={aspectName} value={aspectName}>
                  <AccordionTrigger className="hover:no-underline">
                    <code className="text-sm bg-muted px-2 py-0.5 rounded">{aspectName}</code>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="space-y-2 pl-4">
                      {aspectData.title && (
                        <div>
                          <span className="text-sm text-muted-foreground">Título:</span>{' '}
                          <span className="font-medium">{aspectData.title}</span>
                        </div>
                      )}
                      {aspectData.properties && aspectData.properties.length > 0 && (
                        <div>
                          <span className="text-sm text-muted-foreground">Propiedades:</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {aspectData.properties.map((prop: string) => (
                              <Badge key={prop} variant="secondary" className="text-xs">
                                {prop}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

'use client'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import {
  IconUser,
  IconCalendar,
  IconCash,
  IconTrendingDown,
  IconBuildingBank,
  IconFileText,
  IconTag
} from '@tabler/icons-react'
import type { ExtractedEntity, DocumentMetadata } from '@/lib/types'

// Formato alternativo del backend (langextract_client)
interface BackendEntity {
  name?: string
  type?: string
  role?: string
  context?: string
  metadata?: {
    extraction_method?: string
    provider?: string
    model?: string
    confidence?: number
    source_indices?: [number, number] | null
    document_type?: string
  }
}

// Normaliza entidades de cualquier formato al formato esperado por el componente
function normalizeEntity(entity: ExtractedEntity | BackendEntity): ExtractedEntity {
  // Si ya tiene 'class' y 'text', es formato correcto
  if ('class' in entity && 'text' in entity) {
    return entity as ExtractedEntity
  }

  // Convertir formato backend a formato frontend
  const backendEntity = entity as BackendEntity
  return {
    class: backendEntity.type || 'otros',
    text: backendEntity.name || '',
    attributes: {
      role: backendEntity.role,
      context: backendEntity.context,
      confidence: backendEntity.metadata?.confidence,
      provider: backendEntity.metadata?.provider,
      model: backendEntity.metadata?.model,
    },
    source_indices: backendEntity.metadata?.source_indices
  }
}

interface DocumentEntitiesPanelProps {
  entities: (ExtractedEntity | BackendEntity)[]
  summary?: DocumentMetadata['extraction_summary']
  visualizationHtml?: string
  compact?: boolean
}

// Tipos de entidades relevantes para mostrar (business entities)
const RELEVANT_ENTITY_TYPES = new Set([
  // Personas
  'trabajador', 'person', 'declarante', 'cliente', 'party', 'customer', 'author', 'perceptores',
  // Empresas/Organizaciones
  'empresa', 'organization', 'company', 'proveedor', 'vendor',
  // Financiero
  'liquido', 'devengo', 'deduccion', 'amount', 'total_amount', 'iva_devengado', 'iva_deducible',
  'resultado', 'retencion', 'retenciones', 'percepciones', 'salario_base',
  // Identificadores
  'invoice_number', 'expediente', 'nif', 'cif',
  // Fechas/Períodos
  'periodo', 'fecha', 'date', 'ejercicio', 'fecha_emision',
  // Bancario
  'iban', 'bank', 'datos_bancarios', 'cuenta_bancaria',
  // Contractual
  'contract_type', 'tipo_comunicacion', 'puesto', 'obligation'
])

export function DocumentEntitiesPanel({
  entities,
  summary,
  visualizationHtml,
  compact = false
}: DocumentEntitiesPanelProps) {
  if (!entities || entities.length === 0) {
    return null
  }

  // Normalizar todas las entidades
  const normalizedEntities = entities.map(normalizeEntity)

  // Filtrar solo entidades relevantes
  const relevantEntities = normalizedEntities.filter(entity => {
    const entityClass = (entity.class || '').toLowerCase()
    return RELEVANT_ENTITY_TYPES.has(entityClass)
  })

  // Si no hay entidades relevantes, no mostrar nada
  if (relevantEntities.length === 0) {
    return null
  }

  // Agrupar entidades relevantes por clase
  const groupedEntities = relevantEntities.reduce((acc, entity) => {
    const className = entity.class || 'otros'
    if (!acc[className]) {
      acc[className] = []
    }
    acc[className].push(entity)
    return acc
  }, {} as Record<string, ExtractedEntity[]>)

  // Iconos por tipo de entidad
  const getIcon = (className: string) => {
    const iconMap: Record<string, any> = {
      // Español
      trabajador: IconUser,
      empresa: IconBuildingBank,
      periodo: IconCalendar,
      devengo: IconCash,
      deduccion: IconTrendingDown,
      liquido: IconCash,
      fecha: IconCalendar,
      cliente: IconUser,
      proveedor: IconBuildingBank,
      declarante: IconUser,
      // English (Gemini)
      organization: IconBuildingBank,
      person: IconUser,
      date: IconCalendar,
      amount: IconCash,
      event: IconFileText,
      location: IconTag,
      invoice_number: IconFileText,
      customer: IconUser,
      party: IconUser,
      default: IconTag
    }
    const Icon = iconMap[className.toLowerCase()] || iconMap.default
    return <Icon className="h-4 w-4" />
  }

  // Labels amigables
  const getFriendlyLabel = (className: string): string => {
    const labelMap: Record<string, string> = {
      // Español
      trabajador: 'Trabajador',
      empresa: 'Empresa',
      periodo: 'Período',
      devengo: 'Devengos',
      deduccion: 'Deducciones',
      liquido: 'Líquido Total',
      fecha: 'Fechas',
      cliente: 'Cliente',
      proveedor: 'Proveedor',
      invoice_number: 'Nº Factura',
      amount: 'Importes',
      declarante: 'Declarante',
      ejercicio: 'Ejercicio',
      // English (Gemini)
      organization: 'Organizaciones',
      person: 'Personas',
      date: 'Fechas',
      event: 'Eventos',
      location: 'Ubicaciones',
      customer: 'Cliente',
      party: 'Partes',
      contract_type: 'Tipo Contrato',
      obligation: 'Obligaciones'
    }
    return labelMap[className.toLowerCase()] || className.charAt(0).toUpperCase() + className.slice(1)
  }

  // Vista compacta para document-card
  if (compact && summary) {
    return (
      <div className="space-y-2">
        {/* Info clave según tipo de documento */}
        {summary.trabajador && (
          <div className="flex items-center gap-2 text-sm">
            <IconUser className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium">{summary.trabajador}</span>
          </div>
        )}

        {summary.periodo && (
          <Badge variant="outline" className="text-xs">
            <IconCalendar className="h-3 w-3 mr-1" />
            {summary.periodo}
          </Badge>
        )}

        {summary.liquido_total && (
          <div className="text-lg font-bold text-green-600 dark:text-green-400">
            {summary.liquido_total}
          </div>
        )}

        {/* Para facturas */}
        {summary.invoice_number && (
          <div className="flex items-center gap-2 text-sm">
            <IconFileText className="h-4 w-4 text-muted-foreground" />
            <span>Factura: {summary.invoice_number}</span>
          </div>
        )}

        {summary.total_amount && (
          <div className="text-lg font-bold text-blue-600 dark:text-blue-400">
            {summary.total_amount}
          </div>
        )}

        {/* Badge con total de entidades */}
        <div className="pt-2">
          <Badge variant="secondary" className="text-xs">
            {relevantEntities.length} {relevantEntities.length === 1 ? 'entidad extraída' : 'entidades extraídas'}
          </Badge>
        </div>
      </div>
    )
  }

  // Vista completa con acordeón
  return (
    <Card className="border-0 shadow-none">
      <CardContent className="p-0">
        <Accordion type="multiple" defaultValue={['summary']} className="w-full">
          {/* Acordeón 1: Resumen Ejecutivo */}
          {summary && Object.keys(summary).length > 0 && (
            <AccordionItem value="summary">
              <AccordionTrigger className="hover:no-underline">
                <div className="flex items-center gap-2">
                  <IconFileText className="h-4 w-4" />
                  <span className="font-medium">Resumen Ejecutivo</span>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-4 pt-2">
                  {/* Nómina */}
                  {summary.trabajador && (
                    <div className="space-y-2">
                      <div className="flex items-start gap-3">
                        <IconUser className="h-5 w-5 text-muted-foreground mt-0.5" />
                        <div>
                          <p className="font-medium">{summary.trabajador}</p>
                          {summary.periodo && (
                            <p className="text-sm text-muted-foreground">{summary.periodo}</p>
                          )}
                        </div>
                      </div>

                      {summary.liquido_total && (
                        <div className="rounded-lg bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-900 p-4">
                          <p className="text-sm text-muted-foreground mb-1">Líquido a percibir</p>
                          <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                            {summary.liquido_total}
                          </p>
                        </div>
                      )}

                      {summary.salario_base && (
                        <div className="text-sm">
                          <span className="text-muted-foreground">Salario base: </span>
                          <span className="font-medium">{summary.salario_base}</span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Factura */}
                  {summary.invoice_number && (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <IconFileText className="h-5 w-5 text-muted-foreground" />
                        <span className="font-medium">Factura {summary.invoice_number}</span>
                      </div>

                      {summary.customer && (
                        <div className="text-sm">
                          <span className="text-muted-foreground">Cliente: </span>
                          <span className="font-medium">{summary.customer}</span>
                        </div>
                      )}

                      {summary.total_amount && (
                        <div className="rounded-lg bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-900 p-4">
                          <p className="text-sm text-muted-foreground mb-1">Importe total</p>
                          <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                            {summary.total_amount}
                          </p>
                        </div>
                      )}

                      {summary.dates && Object.keys(summary.dates).length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(summary.dates).map(([key, value]) => (
                            <Badge key={key} variant="outline" className="text-xs">
                              <IconCalendar className="h-3 w-3 mr-1" />
                              {key}: {value}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Contrato */}
                  {summary.parties && summary.parties.length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <IconBuildingBank className="h-5 w-5 text-muted-foreground" />
                        <span className="font-medium">Partes del contrato</span>
                      </div>
                      <div className="space-y-1">
                        {summary.parties.map((party, idx) => (
                          <div key={idx} className="text-sm pl-7">
                            • {party}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </AccordionContent>
            </AccordionItem>
          )}

          {/* Acordeón 2: Detalles Completos */}
          <AccordionItem value="details">
            <AccordionTrigger className="hover:no-underline">
              <div className="flex items-center gap-2">
                <IconTag className="h-4 w-4" />
                <span className="font-medium">Detalles Completos</span>
                <Badge variant="secondary" className="ml-2 text-xs">
                  {Object.keys(groupedEntities).length} categorías
                </Badge>
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-6 pt-2">
                {Object.entries(groupedEntities).map(([className, entityList]) => (
                  <div key={className}>
                    <div className="flex items-center gap-2 mb-3">
                      {getIcon(className)}
                      <h4 className="text-sm font-semibold uppercase text-muted-foreground">
                        {getFriendlyLabel(className)}
                      </h4>
                      <Badge variant="outline" className="text-xs">
                        {entityList.length}
                      </Badge>
                    </div>

                    <div className="flex flex-wrap gap-2 pl-6">
                      {entityList.map((entity, idx) => {
                        // Filtrar atributos técnicos - solo mostrar info relevante
                        const relevantAttrs = entity.attributes
                          ? Object.entries(entity.attributes).filter(
                              ([key, value]) =>
                                value &&
                                !['provider', 'model', 'confidence', 'source_indices', 'extraction_method'].includes(key)
                            )
                          : []

                        const contextValue = entity.attributes?.context
                        const roleValue = entity.attributes?.role

                        return (
                          <Badge
                            key={idx}
                            variant="secondary"
                            className="py-1.5 px-3 text-sm font-normal hover:bg-accent transition-colors"
                          >
                            <span className="font-medium">{entity.text}</span>
                            {(roleValue || contextValue) && (
                              <span className="text-muted-foreground ml-1.5 text-xs">
                                {roleValue && `(${roleValue})`}
                                {contextValue && !roleValue && `• ${contextValue}`}
                              </span>
                            )}
                          </Badge>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </AccordionContent>
          </AccordionItem>

          {/* Acordeón 3: Visualización HTML (si existe) */}
          {visualizationHtml && (
            <AccordionItem value="visualization">
              <AccordionTrigger className="hover:no-underline">
                <div className="flex items-center gap-2">
                  <IconFileText className="h-4 w-4" />
                  <span className="font-medium">Visualización HTML</span>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div
                  className="prose prose-sm dark:prose-invert max-w-none pt-2"
                  dangerouslySetInnerHTML={{ __html: visualizationHtml }}
                />
              </AccordionContent>
            </AccordionItem>
          )}
        </Accordion>
      </CardContent>
    </Card>
  )
}

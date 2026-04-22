/**
 * Data Learning Service for Emma
 *
 * Handles all Data Learning System operations:
 * - Content model discovery
 * - Folder pattern management
 * - Property mappings
 * - Relationship types
 * - Indexing strategies
 * - Learning jobs
 */

import { apiClient } from '@/lib/api-client'

// =============================================================================
// Enums
// =============================================================================

export type DataLearningJobType =
  | 'content_model_discovery'
  | 'folder_analysis'
  | 'property_mapping'
  | 'relationship_learning'
  | 'strategy_optimization'
  | 'full_learning'

export type DataLearningJobStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type DiscoveryMethod = 'api' | 'sampling' | 'manual'

export type LevelSemanticType =
  | 'fixed'
  | 'site_identifier'
  | 'classification'
  | 'temporal'
  | 'user'
  | 'document_type'

export type RelationshipCategory = 'peer' | 'child' | 'reference'

export type ChunkingType =
  | 'semantic'
  | 'fixed_size'
  | 'legal_sections'
  | 'markdown_headers'
  | 'page_based'

// =============================================================================
// Type Definitions
// =============================================================================

export interface ContentModelSummary {
  total_types: number
  total_aspects: number
  total_properties: number
  total_associations: number
  custom_types: string[]
}

export interface TypeSemantic {
  semantic_type: string
  description?: string
  chunking_strategy?: ChunkingType
  importance: number
}

export interface PropertySemantic {
  search_weight: number
  include_in_embedding: boolean
  is_identifier: boolean
  is_date_field: boolean
  normalized_name?: string
}

export interface ConnectorContentModel {
  id: string
  connector_id: string
  content_types: Record<string, Record<string, any>>
  aspects: Record<string, Record<string, any>>
  property_definitions?: Record<string, Record<string, any>>
  association_types?: Record<string, Record<string, any>>
  type_semantics?: Record<string, TypeSemantic>
  property_semantics?: Record<string, PropertySemantic>
  discovery_method: DiscoveryMethod
  discovered_at?: string
  last_updated_at?: string
  created_at: string
}

export interface LevelSemantic {
  name: string
  type: LevelSemanticType
  values?: string[]
  format?: string
}

export interface LearnedFolderPattern {
  id: string
  connector_id: string
  path_pattern: string
  level_semantics: Record<string, Record<string, any>>
  example_paths?: string[]
  match_count: number
  confidence: number
  learned_from_sample_size?: number
  is_verified: boolean
  created_at: string
  updated_at?: string
}

export interface LearnedPropertyMapping {
  id: string
  connector_id: string
  source_property: string
  source_type?: string
  target_field: string
  search_weight: number
  include_in_embedding: boolean
  is_filterable: boolean
  is_facetable: boolean
  transformation?: string
  default_value?: string
  learned_from_usage: boolean
  usage_count: number
  created_at: string
  updated_at?: string
}

export interface LearnedRelationshipType {
  id: string
  connector_id: string
  source_relationship: string
  relationship_category: RelationshipCategory
  kg_edge_type: string
  description?: string
  include_in_retrieval: boolean
  expansion_depth: number
  weight: number
  instance_count: number
  created_at: string
  updated_at?: string
}

export interface ChunkingConfig {
  target_chunk_size: number
  overlap: number
  section_markers?: string[]
  header_levels?: number[]
}

export interface ConnectorIndexingStrategy {
  id: string
  connector_id: string
  document_type?: string
  mime_type_pattern?: string
  chunking_type: ChunkingType
  chunking_config: Record<string, any>
  embedding_fields: string[]
  embedding_weights?: Record<string, number>
  extract_entities: boolean
  entity_types?: string[]
  extract_to_knowledge_graph: boolean
  priority: number
  is_active: boolean
  created_at: string
  updated_at?: string
}

export interface DataLearningJob {
  id: string
  connector_id: string
  job_type: DataLearningJobType
  status: DataLearningJobStatus
  status_message?: string
  progress_percent: number
  current_phase?: string
  results_summary?: Record<string, any>
  errors?: Array<Record<string, any>>
  config?: Record<string, any>
  triggered_by: string
  triggered_by_user_id?: string
  started_at?: string
  completed_at?: string
  created_at: string
}

export interface ConnectorLearningStatus {
  connector_id: string
  connector_name: string
  has_content_model: boolean
  content_model_discovered_at?: string
  content_model_summary?: ContentModelSummary
  folder_patterns_count: number
  verified_patterns_count: number
  property_mappings_count: number
  custom_mappings_count: number
  relationship_types_count: number
  indexing_strategies_count: number
  active_strategies_count: number
  latest_job?: DataLearningJob
  recommendations: string[]
}

export interface TriggerLearningRequest {
  job_type?: DataLearningJobType
  force_rediscovery?: boolean
  config?: Record<string, any>
}

export interface TriggerLearningResponse {
  job_id: string
  connector_id: string
  job_type: DataLearningJobType
  status: DataLearningJobStatus
  message: string
}

export interface FolderContext {
  path: string
  pattern_id?: string
  semantics: Record<string, any>
  confidence: number
}

// Update request types
export interface UpdatePropertyMappingRequest {
  target_field?: string
  search_weight?: number
  include_in_embedding?: boolean
  is_filterable?: boolean
  is_facetable?: boolean
  transformation?: string
  default_value?: string
}

export interface UpdateFolderPatternRequest {
  path_pattern?: string
  level_semantics?: Record<string, LevelSemantic>
  is_verified?: boolean
}

export interface UpdateIndexingStrategyRequest {
  chunking_type?: ChunkingType
  chunking_config?: ChunkingConfig
  embedding_fields?: string[]
  embedding_weights?: Record<string, number>
  extract_entities?: boolean
  entity_types?: string[]
  extract_to_knowledge_graph?: boolean
  priority?: number
  is_active?: boolean
}

// =============================================================================
// Labels and display helpers
// =============================================================================

export const jobTypeLabels: Record<DataLearningJobType, string> = {
  content_model_discovery: 'Descubrimiento de Modelo',
  folder_analysis: 'Análisis de Carpetas',
  property_mapping: 'Mapeo de Propiedades',
  relationship_learning: 'Aprendizaje de Relaciones',
  strategy_optimization: 'Optimización de Estrategias',
  full_learning: 'Aprendizaje Completo',
}

export const jobStatusLabels: Record<DataLearningJobStatus, string> = {
  pending: 'Pendiente',
  running: 'Ejecutando',
  completed: 'Completado',
  failed: 'Fallido',
  cancelled: 'Cancelado',
}

export const chunkingTypeLabels: Record<ChunkingType, string> = {
  semantic: 'Semántico',
  fixed_size: 'Tamaño Fijo',
  legal_sections: 'Secciones Legales',
  markdown_headers: 'Encabezados Markdown',
  page_based: 'Por Página',
}

export const relationshipCategoryLabels: Record<RelationshipCategory, string> = {
  peer: 'Par (Bidireccional)',
  child: 'Padre-Hijo',
  reference: 'Referencia',
}

// =============================================================================
// Service Class
// =============================================================================

class DataLearningService {
  // ===========================================================================
  // Learning Status & Jobs
  // ===========================================================================

  /**
   * Get overall learning status for a connector
   */
  async getLearningStatus(connectorId: string): Promise<{ data: ConnectorLearningStatus | null; error: string | null }> {
    const response = await apiClient.get<ConnectorLearningStatus>(
      `/connectors/${connectorId}/learning-status`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Trigger a learning job for a connector
   */
  async triggerLearning(
    connectorId: string,
    request: TriggerLearningRequest = {}
  ): Promise<{ data: TriggerLearningResponse | null; error: string | null }> {
    const response = await apiClient.post<TriggerLearningResponse>(
      `/connectors/${connectorId}/learn`,
      request
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Get learning jobs for a connector
   */
  async getJobs(
    connectorId: string,
    params?: { status?: DataLearningJobStatus; limit?: number; offset?: number }
  ): Promise<{ data: { items: DataLearningJob[]; total: number } | null; error: string | null }> {
    const searchParams = new URLSearchParams()
    if (params?.status) searchParams.append('status', params.status)
    if (params?.limit) searchParams.append('limit', params.limit.toString())
    if (params?.offset) searchParams.append('offset', params.offset.toString())

    const response = await apiClient.get<{ items: DataLearningJob[]; total: number }>(
      `/connectors/${connectorId}/learning-jobs?${searchParams.toString()}`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Get a specific learning job
   */
  async getJob(
    connectorId: string,
    jobId: string
  ): Promise<{ data: DataLearningJob | null; error: string | null }> {
    const response = await apiClient.get<DataLearningJob>(
      `/connectors/${connectorId}/learning-jobs/${jobId}`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Cancel a running learning job
   */
  async cancelJob(
    connectorId: string,
    jobId: string
  ): Promise<{ error: string | null }> {
    const response = await apiClient.post(
      `/connectors/${connectorId}/learning-jobs/${jobId}/cancel`
    )
    if (response.error) {
      return { error: response.error }
    }
    return { error: null }
  }

  // ===========================================================================
  // Content Model
  // ===========================================================================

  /**
   * Get discovered content model for a connector
   */
  async getContentModel(connectorId: string): Promise<{ data: ConnectorContentModel | null; error: string | null }> {
    const response = await apiClient.get<ConnectorContentModel>(
      `/connectors/${connectorId}/model`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  // ===========================================================================
  // Folder Patterns
  // ===========================================================================

  /**
   * Get learned folder patterns
   */
  async getFolderPatterns(connectorId: string): Promise<{ data: LearnedFolderPattern[] | null; error: string | null }> {
    const response = await apiClient.get<{ items: LearnedFolderPattern[]; total: number }>(
      `/connectors/${connectorId}/folder-patterns`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data?.items ?? [], error: null }
  }

  /**
   * Update a folder pattern
   */
  async updateFolderPattern(
    connectorId: string,
    patternId: string,
    data: UpdateFolderPatternRequest
  ): Promise<{ data: LearnedFolderPattern | null; error: string | null }> {
    const response = await apiClient.put<LearnedFolderPattern>(
      `/connectors/${connectorId}/folder-patterns/${patternId}`,
      data
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Verify a folder pattern
   */
  async verifyFolderPattern(
    connectorId: string,
    patternId: string
  ): Promise<{ data: LearnedFolderPattern | null; error: string | null }> {
    return this.updateFolderPattern(connectorId, patternId, { is_verified: true })
  }

  /**
   * Delete a folder pattern
   */
  async deleteFolderPattern(
    connectorId: string,
    patternId: string
  ): Promise<{ error: string | null }> {
    const response = await apiClient.delete(
      `/connectors/${connectorId}/folder-patterns/${patternId}`
    )
    if (response.error) {
      return { error: response.error }
    }
    return { error: null }
  }

  /**
   * Get folder context for a document path
   */
  async getFolderContext(
    connectorId: string,
    path: string
  ): Promise<{ data: FolderContext | null; error: string | null }> {
    const response = await apiClient.post<FolderContext>(
      `/connectors/${connectorId}/folder-context`,
      { path }
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  // ===========================================================================
  // Property Mappings
  // ===========================================================================

  /**
   * Get property mappings
   */
  async getPropertyMappings(connectorId: string): Promise<{ data: LearnedPropertyMapping[] | null; error: string | null }> {
    const response = await apiClient.get<{ items: LearnedPropertyMapping[]; total: number }>(
      `/connectors/${connectorId}/property-mappings`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data?.items ?? [], error: null }
  }

  /**
   * Update a property mapping
   */
  async updatePropertyMapping(
    connectorId: string,
    mappingId: string,
    data: UpdatePropertyMappingRequest
  ): Promise<{ data: LearnedPropertyMapping | null; error: string | null }> {
    const response = await apiClient.put<LearnedPropertyMapping>(
      `/connectors/${connectorId}/property-mappings/${mappingId}`,
      data
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Delete a property mapping
   */
  async deletePropertyMapping(
    connectorId: string,
    mappingId: string
  ): Promise<{ error: string | null }> {
    const response = await apiClient.delete(
      `/connectors/${connectorId}/property-mappings/${mappingId}`
    )
    if (response.error) {
      return { error: response.error }
    }
    return { error: null }
  }

  // ===========================================================================
  // Relationship Types
  // ===========================================================================

  /**
   * Get relationship types
   */
  async getRelationshipTypes(connectorId: string): Promise<{ data: LearnedRelationshipType[] | null; error: string | null }> {
    const response = await apiClient.get<{ items: LearnedRelationshipType[]; total: number }>(
      `/connectors/${connectorId}/relationship-types`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data?.items ?? [], error: null }
  }

  // ===========================================================================
  // Indexing Strategies
  // ===========================================================================

  /**
   * Get indexing strategies
   */
  async getIndexingStrategies(connectorId: string): Promise<{ data: ConnectorIndexingStrategy[] | null; error: string | null }> {
    const response = await apiClient.get<{ items: ConnectorIndexingStrategy[]; total: number }>(
      `/connectors/${connectorId}/indexing-strategies`
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data?.items ?? [], error: null }
  }

  /**
   * Update an indexing strategy
   */
  async updateIndexingStrategy(
    connectorId: string,
    strategyId: string,
    data: UpdateIndexingStrategyRequest
  ): Promise<{ data: ConnectorIndexingStrategy | null; error: string | null }> {
    const response = await apiClient.put<ConnectorIndexingStrategy>(
      `/connectors/${connectorId}/indexing-strategies/${strategyId}`,
      data
    )
    if (response.error) {
      return { data: null, error: response.error }
    }
    return { data: response.data, error: null }
  }

  /**
   * Toggle indexing strategy active state
   */
  async toggleStrategy(
    connectorId: string,
    strategyId: string,
    isActive: boolean
  ): Promise<{ data: ConnectorIndexingStrategy | null; error: string | null }> {
    return this.updateIndexingStrategy(connectorId, strategyId, { is_active: isActive })
  }
}

export const dataLearningService = new DataLearningService()

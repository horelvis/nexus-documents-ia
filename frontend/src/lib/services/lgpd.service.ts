/**
 * LGPD Service - API client for LGPD compliance endpoints
 * Lei Geral de Proteção de Dados (LGPD) compliance
 */

export interface UserDataSummary {
  user_id: string
  email: string
  full_name: string | null
  tenant: string
  created_at: string
  data_summary: {
    profile_data: {
      user_record: number
      user_image: number
      external_accounts: {
        clerk: boolean
        stripe: boolean
      }
    }
    document_data: {
      documents_created: number
      document_views: number
    }
    access_data: {
      role_assignments: number
    }
    audit_data: {
      note: string
      retention_reason: string
    }
  }
  lgpd_rights: {
    article_18: string
    deletion_scope: string
    audit_retention: string
    external_services: string
  }
}

export interface LGPDDeletionRequest {
  confirmation_email: string
  confirmation_text: string
  reason?: string
}

export interface DeletionResult {
  user_id: string
  deletion_id: string
  status: string
  deleted_at: string
  summary: {
    deleted_records: Record<string, number>
    anonymized_records: number
    storage_deletions: Record<string, any>
    external_deletions: Record<string, any>
    errors: string[]
  }
  lgpd_compliance: {
    article: string
    method: string
    anonymization_applied: boolean
    external_services_notified: Record<string, any>
  }
}

export interface DeletionAuditRecord {
  deletion_id: string
  user_id: string
  user_email: string
  requested_by: {
    id: string
    email: string
    full_name: string | null
  } | null
  status: string
  started_at: string
  completed_at: string | null
  total_records_deleted: number
  anonymized_records: number
  lgpd_article: string
  deletion_method: string
  reason: string | null
}

export interface LGPDComplianceInfo {
  lgpd_compliance: {
    law: string
    user_rights: {
      article_18: {
        title: string
        description: string
        scope: string
        exceptions: string
      }
      article_9: {
        title: string
        description: string
        endpoint: string
      }
    }
    deletion_process: {
      step_1: string
      step_2: string
      step_3: string
      step_4: string
      irreversible: boolean
      external_services: string
    }
    data_retention: {
      audit_records: string
      deleted_data: string
      backups: string
    }
  }
}

class LGPDService {
  private baseUrl = '/api/v1/lgpd'

  /**
   * Get comprehensive summary of user data for LGPD transparency
   */
  async getUserDataSummary(): Promise<UserDataSummary> {
    const response = await fetch(`${this.baseUrl}/data-summary`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to get data summary')
    }

    return response.json()
  }

  /**
   * Request complete user data deletion for LGPD compliance
   */
  async requestUserDeletion(request: LGPDDeletionRequest): Promise<DeletionResult> {
    const response = await fetch(`${this.baseUrl}/request-deletion`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to process deletion request')
    }

    return response.json()
  }

  /**
   * Admin endpoint to delete user for LGPD compliance
   */
  async adminDeleteUser(userId: string, reason?: string): Promise<DeletionResult> {
    const response = await fetch(`${this.baseUrl}/admin/delete-user`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        user_id: userId,
        reason,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to process admin deletion request')
    }

    return response.json()
  }

  /**
   * Get LGPD deletion audit history for the tenant (admin only)
   */
  async getDeletionHistory(): Promise<{
    tenant_id: string
    total_deletions: number
    deletions: DeletionAuditRecord[]
  }> {
    const response = await fetch(`${this.baseUrl}/deletion-history`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to get deletion history')
    }

    return response.json()
  }

  /**
   * Get information about LGPD compliance and user rights
   */
  async getComplianceInfo(): Promise<LGPDComplianceInfo> {
    const response = await fetch(`${this.baseUrl}/compliance-info`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Failed to get compliance info')
    }

    return response.json()
  }

  /**
   * Format deletion summary for display
   */
  formatDeletionSummary(summary: DeletionResult['summary']): {
    totalDeleted: number
    deletedByType: Array<{ type: string; count: number }>
    hasErrors: boolean
    errorCount: number
  } {
    const totalDeleted = Object.values(summary.deleted_records).reduce((total, count) => total + count, 0)
    
    const deletedByType = Object.entries(summary.deleted_records)
      .filter(([_, count]) => count > 0)
      .map(([type, count]) => ({
        type: this.formatRecordType(type),
        count
      }))

    return {
      totalDeleted,
      deletedByType,
      hasErrors: summary.errors.length > 0,
      errorCount: summary.errors.length
    }
  }

  /**
   * Format record type for display
   */
  private formatRecordType(type: string): string {
    const typeMap: Record<string, string> = {
      'documents': 'Documentos',
      'profile_data': 'Dados de Perfil',
      'user': 'Usuário',
      'vector_data': 'Dados Vetoriais',
      'elasticsearch_data': 'Índices de Busca'
    }

    return typeMap[type] || type
  }

  /**
   * Validate deletion confirmation text
   */
  validateConfirmationText(text: string): boolean {
    return text === "DELETE"
  }

  /**
   * Check if user can request deletion (basic validation)
   */
  canRequestDeletion(userEmail: string, confirmationEmail: string, confirmationText: string): boolean {
    return userEmail === confirmationEmail && this.validateConfirmationText(confirmationText)
  }

  /**
   * Format date for Brazilian locale
   */
  formatDate(dateString: string): string {
    return new Date(dateString).toLocaleString('pt-BR', {
      year: 'numeric',
      month: '2-digit', 
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  /**
   * Get deletion status display info
   */
  getDeletionStatusInfo(status: string): {
    label: string
    color: string
    description: string
  } {
    const statusMap: Record<string, { label: string; color: string; description: string }> = {
      'pending': {
        label: 'Pendente',
        color: 'text-yellow-600',
        description: 'Solicitação de exclusão aguardando processamento'
      },
      'in_progress': {
        label: 'Em Processamento',
        color: 'text-blue-600',
        description: 'Exclusão de dados em andamento'
      },
      'completed': {
        label: 'Concluído',
        color: 'text-green-600',
        description: 'Dados excluídos com sucesso'
      },
      'completed_with_errors': {
        label: 'Concluído com Erros',
        color: 'text-orange-600',
        description: 'Exclusão finalizada mas com alguns erros'
      },
      'failed': {
        label: 'Falhou',
        color: 'text-red-600',
        description: 'Falha na exclusão dos dados'
      }
    }

    return statusMap[status] || {
      label: status,
      color: 'text-gray-600',
      description: 'Status desconhecido'
    }
  }
}

// Export singleton instance
export const lgpdService = new LGPDService()
export default lgpdService

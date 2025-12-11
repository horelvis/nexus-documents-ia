import { useMemo } from 'react'
import { useApiClient } from '../api-client'
import {
  DocumentACL,
  DocumentACLListResponse,
  EffectivePermissions,
  GrantPermissionRequest,
  RevokePermissionRequest,
  CheckPermissionResponse,
  Permission,
  DocumentACLAuditListResponse,
  BulkACLUpdateRequest,
  BulkACLUpdateResponse,
} from '../types'

/**
 * Service for managing document-level Access Control Lists (ACLs).
 *
 * Provides methods to:
 * - Check user permissions on documents
 * - Grant/revoke permissions to users, roles, or everyone
 * - List ACL entries for documents
 * - View audit logs for permission changes
 */
export class DocumentACLService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  // ========================================
  // PERMISSION CHECKING
  // ========================================

  /**
   * Get current user's effective permissions on a document.
   * This combines owner status, admin status, and all applicable ACLs.
   */
  async getMyPermissions(documentId: string) {
    const endpoint = `/documents/${documentId}/acl/my-permissions`
    return this.apiClient.get<EffectivePermissions>(endpoint)
  }

  /**
   * Check if current user has a specific permission on a document.
   */
  async checkPermission(documentId: string, permission: Permission) {
    const endpoint = `/documents/${documentId}/acl/check/${permission}`
    return this.apiClient.get<CheckPermissionResponse>(endpoint)
  }

  // ========================================
  // LIST/GET ACLs
  // ========================================

  /**
   * List all ACL entries for a document.
   * Includes resolved names for grantees and granters.
   */
  async listDocumentACLs(documentId: string) {
    const endpoint = `/documents/${documentId}/acl`
    return this.apiClient.get<DocumentACLListResponse>(endpoint)
  }

  /**
   * Get a specific ACL entry by ID.
   */
  async getACL(documentId: string, aclId: string) {
    const endpoint = `/documents/${documentId}/acl/${aclId}`
    return this.apiClient.get<DocumentACL>(endpoint)
  }

  // ========================================
  // GRANT PERMISSIONS
  // ========================================

  /**
   * Grant permissions on a document to a user, role, or everyone.
   *
   * @param documentId - Document to grant access to
   * @param request - Grant request with grantee and permissions
   * @returns Created or updated ACL entry
   */
  async grantPermission(documentId: string, request: GrantPermissionRequest) {
    const endpoint = `/documents/${documentId}/acl`
    return this.apiClient.post<DocumentACL>(endpoint, request)
  }

  /**
   * Grant permissions to multiple grantees at once.
   */
  async grantPermissionsBatch(documentId: string, grants: GrantPermissionRequest[]) {
    const endpoint = `/documents/${documentId}/acl/batch`
    return this.apiClient.post<DocumentACL[]>(endpoint, { grants })
  }

  // ========================================
  // REVOKE PERMISSIONS
  // ========================================

  /**
   * Revoke a specific ACL entry by its ID.
   */
  async revokeByACLId(documentId: string, aclId: string) {
    const endpoint = `/documents/${documentId}/acl/${aclId}`
    return this.apiClient.delete<{ status: string; message: string }>(endpoint)
  }

  /**
   * Revoke permissions from a user, role, or everyone.
   */
  async revokePermission(documentId: string, request: RevokePermissionRequest) {
    const endpoint = `/documents/${documentId}/acl/revoke`
    return this.apiClient.post<{ status: string; message: string }>(endpoint, request)
  }

  // ========================================
  // BULK OPERATIONS
  // ========================================

  /**
   * Update ACLs on multiple documents at once.
   * Useful for applying same permissions to multiple documents.
   */
  async bulkUpdateACLs(request: BulkACLUpdateRequest) {
    const endpoint = `/documents/bulk-update`
    return this.apiClient.post<BulkACLUpdateResponse>(endpoint, request)
  }

  // ========================================
  // AUDIT LOG
  // ========================================

  /**
   * Get ACL audit log for a specific document.
   * Shows all permission changes (granted, revoked, modified, expired).
   */
  async getDocumentAuditLog(documentId: string, page: number = 1, pageSize: number = 50) {
    const searchParams = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    })
    const endpoint = `/documents/${documentId}/acl/audit?${searchParams.toString()}`
    return this.apiClient.get<DocumentACLAuditListResponse>(endpoint)
  }

  /**
   * Get ACL audit log for all documents in tenant.
   * Requires admin permissions.
   */
  async getTenantAuditLog(page: number = 1, pageSize: number = 50) {
    const searchParams = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    })
    const endpoint = `/documents/audit?${searchParams.toString()}`
    return this.apiClient.get<DocumentACLAuditListResponse>(endpoint)
  }

  // ========================================
  // HELPER METHODS
  // ========================================

  /**
   * Grant view-only access to a user.
   */
  async grantViewAccess(documentId: string, userId: string, expiresAt?: string) {
    return this.grantPermission(documentId, {
      grantee_type: 'user',
      grantee_id: userId,
      permissions: {
        can_view: true,
        can_edit: false,
        can_delete: false,
        can_share: false,
      },
      expires_at: expiresAt,
      source: 'manual',
    })
  }

  /**
   * Grant edit access to a user (includes view).
   */
  async grantEditAccess(documentId: string, userId: string, expiresAt?: string) {
    return this.grantPermission(documentId, {
      grantee_type: 'user',
      grantee_id: userId,
      permissions: {
        can_view: true,
        can_edit: true,
        can_delete: false,
        can_share: false,
      },
      expires_at: expiresAt,
      source: 'manual',
    })
  }

  /**
   * Grant full access to a user (view, edit, delete, share).
   */
  async grantFullAccess(documentId: string, userId: string, expiresAt?: string) {
    return this.grantPermission(documentId, {
      grantee_type: 'user',
      grantee_id: userId,
      permissions: {
        can_view: true,
        can_edit: true,
        can_delete: true,
        can_share: true,
      },
      expires_at: expiresAt,
      source: 'manual',
    })
  }

  /**
   * Make document accessible to everyone in the tenant (view only).
   */
  async makePublicInTenant(documentId: string) {
    return this.grantPermission(documentId, {
      grantee_type: 'everyone',
      permissions: {
        can_view: true,
        can_edit: false,
        can_delete: false,
        can_share: false,
      },
      source: 'manual',
    })
  }

  /**
   * Remove public access (revoke 'everyone' ACL).
   */
  async makePrivate(documentId: string) {
    return this.revokePermission(documentId, {
      grantee_type: 'everyone',
    })
  }

  /**
   * Revoke all access for a specific user.
   */
  async revokeUserAccess(documentId: string, userId: string) {
    return this.revokePermission(documentId, {
      grantee_type: 'user',
      grantee_id: userId,
    })
  }
}

/**
 * Hook to use the Document ACL service.
 * Provides memoized instance that updates when apiClient changes.
 */
export function useDocumentACLService() {
  const apiClient = useApiClient()
  return useMemo(() => new DocumentACLService(apiClient), [apiClient])
}

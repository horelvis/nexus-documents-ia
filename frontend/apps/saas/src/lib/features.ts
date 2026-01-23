/**
 * Feature Flags Client for NouxCubeIA Frontend
 *
 * Fetches and caches feature flag state from the backend.
 * Used to conditionally render UI components based on deployment mode.
 *
 * Usage:
 *   import { isFeatureEnabled, getFeatures, DeploymentMode } from '@/lib/features'
 *
 *   if (await isFeatureEnabled('digital_signatures')) {
 *     // Show signatures UI
 *   }
 */

import { apiClient } from './api-client'

/**
 * Available feature flags.
 * Must match backend Feature enum in app.core.features.
 */
export enum Feature {
  // Modules to DISABLE for on-premise
  DIGITAL_SIGNATURES = 'digital_signatures',
  SITE_PORTAL = 'site_portal',
  DASHBOARD_ANALYTICS = 'dashboard_analytics',
  ELASTICSEARCH_SEARCH = 'elasticsearch_search',
  DOCUMENT_EDITING = 'document_editing',
  DOCUMENT_LIBRARY_UI = 'document_library_ui',
  STRIPE_BILLING = 'stripe_billing',
  CLERK_AUTH = 'clerk_auth',

  // Modules to ENABLE for on-premise
  EMMA_FULLSCREEN_MODE = 'emma_fullscreen_mode',
  SSO_MULTI_PROTOCOL = 'sso_multi_protocol',
  SHAREPOINT_CONNECTOR = 'sharepoint_connector',
  ONEDRIVE_CONNECTOR = 'onedrive_connector',
  GOOGLE_WORKSPACE_CONNECTOR = 'google_workspace_connector',
  WEAVIATE_HYBRID_SEARCH = 'weaviate_hybrid_search',
}

/**
 * Deployment modes matching backend DeploymentMode enum.
 */
export enum DeploymentMode {
  SAAS = 'saas',
  ON_PREMISE = 'on_premise',
  CUSTOM = 'custom',
}

/**
 * Feature flags response from API.
 */
export interface FeatureFlagsResponse {
  deployment_mode: string
  features: Record<string, boolean>
  enabled: string[]
  disabled: string[]
}

/**
 * Deployment info response (public, no auth required).
 */
export interface DeploymentInfo {
  deployment_mode: string
  auth_provider: 'clerk' | 'sso'
  emma_mode: 'fullscreen' | 'sidebar'
}

// Cache for feature flags
let cachedFeatures: FeatureFlagsResponse | null = null
let cacheTimestamp = 0
const CACHE_TTL_MS = 5 * 60 * 1000 // 5 minutes

/**
 * Fetch feature flags from the backend.
 * Results are cached for 5 minutes.
 *
 * @param forceRefresh - Force refresh even if cache is valid
 * @returns Feature flags response
 */
export async function getFeatures(
  forceRefresh = false
): Promise<FeatureFlagsResponse> {
  const now = Date.now()

  // Return cached if valid
  if (!forceRefresh && cachedFeatures && now - cacheTimestamp < CACHE_TTL_MS) {
    return cachedFeatures
  }

  try {
    const response = await apiClient.get<FeatureFlagsResponse>('/features')

    if (response.data) {
      cachedFeatures = response.data
      cacheTimestamp = now
      return response.data
    }

    // Return default on error
    return getDefaultFeatures()
  } catch (error) {
    console.error('Failed to fetch features:', error)
    return getDefaultFeatures()
  }
}

/**
 * Check if a specific feature is enabled.
 *
 * @param feature - Feature to check
 * @returns true if enabled
 */
export async function isFeatureEnabled(feature: Feature): Promise<boolean> {
  const features = await getFeatures()
  return features.features[feature] ?? true
}

/**
 * Synchronous check if a feature is enabled.
 * Only works if features have been fetched already.
 * Returns true by default if cache is empty.
 *
 * @param feature - Feature to check
 * @returns true if enabled (or unknown)
 */
export function isFeatureEnabledSync(feature: Feature): boolean {
  if (!cachedFeatures) {
    return true // Default to enabled if not loaded
  }
  return cachedFeatures.features[feature] ?? true
}

/**
 * Get the current deployment mode.
 *
 * @returns Deployment mode string
 */
export async function getDeploymentMode(): Promise<string> {
  const features = await getFeatures()
  return features.deployment_mode
}

/**
 * Check if running in on-premise mode.
 */
export async function isOnPremiseMode(): Promise<boolean> {
  const mode = await getDeploymentMode()
  return mode === DeploymentMode.ON_PREMISE
}

/**
 * Check if running in SaaS mode.
 */
export async function isSaaSMode(): Promise<boolean> {
  const mode = await getDeploymentMode()
  return mode === DeploymentMode.SAAS
}

/**
 * Get deployment info (public endpoint, no auth required).
 * Useful for login page customization.
 */
export async function getDeploymentInfo(): Promise<DeploymentInfo> {
  try {
    const response = await fetch('/api/v1/features/mode/info')
    if (response.ok) {
      return await response.json()
    }
  } catch (error) {
    console.error('Failed to fetch deployment info:', error)
  }

  // Default to On-Premise mode
  return {
    deployment_mode: DeploymentMode.ON_PREMISE,
    auth_provider: 'sso',
    emma_mode: 'fullscreen',
  }
}

/**
 * Clear the feature flags cache.
 * Call this when tenant changes or on logout.
 */
export function clearFeaturesCache(): void {
  cachedFeatures = null
  cacheTimestamp = 0
}

/**
 * Prefetch features for faster subsequent access.
 * Call this early in app initialization.
 */
export async function prefetchFeatures(): Promise<void> {
  await getFeatures(true)
}

/**
 * Get list of enabled features.
 */
export async function getEnabledFeatures(): Promise<string[]> {
  const features = await getFeatures()
  return features.enabled
}

/**
 * Get list of disabled features.
 */
export async function getDisabledFeatures(): Promise<string[]> {
  const features = await getFeatures()
  return features.disabled
}

/**
 * Default feature flags (On-Premise mode).
 * Used as fallback when API is unavailable.
 * Default is ON_PREMISE for Emma-centric deployment.
 */
function getDefaultFeatures(): FeatureFlagsResponse {
  return {
    deployment_mode: DeploymentMode.ON_PREMISE,
    features: {
      [Feature.DIGITAL_SIGNATURES]: false,
      [Feature.SITE_PORTAL]: false,
      [Feature.DASHBOARD_ANALYTICS]: false,
      [Feature.ELASTICSEARCH_SEARCH]: false,
      [Feature.DOCUMENT_EDITING]: false,
      [Feature.DOCUMENT_LIBRARY_UI]: false,
      [Feature.STRIPE_BILLING]: false,
      [Feature.CLERK_AUTH]: false,
      [Feature.EMMA_FULLSCREEN_MODE]: true,
      [Feature.SSO_MULTI_PROTOCOL]: true,
      [Feature.SHAREPOINT_CONNECTOR]: true,
      [Feature.ONEDRIVE_CONNECTOR]: true,
      [Feature.GOOGLE_WORKSPACE_CONNECTOR]: true,
      [Feature.WEAVIATE_HYBRID_SEARCH]: true,
    },
    enabled: [
      Feature.EMMA_FULLSCREEN_MODE,
      Feature.SSO_MULTI_PROTOCOL,
      Feature.SHAREPOINT_CONNECTOR,
      Feature.ONEDRIVE_CONNECTOR,
      Feature.GOOGLE_WORKSPACE_CONNECTOR,
      Feature.WEAVIATE_HYBRID_SEARCH,
    ],
    disabled: [
      Feature.DIGITAL_SIGNATURES,
      Feature.SITE_PORTAL,
      Feature.DASHBOARD_ANALYTICS,
      Feature.ELASTICSEARCH_SEARCH,
      Feature.DOCUMENT_EDITING,
      Feature.DOCUMENT_LIBRARY_UI,
      Feature.STRIPE_BILLING,
      Feature.CLERK_AUTH,
    ],
  }
}

// ============================================================================
// React Hooks (for use in components)
// ============================================================================

import { useState, useEffect } from 'react'

/**
 * React hook to get all feature flags.
 *
 * @example
 * const { features, loading, error } = useFeatures()
 * if (features?.features.digital_signatures) {
 *   return <SignaturesUI />
 * }
 */
export function useFeatures() {
  const [features, setFeatures] = useState<FeatureFlagsResponse | null>(
    cachedFeatures
  )
  const [loading, setLoading] = useState(!cachedFeatures)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    let mounted = true

    async function fetchFeatures() {
      try {
        const data = await getFeatures()
        if (mounted) {
          setFeatures(data)
          setLoading(false)
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err : new Error('Unknown error'))
          setLoading(false)
        }
      }
    }

    if (!cachedFeatures) {
      fetchFeatures()
    }

    return () => {
      mounted = false
    }
  }, [])

  return { features, loading, error }
}

/**
 * React hook to check if a feature is enabled.
 *
 * @example
 * const signaturesEnabled = useFeature(Feature.DIGITAL_SIGNATURES)
 * if (signaturesEnabled) {
 *   return <SignaturesUI />
 * }
 */
export function useFeature(feature: Feature): boolean {
  const { features } = useFeatures()
  return features?.features[feature] ?? true
}

/**
 * React hook to get deployment mode.
 *
 * @example
 * const mode = useDeploymentMode()
 * if (mode === DeploymentMode.ON_PREMISE) {
 *   return <EmmaFullscreen />
 * }
 */
export function useDeploymentMode(): string {
  const { features } = useFeatures()
  return features?.deployment_mode ?? DeploymentMode.ON_PREMISE
}

/**
 * React hook for Emma fullscreen mode check.
 *
 * @example
 * const isEmmaFullscreen = useEmmaFullscreenMode()
 */
export function useEmmaFullscreenMode(): boolean {
  return useFeature(Feature.EMMA_FULLSCREEN_MODE)
}

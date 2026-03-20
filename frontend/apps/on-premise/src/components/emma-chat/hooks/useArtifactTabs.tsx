import { FileCheck, TrendingUp, Hammer, Eye } from 'lucide-react'
import type { ArtifactTab } from '../ArtifactsPanel'
import { VerifiedGenTab } from '../artifacts/VerifiedGenTab'
import { PredictiveTab } from '../artifacts/PredictiveTab'
import { ForgeTab } from '../artifacts/ForgeTab'
import { DocumentPreviewTab } from '../artifacts/DocumentPreviewTab'
import type { DocumentInfo, ForgeMetadata } from '@/lib/types/emma'

interface UseArtifactTabsParams {
  verifiedJobs: Record<string, any>
  predictiveJobs: Record<string, any>
  forgeMetadata: ForgeMetadata | null
  onSubmitReview: (jobId: string, review: any) => void
  previewDoc?: DocumentInfo | null
  onClosePreview?: () => void
}

export function useArtifactTabs({
  verifiedJobs,
  predictiveJobs,
  forgeMetadata,
  onSubmitReview,
  previewDoc,
  onClosePreview,
}: UseArtifactTabsParams): ArtifactTab[] {
  const tabs: ArtifactTab[] = []

  // Preview tab — inserted first when a document is selected
  if (previewDoc) {
    tabs.push({
      id: 'preview',
      label: 'Vista Previa',
      icon: <Eye className="h-3.5 w-3.5" />,
      content: <DocumentPreviewTab document={previewDoc} onClose={onClosePreview} />,
    })
  }

  if (Object.keys(verifiedJobs).length > 0) {
    const totalClaims = Object.values(verifiedJobs).reduce(
      (sum, j) => sum + (j.total_claims || 0),
      0,
    )
    const verifiedCount = Object.values(verifiedJobs).reduce(
      (sum, j) => sum + (j.verified_count || 0),
      0,
    )
    tabs.push({
      id: 'verified',
      label: 'Verified Gen',
      icon: <FileCheck className="h-3.5 w-3.5" />,
      badge: totalClaims > 0 ? `${verifiedCount}/${totalClaims}` : undefined,
      content: <VerifiedGenTab jobs={verifiedJobs} onSubmitReview={onSubmitReview} />,
    })
  }

  if (Object.keys(predictiveJobs).length > 0) {
    tabs.push({
      id: 'predictive',
      label: 'Predictive',
      icon: <TrendingUp className="h-3.5 w-3.5" />,
      content: <PredictiveTab jobs={predictiveJobs} />,
    })
  }

  if (forgeMetadata) {
    tabs.push({
      id: 'forge',
      label: 'Document Forge',
      icon: <Hammer className="h-3.5 w-3.5" />,
      badge: forgeMetadata.fields?.length
        ? `${forgeMetadata.fields_filled || 0}/${forgeMetadata.fields.length}`
        : undefined,
      content: <ForgeTab metadata={forgeMetadata} />,
    })
  }

  return tabs
}

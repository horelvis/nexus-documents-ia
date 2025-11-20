"use client"

import { useParams } from "next/navigation"
import { UploadDialog } from "@/components/dashboard/upload-dialog"
import { useUpload } from "@/contexts/upload-context"
import { useNotifications } from "@/contexts/app-state-context"
import { useDocumentEvents } from "@/contexts/document-events-context"

export function GlobalUploadDialog() {
  const { uploadDialogOpen, setUploadDialogOpen, onUploadComplete } = useUpload()
  const { addNotification } = useNotifications()
  const { emitDocumentEvent } = useDocumentEvents()
  const params = useParams()
  const tenantIdParam = params?.tenantId as string | string[] | undefined
  const tenantId = Array.isArray(tenantIdParam) ? tenantIdParam[0] : tenantIdParam

  const handleUploadComplete = (uploadedFiles: Array<{file: File, id: string, status: string}>) => {
    console.log('GlobalUploadDialog handleUploadComplete called with:', uploadedFiles)
    
    if (!uploadedFiles || !Array.isArray(uploadedFiles)) {
      console.error('Invalid uploadedFiles received:', uploadedFiles)
      return
    }

    addNotification({
      type: 'upload',
      title: 'Upload Complete',
      message: `${uploadedFiles.length} file${uploadedFiles.length > 1 ? 's' : ''} uploaded successfully`,
      fileCount: uploadedFiles.length,
      action: {
        label: 'View Documents',
        href: '/dashboard/documents'
      }
    })

    emitDocumentEvent("documents:updated", {
      tenantId,
      source: "upload",
      files: uploadedFiles
    })

    if (onUploadComplete && typeof onUploadComplete === 'function') {
      try {
        onUploadComplete(uploadedFiles)
      } catch (error) {
        console.error('Error in onUploadComplete callback:', error)
      }
    }
  }

  return (
    <UploadDialog 
      open={uploadDialogOpen}
      onOpenChange={setUploadDialogOpen}
      onUploadComplete={handleUploadComplete}
    />
  )
}

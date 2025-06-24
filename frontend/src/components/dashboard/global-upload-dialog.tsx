"use client"

import { UploadDialog } from "@/components/dashboard/upload-dialog"
import { useUpload } from "@/contexts/upload-context"
import { useNotifications } from "@/contexts/app-state-context"

export function GlobalUploadDialog() {
  const { uploadDialogOpen, setUploadDialogOpen, onUploadComplete } = useUpload()
  const { addNotification } = useNotifications()

  const handleUploadComplete = (uploadedFiles: Array<{file: File, id: string, status: string}>) => {
    console.log('GlobalUploadDialog handleUploadComplete called with:', uploadedFiles)
    
    // Validate uploadedFiles
    if (!uploadedFiles || !Array.isArray(uploadedFiles)) {
      console.error('Invalid uploadedFiles received:', uploadedFiles)
      return
    }

    // Show success notification
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

    // Call the specific page handler if it exists
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
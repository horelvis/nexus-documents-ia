"use client"

import { createContext, useContext, useState, ReactNode, useCallback } from "react"

interface UploadContextType {
  uploadDialogOpen: boolean
  setUploadDialogOpen: (open: boolean) => void
  openUploadDialog: (folderPath?: string) => void
  closeUploadDialog: () => void
  onUploadComplete?: (files: any[]) => void
  setOnUploadComplete: (callback?: (files: any[]) => void) => void
  targetFolderPath: string | null
  setTargetFolderPath: (path: string | null) => void
}

const UploadContext = createContext<UploadContextType | undefined>(undefined)

export function UploadProvider({ children }: { children: ReactNode }) {
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false)
  const [onUploadComplete, setOnUploadComplete] = useState<((files: any[]) => void) | undefined>(undefined)
  const [targetFolderPath, setTargetFolderPath] = useState<string | null>(null)

  const openUploadDialog = (folderPath?: string) => {
    console.log('[DEBUG] UploadContext: Opening dialog with folder:', folderPath)
    if (folderPath) {
      setTargetFolderPath(folderPath)
    }
    setUploadDialogOpen(true)
  }
  const closeUploadDialog = () => {
    console.log('[DEBUG] UploadContext: Closing dialog')
    setUploadDialogOpen(false)
    setTargetFolderPath(null)
  }

  const handleSetOnUploadComplete = useCallback((callback?: (files: any[]) => void) => {
    setOnUploadComplete(() => callback)
  }, [])

  return (
    <UploadContext.Provider value={{
      uploadDialogOpen,
      setUploadDialogOpen,
      openUploadDialog,
      closeUploadDialog,
      onUploadComplete,
      setOnUploadComplete: handleSetOnUploadComplete,
      targetFolderPath,
      setTargetFolderPath
    }}>
      {children}
    </UploadContext.Provider>
  )
}

export function useUpload() {
  const context = useContext(UploadContext)
  if (context === undefined) {
    throw new Error('useUpload must be used within an UploadProvider')
  }
  return context
}

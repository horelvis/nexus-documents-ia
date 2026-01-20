import { useState } from 'react'
import { Document } from '@/lib/types'

interface DocumentOperationsState {
  // Dialog states
  viewDialogOpen: boolean
  editDialogOpen: boolean
  deleteDialogOpen: boolean
  selectedDocument: Document | null
  
  // Actions
  openViewDialog: (document: Document) => void
  openEditDialog: (document: Document) => void
  openDeleteDialog: (document: Document) => void
  closeAllDialogs: () => void
}

export function useDocumentOperations(): DocumentOperationsState {
  const [viewDialogOpen, setViewDialogOpen] = useState(false)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null)

  const openViewDialog = (document: Document) => {
    setSelectedDocument(document)
    setViewDialogOpen(true)
  }

  const openEditDialog = (document: Document) => {
    setSelectedDocument(document)
    setEditDialogOpen(true)
  }

  const openDeleteDialog = (document: Document) => {
    setSelectedDocument(document)
    setDeleteDialogOpen(true)
  }

  const closeAllDialogs = () => {
    setViewDialogOpen(false)
    setEditDialogOpen(false)
    setDeleteDialogOpen(false)
    setSelectedDocument(null)
  }

  return {
    viewDialogOpen,
    editDialogOpen,
    deleteDialogOpen,
    selectedDocument,
    openViewDialog,
    openEditDialog,
    openDeleteDialog,
    closeAllDialogs
  }
}
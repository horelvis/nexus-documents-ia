"use client"

import React, { createContext, useContext } from 'react'
import { toast } from 'sonner'

interface ToastContextType {
  showSuccessToast: (message: string) => void
  showErrorToast: (message: string) => void
}

export const ToastContext = createContext<ToastContextType>({
  showSuccessToast: () => {},
  showErrorToast: () => {},
})

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const showSuccessToast = (message: string) => {
    toast.success(message)
  }

  const showErrorToast = (message: string) => {
    toast.error(message)
  }

  return (
    <ToastContext.Provider value={{ showSuccessToast, showErrorToast }}>
      {children}
    </ToastContext.Provider>
  )
}

export const useToast = () => {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}
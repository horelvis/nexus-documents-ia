/**
 * Type stub for @/contexts/ToastContext.
 * Actual implementation lives in the consuming app.
 */
import React from 'react'

export declare const ToastContext: React.Context<{
  showSuccessToast: (message: string) => void
  showErrorToast: (message: string) => void
}>

export declare function ToastProvider(props: { children: React.ReactNode }): React.JSX.Element

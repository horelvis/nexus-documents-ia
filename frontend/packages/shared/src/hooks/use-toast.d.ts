/**
 * Type stub for @/hooks/use-toast.
 * Actual implementation lives in the consuming app.
 */
export declare function useToast(): {
  toast: (props: any) => void
  dismiss: (toastId?: string) => void
  toasts: any[]
}

export declare function toast(props: any): void
